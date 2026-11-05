# 데모 쌍(사용자 x 웹곡)의 모델 입력 특성 129개를 만든다.
# 원본: 전달용_코드패키지/A/v11.py 의 특성 생성부(1~2단계)를 그대로 복사하고 아래만 바꿨다 (학습·평가 부분은 제거).
#   1) data.csv 맨 뒤에 쌍 행(row_order >= N_ORIG)을 붙여서 읽는다            -> load_data()
#   2) 쌍 행은 누적 계산(횟수·합·창·간격·직전 행)에 들어가지 않고, data.csv 전체 이력의 마지막 상태를 읽기만 한다
#      -> prior_cnt / prior_sum / window_cnt / last_gap / prev_same 교체, lagged_rate 의 이력에서 쌍 제외
#   3) 쌍 행만 특성 파일로 저장한다.
# 입력: data.csv, server/data/pairs_raw.parquet (prepare_pairs.py)   출력: server/data/pairs_features.parquet, features.json
# 사용: python3 web/tools/build_serving_features.py
# 주의: 노출 경로(source_*)를 모델 입력에 사용한다.
import json
import os
import time
import warnings

import joblib
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score

warnings.filterwarnings("ignore", category=RuntimeWarning)

from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = str(ROOT / "data.csv")
PAIRS_PATH = os.environ.get("PAIRS_PATH", str(ROOT / "server/data/pairs_raw.parquet"))


def load_data(usecols):
    """data.csv 뒤에 데모 쌍 행을 붙여서 돌려준다 (v11.py 는 data.csv 만 읽음)."""
    d = pd.read_csv(DATA_PATH, engine="pyarrow", usecols=usecols)
    p = pd.read_parquet(PAIRS_PATH, columns=usecols)
    return pd.concat([d, p], ignore_index=True)

OUT = os.environ.get("OUT_DIR", str(ROOT / "server/data"))
V10_DIR = "v10"   # 선택: 이전 모델(v10) 예측 파일이 있으면 결과 비교표에 추가한다. 없어도 실행된다
N_ORIG = 7377418
BLOCKS = {"pair": (1.0, 2.0)}   # 쌍 행만 만든다(맨 뒤, row_order >= N_ORIG)
LAG_FRAC = 0.43
SMOOTH_M = 5
SEED = 42
SVD_COMP = 24
W_SHORT = 20000
W_LONG = 300000
SAVE_FEATURES = True   # 보정 분석(B 폴더)이 읽는 특성 파일(featv11_*)을 저장
W_TINY = 2000
ADOPT_GAIN = 0.001
LGB_SEEDS = [1, 2, 3, 4, 5]
AUC_TOL = 0.0003
ECE_MAX = 0.01
ITER_SCALE = 1.15
N_BOOT = 300
TARGET_AUC = 0.70

CAT = "primary_genre_code"
KEYS = ["row_order", "msno", "song_id", "target"]
SRC_COLS = ["src_tab", "src_screen", "src_type"]
CATS = [CAT] + SRC_COLS
BIG = 1 << 23
LAG_ROWS = int(LAG_FRAC * N_ORIG)
REF = {"v6_valid_holdout": 0.67484, "v7_valid_holdout": 0.70845, "v8_valid_holdout": 0.71108, "v9_valid_holdout": 0.71299}
PARAMS = dict(learning_rate=0.05, num_leaves=63, max_depth=9, min_child_samples=300, subsample=0.7, colsample_bytree=0.7, reg_lambda=30.0)

os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def tick(msg):
    print(f"[{time.time() - T0:.0f}초] {msg}", flush=True)


def build_v6_features():
    """[1단계] 원본 data.csv에서 기본 특성 71개를 만든다(구 v6.py). 구간별 DataFrame과 특성 그룹을 돌려준다."""
    usecols = [
        "row_order", "msno", "song_id", "target",
        "source_system_tab", "source_screen_name", "source_type",
        "song_length_min", "is_short", "is_long", "primary_genre", "n_genres",
        "main_artist", "n_artists", "is_various_artist", "language",
        "bd_clean", "age_group", "gender", "registration_init_time", "expiration_date",
    ]
    df = load_data(usecols)
    df = df.sort_values("row_order", kind="stable").reset_index(drop=True)
    ro = df["row_order"].to_numpy().astype(np.int64)
    PAIR = ro >= N_ORIG   # 데모 쌍 행(맨 뒤). 누적 계산에는 안 들어가고 값만 읽음
    NREAL = int((~PAIR).sum())
    assert PAIR[NREAL:].all()
    N = len(df)
    tick(f"데이터 로드 {N:,}행")


    def cut(frac):
        return int(np.searchsorted(ro, frac * N_ORIG, side="left"))


    U = pd.factorize(df["msno"])[0].astype(np.int64)
    S = pd.factorize(df["song_id"])[0].astype(np.int64)
    A = pd.factorize(df["main_artist"])[0].astype(np.int64)
    A[df["is_various_artist"].to_numpy() == 1] = -1
    pg = df["primary_genre"].astype(str)
    G = pd.factorize(pg)[0].astype(np.int64)
    G[(pg == "unknown").to_numpy()] = -1
    L = pd.factorize(df["language"])[0].astype(np.int64)
    L[(df["language"] == -1).to_numpy()] = -1
    Y = df["target"].to_numpy(dtype=float)
    SRC = {
        c: pd.factorize(df[s].astype(str))[0].astype(np.int64) + 1
        for c, s in zip(SRC_COLS, ["source_system_tab", "source_screen_name", "source_type"])
    }

    nU, NS, NA, NG, NL = (int(x.max()) + 1 for x in (U, S, A, G, L))
    KUA = np.where(A >= 0, U * NA + A, -1)
    KUG = np.where(G >= 0, U * NG + G, -1)
    KUL = np.where(L >= 0, U * NL + L, -1)

    first = np.unique(U, return_index=True)[1]
    mem = df.iloc[first]
    reg = pd.to_datetime(mem["registration_init_time"])
    MEM_DAYS = np.full(nU, np.nan)
    MEM_DAYS[U[first]] = (pd.to_datetime(mem["expiration_date"]) - reg).dt.days.to_numpy(dtype=float)
    REG_YEAR = np.full(nU, np.nan)
    REG_YEAR[U[first]] = reg.dt.year.to_numpy(dtype=float)


    # 행 단위 특성: 모두 "현재 행 직전까지"의 기록만 쓴다(정답 미사용)
    def prior_cnt(K):
        Kr = K[:NREAL]
        out = np.empty(N, dtype=np.float32)
        out[:NREAL] = pd.Series(Kr).groupby(Kr).cumcount().to_numpy()
        out[NREAL:] = pd.Series(K[NREAL:]).map(pd.Series(Kr).value_counts()).fillna(0).to_numpy()
        out[K < 0] = np.nan
        return out


    def prior_sum(K, x):
        x = np.asarray(x, dtype=float)
        Kr, xr = K[:NREAL], x[:NREAL]
        out = np.empty(N, dtype=np.float32)
        out[:NREAL] = pd.Series(xr).groupby(Kr).cumsum().to_numpy() - xr
        out[NREAL:] = pd.Series(K[NREAL:]).map(pd.Series(xr).groupby(Kr).sum()).fillna(0).to_numpy()
        out[K < 0] = np.nan
        return out


    def last_gap(K):
        out = np.full(N, np.nan, dtype=np.float32)
        idx = np.flatnonzero(K[:NREAL] >= 0)
        o = idx[np.argsort(K[idx], kind="stable")]
        same = K[o][1:] == K[o][:-1]
        out[o[1:][same]] = np.log1p(ro[o][1:][same] - ro[o][:-1][same])
        last = pd.Series(ro[o]).groupby(K[o]).max()
        pi = np.flatnonzero(K[NREAL:] >= 0) + NREAL
        lr = pd.Series(K[pi]).map(last).to_numpy(dtype=float)
        out[pi] = np.log1p(ro[pi] - lr)
        return out


    def window_cnt(K, w):
        out = np.full(N, np.nan, dtype=np.float32)
        idx = np.flatnonzero(K[:NREAL] >= 0)
        comp = K[idx] * BIG + ro[idx]
        order = np.argsort(comp, kind="stable")
        cs = comp[order]
        out[idx[order]] = np.arange(len(cs)) - np.searchsorted(cs, cs - w, side="left")
        pi = np.flatnonzero(K[NREAL:] >= 0) + NREAL
        q = K[pi] * BIG + ro[pi]
        out[pi] = np.searchsorted(cs, q, side="left") - np.searchsorted(cs, q - w, side="left")
        return out


    def prev_same(V):
        out = np.full(N, np.nan, dtype=np.float32)
        Ur, Vr = U[:NREAL], V[:NREAL]
        o = np.argsort(Ur, kind="stable")
        same_u = Ur[o][1:] == Ur[o][:-1]
        v1, v0 = Vr[o][1:], Vr[o][:-1]
        out[o[1:][same_u]] = ((v1 == v0) & (v1 >= 0))[same_u]
        li = pd.Series(U[NREAL:]).map(pd.Series(np.arange(NREAL)).groupby(Ur).max())
        ok = li.notna().to_numpy()
        vl = V[li.fillna(0).astype(int).to_numpy()]
        vp = V[NREAL:]
        out[NREAL:] = np.where(ok, ((vp == vl) & (vp >= 0)).astype(np.float32), np.nan)
        return out


    def ratio(a, b):
        return (a / np.maximum(b, 1)).astype(np.float32)


    F = {}
    F["u_cnt_now"] = prior_cnt(U)
    F["s_cnt_now"] = prior_cnt(S)
    F["a_cnt_now"] = prior_cnt(A)
    F["ua_cnt_now"] = prior_cnt(KUA)
    F["ug_cnt_now"] = prior_cnt(KUG)
    F["ul_cnt_now"] = prior_cnt(KUL)
    F["ua_share_now"] = ratio(F["ua_cnt_now"], F["u_cnt_now"])
    F["ug_share_now"] = ratio(F["ug_cnt_now"], F["u_cnt_now"])
    F["ul_share_now"] = ratio(F["ul_cnt_now"], F["u_cnt_now"])
    F["s_share_in_artist"] = ratio(F["s_cnt_now"], F["a_cnt_now"])

    valid_a, valid_g = A >= 0, G >= 0
    new_a = valid_a & (F["ua_cnt_now"] == 0)
    oot_g = valid_g & (F["ug_cnt_now"] == 0)
    log_pop = np.log1p(F["s_cnt_now"])
    F["is_new_artist"] = new_a.astype(np.int8)
    F["is_new_genre"] = oot_g.astype(np.int8)
    F["u_nuniq_artist_now"] = prior_sum(U, new_a)
    F["u_nuniq_genre_now"] = prior_sum(U, oot_g)
    F["u_newartist_ratio_now"] = ratio(F["u_nuniq_artist_now"], prior_sum(U, valid_a))
    F["u_avg_pop_now"] = ratio(prior_sum(U, log_pop), F["u_cnt_now"])
    F["pop_vs_user"] = (log_pop - F["u_avg_pop_now"]).astype(np.float32)
    tick("누적 횟수 특성 완료")

    for tag, K in (("u", U), ("s", S), ("a", A), ("ua", KUA), ("ug", KUG)):
        F[f"gap_{tag}"] = last_gap(K)
    for tag, K in (("u", U), ("s", S), ("a", A)):
        F[f"{tag}_w_short"] = window_cnt(K, W_SHORT)
        F[f"{tag}_w_long"] = window_cnt(K, W_LONG)
    F["ua_w_long"] = window_cnt(KUA, W_LONG)
    F["ug_w_long"] = window_cnt(KUG, W_LONG)
    F["ua_share_recent"] = ratio(F["ua_w_long"], F["u_w_long"])
    F["ug_share_recent"] = ratio(F["ug_w_long"], F["u_w_long"])
    F["s_velocity"] = (F["s_w_long"] / (F["s_cnt_now"] + 1)).astype(np.float32)
    F["a_velocity"] = (F["a_w_long"] / (F["a_cnt_now"] + 1)).astype(np.float32)
    F["u_velocity"] = (F["u_w_long"] / (F["u_cnt_now"] + 1)).astype(np.float32)
    F["prev_same_artist"] = prev_same(A)
    F["prev_same_genre"] = prev_same(G)
    tick("최근성·연속성 특성 완료")

    # 지연 정답 재청취율: 현재 행보다 LAG_ROWS 이상 앞선 행의 정답만 사용(v2 규칙 유지)
    thr = np.maximum(ro - LAG_ROWS, 0)
    k_all = np.searchsorted(ro, thr, side="left")
    cumY = np.concatenate([[0.0], np.cumsum(Y)])
    prior_all = np.where(k_all > 0, cumY[k_all] / np.maximum(k_all, 1), np.nan)


    def lagged_rate(hist_key, look_key):
        hist_key = np.where(PAIR, -1, hist_key)
        idx = np.flatnonzero(hist_key >= 0)
        comp = hist_key[idx] * BIG + ro[idx]
        order = np.argsort(comp, kind="stable")
        comp = comp[order]
        cy = np.concatenate([[0.0], np.cumsum(Y[idx][order])])
        ok = look_key >= 0
        q = np.where(ok, look_key, 0)
        lo = np.searchsorted(comp, q * BIG, side="left")
        hi = np.searchsorted(comp, q * BIG + thr, side="left")
        cnt = (hi - lo).astype(float)
        ssum = cy[hi] - cy[lo]
        cnt[~ok] = 0.0
        ssum[~ok] = 0.0
        rate = (ssum + prior_all * SMOOTH_M) / (cnt + SMOOTH_M)
        return rate.astype(np.float32), cnt.astype(np.float32)


    pop_seg = F["s_cnt_now"] >= np.interp(ro / N_ORIG, [0.2, 0.4, 0.6, 0.8], [12, 21, 28, 35])
    for nm, (hk, lk) in {
        "user": (U, U), "song": (S, S), "artist": (A, A), "genre": (G, G),
        "user_artist": (KUA, KUA), "user_genre": (KUG, KUG), "user_lang": (KUL, KUL),
        "user_pop": (np.where(pop_seg, U, -1), U), "user_unpop": (np.where(~pop_seg, U, -1), U),
        "user_newartist": (np.where(new_a, U, -1), U), "user_ootgenre": (np.where(oot_g, U, -1), U),
    }.items():
        F[f"{nm}_rate_lag"], n = lagged_rate(hk, lk)
        if nm in ("user", "song", "artist"):
            F[f"{nm}_lag_n"] = n
    F["user_popseg_rate_lag"] = np.where(pop_seg, F["user_pop_rate_lag"], F["user_unpop_rate_lag"])
    F["user_newseg_rate_lag"] = np.where(new_a, F["user_newartist_rate_lag"], F["user_artist_rate_lag"])
    F["rate_gap_user_song"] = (F["song_rate_lag"] - F["user_rate_lag"]).astype(np.float32)
    tick(f"지연 정답 재청취율 완료 (지연 {LAG_ROWS:,}행)")

    STATIC = {
        "song_length_min": df["song_length_min"].to_numpy(np.float32),
        "is_short": df["is_short"].to_numpy(),
        "is_long": df["is_long"].to_numpy(),
        "n_genres": df["n_genres"].to_numpy(),
        "n_artists": df["n_artists"].to_numpy(),
        "language": df["language"].to_numpy(),
        "is_various_artist": df["is_various_artist"].to_numpy(),
        "bd_clean": df["bd_clean"].to_numpy(np.float32),
        "age_group": df["age_group"].to_numpy(),
        CAT: G + 1,
        "gender_code": df["gender"].map({"male": 1, "female": 2}).fillna(0).to_numpy().astype(np.int8),
        "membership_days": MEM_DAYS[U].astype(np.float32),
        "reg_year": REG_YEAR[U].astype(np.float32),
    }


    def svd_feats(s0, s1):
        out = {}
        qu = U[s0:s1]
        for tag, items, n_items in (("song", S, NS), ("artist", A, NA)):
            hi = items[:s0]
            m = hi >= 0
            mat = sparse.csr_matrix((np.ones(m.sum(), dtype=np.float32), (U[:s0][m], hi[m])), shape=(nU, n_items))
            mat.data = np.log1p(mat.data)
            svd = TruncatedSVD(n_components=SVD_COMP, n_iter=3, random_state=SEED)
            uv = svd.fit_transform(mat)
            iv = svd.components_.T
            qi = items[s0:s1]
            ok = qi >= 0
            a, b = uv[qu], iv[np.where(ok, qi, 0)]
            dot = np.einsum("ij,ij->i", a, b)
            cos = dot / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-9)
            dot[~ok] = np.nan
            cos[~ok] = np.nan
            out[f"svd_{tag}_dot"] = dot.astype(np.float32)
            out[f"svd_{tag}_cos"] = cos.astype(np.float32)
        return out


    B = {}
    for name, (lo, hi) in BLOCKS.items():
        s0, s1 = cut(lo), cut(hi)
        sl = slice(s0, s1)
        f = pd.DataFrame({"row_order": ro[sl], "msno": df["msno"].to_numpy()[sl], "song_id": df["song_id"].to_numpy()[sl], "target": df["target"].to_numpy()[sl]})
        for k, v in {**STATIC, **F}.items():
            f[k] = v[sl]
        for k, v in svd_feats(s0, s1).items():
            f[k] = v
        for c in SRC_COLS:
            f[c] = SRC[c][sl]
        fc = f.select_dtypes("float64").columns
        f[fc] = f[fc].astype("float32")
        B[name] = f
        tick(f"{name} 특성 생성 {len(f):,}행")
    del df, F

    FEATS_ = [c for c in B["pair"].columns if c not in KEYS and c not in SRC_COLS]
    GROUPS6 = {
        "정적": list(STATIC),
        "누적": [c for c in FEATS_ if c.endswith("_now") or c in ("s_share_in_artist", "is_new_artist", "is_new_genre", "pop_vs_user")],
        "최근성": [c for c in FEATS_ if c.startswith("gap_") or "_w_" in c or "velocity" in c or "recent" in c or c.startswith("prev_same")],
        "지연정답": [c for c in FEATS_ if "_lag" in c or c == "rate_gap_user_song"],
        "취향SVD": [c for c in FEATS_ if c.startswith("svd_")],
    }
    return B, GROUPS6



B6, GROUPS6 = build_v6_features()

df = load_data(["row_order", "msno", "song_id", "main_artist", "is_various_artist", "primary_genre", "target", "source_system_tab", "source_screen_name", "source_type"])
df = df.sort_values("row_order", kind="stable").reset_index(drop=True)
ro = df["row_order"].to_numpy().astype(np.int64)
PAIR = ro >= N_ORIG   # 데모 쌍 행(맨 뒤). 누적 계산에는 안 들어가고 값만 읽음
NREAL = int((~PAIR).sum())
assert PAIR[NREAL:].all()
N = len(df)
U = pd.factorize(df["msno"])[0].astype(np.int64)
S = pd.factorize(df["song_id"])[0].astype(np.int64)
A = pd.factorize(df["main_artist"])[0].astype(np.int64)
A[df["is_various_artist"].to_numpy() == 1] = -1
pg = df["primary_genre"].astype(str)
G = pd.factorize(pg)[0].astype(np.int64)
G[(pg == "unknown").to_numpy()] = -1
Y = df["target"].to_numpy(dtype=float)
# v6 특성 파일과 같은 코드(factorize + 1)를 쓴다
SRC = {
    c: pd.factorize(df[s].astype(str))[0].astype(np.int64)
    for c, s in zip(SRC_COLS, ["source_system_tab", "source_screen_name", "source_type"])
}
st = df["source_type"].astype(str).to_numpy()
IS_LOCAL = np.isin(st, ["local-library", "local-playlist"])
IS_RADIO = st == "radio"
del df, st
nU, NS, NA, NG = int(U.max()) + 1, int(S.max()) + 1, int(A.max()) + 1, int(G.max()) + 1
tick(f"데이터 로드 {N:,}행")


def cut(frac):
    return int(np.searchsorted(ro, frac * N_ORIG, side="left"))


def prior_cnt(K):
    Kr = K[:NREAL]
    out = np.empty(N, dtype=np.float32)
    out[:NREAL] = pd.Series(Kr).groupby(Kr).cumcount().to_numpy()
    out[NREAL:] = pd.Series(K[NREAL:]).map(pd.Series(Kr).value_counts()).fillna(0).to_numpy()
    out[K < 0] = np.nan
    return out


def prior_sum(K, x):
    x = np.asarray(x, dtype=float)
    Kr, xr = K[:NREAL], x[:NREAL]
    out = np.empty(N, dtype=np.float32)
    out[:NREAL] = pd.Series(xr).groupby(Kr).cumsum().to_numpy() - xr
    out[NREAL:] = pd.Series(K[NREAL:]).map(pd.Series(xr).groupby(Kr).sum()).fillna(0).to_numpy()
    out[K < 0] = np.nan
    return out


def window_cnt(K, w):
    out = np.full(N, np.nan, dtype=np.float32)
    idx = np.flatnonzero(K[:NREAL] >= 0)
    comp = K[idx] * BIG + ro[idx]
    order = np.argsort(comp, kind="stable")
    cs = comp[order]
    out[idx[order]] = np.arange(len(cs)) - np.searchsorted(cs, cs - w, side="left")
    pi = np.flatnonzero(K[NREAL:] >= 0) + NREAL
    q = K[pi] * BIG + ro[pi]
    out[pi] = np.searchsorted(cs, q, side="left") - np.searchsorted(cs, q - w, side="left")
    return out


def prev_same(V):
    out = np.full(N, np.nan, dtype=np.float32)
    Ur, Vr = U[:NREAL], V[:NREAL]
    o = np.argsort(Ur, kind="stable")
    same_u = Ur[o][1:] == Ur[o][:-1]
    v1, v0 = Vr[o][1:], Vr[o][:-1]
    out[o[1:][same_u]] = ((v1 == v0) & (v1 >= 0))[same_u]
    li = pd.Series(U[NREAL:]).map(pd.Series(np.arange(NREAL)).groupby(Ur).max())
    ok = li.notna().to_numpy()
    vl = V[li.fillna(0).astype(int).to_numpy()]
    vp = V[NREAL:]
    out[NREAL:] = np.where(ok, ((vp == vl) & (vp >= 0)).astype(np.float32), np.nan)
    return out


def ratio(a, b):
    return (a / np.maximum(b, 1)).astype(np.float32)


thr = np.maximum(ro - LAG_ROWS, 0)
k_all = np.searchsorted(ro, thr, side="left")
cumY = np.concatenate([[0.0], np.cumsum(Y)])
prior_all = np.where(k_all > 0, cumY[k_all] / np.maximum(k_all, 1), np.nan)


def lagged_rate(hist_key, look_key, w=None):
    hist_key = np.where(PAIR, -1, hist_key)
    idx = np.flatnonzero(hist_key >= 0)
    comp = hist_key[idx] * BIG + ro[idx]
    order = np.argsort(comp, kind="stable")
    comp = comp[order]
    cy = np.concatenate([[0.0], np.cumsum(Y[idx][order])])
    ok = look_key >= 0
    q = np.where(ok, look_key, 0)
    lo = np.searchsorted(comp, q * BIG + (0 if w is None else np.maximum(thr - w, 0)), side="left")
    hi = np.searchsorted(comp, q * BIG + thr, side="left")
    cnt = (hi - lo).astype(float)
    ssum = cy[hi] - cy[lo]
    cnt[~ok] = 0.0
    ssum[~ok] = 0.0
    rate = (ssum + prior_all * SMOOTH_M) / (cnt + SMOOTH_M)
    return rate.astype(np.float32)


T, C, R = SRC["src_type"], SRC["src_screen"], SRC["src_tab"]
NT, NC, NR = int(T.max()) + 1, int(C.max()) + 1, int(R.max()) + 1
KUT, KUC, KUR = U * NT + T, U * NC + C, U * NR + R
KST = S * NT + T
KAT = np.where(A >= 0, A * NT + T, -1)
KTC = T * NC + C
KUA = np.where(A >= 0, U * NA + A, -1)
KUG = np.where(G >= 0, U * NG + G, -1)

F = {}
# 지연 정답 재청취율 (정답은 LAG_ROWS 이상 앞선 행만)
for nm, K in {
    "srctype": T, "srcscreen": C, "srctab": R, "srctype_screen": KTC,
    "user_srctype": KUT, "user_srcscreen": KUC, "user_srctab": KUR,
    "song_srctype": KST, "artist_srctype": KAT,
}.items():
    F[f"{nm}_rate_lag"] = lagged_rate(K, K)
tick("경로별 지연 재청취율 완료")

# 정답 없이 쓰는 경로 행동 특성
u_cnt = prior_cnt(U)
s_cnt = prior_cnt(S)
F["ut_cnt_now"] = prior_cnt(KUT)
F["ut_share_now"] = ratio(F["ut_cnt_now"], u_cnt)
F["ur_share_now"] = ratio(prior_cnt(KUR), u_cnt)
F["uc_share_now"] = ratio(prior_cnt(KUC), u_cnt)
F["st_share_now"] = ratio(prior_cnt(KST), s_cnt)
u_w = window_cnt(U, W_LONG)
F["ut_share_recent"] = ratio(window_cnt(KUT, W_LONG), u_w)
F["prev_same_srctype"] = prev_same(T)
F["prev_same_srcscreen"] = prev_same(C)
tick("경로 행동 특성 완료")

# v9 신규: 라이브러리·라디오 성향 (정답 미사용, 현재 행 직전까지)
LIB = {}
a_cnt = prior_cnt(A)
LIB["s_local_share_now"] = ratio(prior_sum(S, IS_LOCAL), s_cnt)
LIB["s_local_n_now"] = prior_sum(S, IS_LOCAL)
LIB["s_radio_share_now"] = ratio(prior_sum(S, IS_RADIO), s_cnt)
LIB["a_local_share_now"] = ratio(prior_sum(A, IS_LOCAL), a_cnt)
LIB["u_local_share_now"] = ratio(prior_sum(U, IS_LOCAL), u_cnt)
LIB["u_radio_share_now"] = ratio(prior_sum(U, IS_RADIO), u_cnt)
LIB["ua_local_cnt_now"] = prior_sum(KUA, IS_LOCAL)
LIB["ua_local_share_now"] = ratio(LIB["ua_local_cnt_now"], prior_cnt(KUA))
LIB["u_local_share_recent"] = ratio(window_cnt(np.where(IS_LOCAL, U, -1), W_LONG), u_w)
LIB["u_w_tiny"] = window_cnt(U, W_TINY)
LIB["ut_w_tiny"] = window_cnt(KUT, W_TINY)
F.update(LIB)
tick("라이브러리·라디오 성향 특성 완료")

# v10 신규: 경로 프로필 = 지금까지 재생된 탭별 비율 (정답 미사용)
PROF = {}
for k in range(NR):
    m = R == k
    PROF[f"s_tab{k}_share"] = ratio(prior_sum(S, m), s_cnt)
    PROF[f"u_tab{k}_share"] = ratio(prior_sum(U, m), u_cnt)
    PROF[f"a_tab{k}_share"] = ratio(prior_sum(A, m), a_cnt)
F.update(PROF)
tick(f"경로 프로필 특성 {len(PROF)}개 완료")
NEW = list(F)
LIB_COLS = list(LIB)
PROF_COLS = list(PROF)
V7_NEW = [c for c in NEW if c not in LIB_COLS and c not in PROF_COLS]

B = {}
for name, (lo, hi) in BLOCKS.items():
    s0, s1 = cut(lo), cut(hi)
    f = B6[name]
    assert len(f) == s1 - s0 and (f["row_order"].to_numpy() == ro[s0:s1]).all()
    assert (f["src_type"].to_numpy() == T[s0:s1] + 1).all()
    for k, v in F.items():
        f[k] = v[s0:s1]
    B[name] = f
    tick(f"{name} 특성 결합 {len(f):,}행")
del F

FEATS6 = [c for g in GROUPS6.values() for c in g]
FEATS7 = FEATS6 + SRC_COLS + V7_NEW
GROUPS = {**GROUPS6, "노출경로": SRC_COLS + V7_NEW, "라이브러리성향(v9)": LIB_COLS, "경로프로필(v10)": PROF_COLS}
FEATS9 = FEATS7 + LIB_COLS
FEATS = FEATS9 + PROF_COLS
print("후보 특성 수:", len(FEATS), {k: len(v) for k, v in GROUPS.items()})


import json as _json
_users = {v: k for k, v in _json.load(open(ROOT / "server/data/demo_users.json")).items()}
_f = B["pair"][KEYS + FEATS].copy()
_f["user"] = _f["msno"].map(_users)     # 실제 ID 대신 가명(A~D)도 함께 저장
_f.to_parquet(f"{OUT}/pairs_features.parquet", index=False)
_json.dump(FEATS, open(f"{OUT}/features.json", "w"))
tick(f"저장 완료: {len(_f):,}쌍 x 특성 {len(FEATS)}개")
