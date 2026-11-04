# v11: v10 특성 129개 고정. 기본 모델 4종(LightGBM 2종, CatBoost, XGBoost)과 단독·평균·가중평균·스태킹 조합을 모두 비교.
# 주의: source_*는 재생 시점에 정해지는 값이라 기획서 방침(모델 입력 제외)과 다르다.
# 이 버전은 "해당 경로로 재생된 곡이 재청취될지"를 예측하는 모델이다.
import json
import os
import time
import warnings

import joblib
import optuna
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from catboost import CatBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score

warnings.filterwarnings("ignore", category=RuntimeWarning)
optuna.logging.set_verbosity(optuna.logging.WARNING)

DATA_PATH = "data.csv"
V6_DIR = "v6"
OUT = "v11"
V10_DIR = "v10"
V8_DIR = "v8"
V9_DIR = "v9"
N_ORIG = 7377418
BLOCKS = {
    "train_a": (0.2, 0.4),
    "train_b": (0.4, 0.6),
    "valid": (0.6, 0.8),
    "test": (0.8, 1.0),
}
LAG_FRAC = 0.43
SMOOTH_M = 5
SEED = 42
W_LONG = 300000
W_TINY = 2000
ADOPT_GAIN = 0.001
N_TRIALS = 6
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


df = pd.read_csv(DATA_PATH, engine="pyarrow", usecols=["row_order", "msno", "song_id", "main_artist", "is_various_artist", "primary_genre", "target", "source_system_tab", "source_screen_name", "source_type"])
df = df.sort_values("row_order", kind="stable").reset_index(drop=True)
ro = df["row_order"].to_numpy().astype(np.int64)
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
    out = pd.Series(K).groupby(K).cumcount().to_numpy().astype(np.float32)
    out[K < 0] = np.nan
    return out


def prior_sum(K, x):
    x = np.asarray(x, dtype=float)
    out = (pd.Series(x).groupby(K).cumsum().to_numpy() - x).astype(np.float32)
    out[K < 0] = np.nan
    return out


def window_cnt(K, w):
    out = np.full(N, np.nan, dtype=np.float32)
    idx = np.flatnonzero(K >= 0)
    comp = K[idx] * BIG + ro[idx]
    order = np.argsort(comp, kind="stable")
    cs = comp[order]
    out[idx[order]] = np.arange(len(cs)) - np.searchsorted(cs, cs - w, side="left")
    return out


def prev_same(V):
    out = np.full(N, np.nan, dtype=np.float32)
    o = np.argsort(U, kind="stable")
    same_u = U[o][1:] == U[o][:-1]
    v1, v0 = V[o][1:], V[o][:-1]
    out[o[1:][same_u]] = ((v1 == v0) & (v1 >= 0))[same_u]
    return out


def ratio(a, b):
    return (a / np.maximum(b, 1)).astype(np.float32)


thr = np.maximum(ro - LAG_ROWS, 0)
k_all = np.searchsorted(ro, thr, side="left")
cumY = np.concatenate([[0.0], np.cumsum(Y)])
prior_all = np.where(k_all > 0, cumY[k_all] / np.maximum(k_all, 1), np.nan)


def lagged_rate(hist_key, look_key, w=None):
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
    f = pd.read_parquet(f"{V6_DIR}/featv6_{name}.parquet")
    assert len(f) == s1 - s0 and (f["row_order"].to_numpy() == ro[s0:s1]).all()
    assert (f["src_type"].to_numpy() == T[s0:s1] + 1).all()
    for k, v in F.items():
        f[k] = v[s0:s1]
    B[name] = f
    tick(f"{name} 특성 결합 {len(f):,}행")
del F

cfg6 = json.load(open(f"{V6_DIR}/modelA_v6_설정과결과.json", encoding="utf-8"))
FEATS6 = [c for g in cfg6["특성그룹"].values() for c in g]
FEATS7 = FEATS6 + SRC_COLS + V7_NEW
GROUPS = {**cfg6["특성그룹"], "노출경로": SRC_COLS + V7_NEW, "라이브러리성향(v9)": LIB_COLS, "경로프로필(v10)": PROF_COLS}
FEATS9 = FEATS7 + LIB_COLS
FEATS = FEATS9 + PROF_COLS
print("후보 특성 수:", len(FEATS), {k: len(v) for k, v in GROUPS.items()})

tr_all = pd.concat([B["train_a"], B["train_b"]], ignore_index=True)
tr = tr_all[tr_all["user_rate_lag"].notna()].reset_index(drop=True)
va, te = B["valid"], B["test"]
ytr, yv, yte = tr["target"].to_numpy(), va["target"].to_numpy(), te["target"].to_numpy()
print(f"학습 행 {len(tr):,}")

users = va["msno"].unique()
rng = np.random.default_rng(SEED)
tune_users = set(rng.choice(users, len(users) // 2, replace=False))
is_tune = va["msno"].isin(tune_users).to_numpy()
is_hold = ~is_tune
yt, yh = yv[is_tune], yv[is_hold]
user_h, user_te = va["msno"].to_numpy()[is_hold], te["msno"].to_numpy()


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def ece(yy, p, n_bins=10):
    b = pd.qcut(p, q=n_bins, duplicates="drop")
    s = pd.DataFrame({"y": yy, "p": p, "b": b}).groupby("b", observed=True).agg(y=("y", "mean"), p=("p", "mean"), n=("y", "size"))
    return float((s["n"] * (s["y"] - s["p"]).abs()).sum() / s["n"].sum())


def table(y, preds):
    rows = []
    for n, p in preds.items():
        p = np.asarray(p, dtype=float)
        rows.append({"모델": n, "AUC": roc_auc_score(y, p), "logloss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)), "ECE": ece(y, p), "평균예측": p.mean(), "실제평균": float(np.mean(y))})
    return pd.DataFrame(rows)


def boot_diff(yy, user, p_m, p_b, n_boot=N_BOOT):
    yy = np.asarray(yy).astype(float)
    codes, uniq = pd.factorize(np.asarray(user))
    nu = len(uniq)
    _, gm = np.unique(np.asarray(p_m, dtype=float), return_inverse=True)
    _, gb = np.unique(np.asarray(p_b, dtype=float), return_inverse=True)
    km, kb = gm.max() + 1, gb.max() + 1

    def wauc(g, k, w):
        pos = np.bincount(g, weights=w * yy, minlength=k)
        neg = np.bincount(g, weights=w * (1 - yy), minlength=k)
        below = np.cumsum(neg) - neg
        return float((pos * (below + 0.5 * neg)).sum() / (pos.sum() * neg.sum()))

    ones = np.ones(len(yy))
    am, ab = wauc(gm, km, ones), wauc(gb, kb, ones)
    r = np.random.default_rng(SEED)
    d = np.empty(n_boot)
    for i in range(n_boot):
        w = np.bincount(r.integers(0, nu, nu), minlength=nu).astype(float)[codes]
        d[i] = wauc(gm, km, w) - wauc(gb, kb, w)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return am, ab, am - ab, float(lo), float(hi)


def fit_lgb(d, seed, n_est=None, feats=None, params=None):
    feats = FEATS if feats is None else feats
    kw = dict(subsample_freq=1, n_jobs=-1, random_state=SEED + seed, verbose=-1, **(PARAMS if params is None else params))
    y = d["target"].to_numpy()
    if n_est is None:
        m = lgb.LGBMClassifier(n_estimators=3000, **kw)
        m.fit(d[feats], y, eval_set=[(va.loc[is_tune, feats], yt)], eval_metric="auc", categorical_feature=CATS, callbacks=[lgb.early_stopping(50, verbose=False)])
    else:
        m = lgb.LGBMClassifier(n_estimators=n_est, **kw)
        m.fit(d[feats], y, categorical_feature=CATS)
    return m


def lgb_pred(m, X):
    return m.predict_proba(X, num_iteration=m.best_iteration_)[:, 1] if m.best_iteration_ else m.predict_proba(X)[:, 1]



MEMBERS = ["LightGBM", "LightGBM_B", "CatBoost", "XGBoost"]
LGB_B_SEEDS = [11, 12, 13]
LGB_B_PARAMS = dict(learning_rate=0.03, num_leaves=127, max_depth=10, min_child_samples=800, subsample=0.8, colsample_bytree=0.45, reg_lambda=20.0)
CAT_KW = dict(learning_rate=0.08, depth=8, l2_leaf_reg=10, max_ctr_complexity=1, random_seed=SEED + 1, verbose=0, thread_count=-1, cat_features=CATS)
XGB_KW = dict(learning_rate=0.04, max_depth=9, min_child_weight=100, subsample=0.8, colsample_bytree=0.6, reg_lambda=10.0, tree_method="hist", n_jobs=-1, random_state=SEED)


def fit_member(name, d, n_iter=None):
    es = n_iter is None
    X, y = d[FEATS], d["target"].to_numpy()
    Xt = va.loc[is_tune, FEATS]
    if name in ("LightGBM", "LightGBM_B"):
        seeds, params = (LGB_SEEDS, PARAMS) if name == "LightGBM" else (LGB_B_SEEDS, LGB_B_PARAMS)
        ms = [fit_lgb(d, s, n_iter, params=params) for s in seeds]
        it = int(np.mean([m.best_iteration_ for m in ms])) if es else n_iter
    elif name == "CatBoost":
        ms = CatBoostClassifier(iterations=3000 if es else n_iter, **({"eval_metric": "AUC", "od_type": "Iter", "od_wait": 50, "use_best_model": True} if es else {}), **CAT_KW)
        ms.fit(X, y, eval_set=(Xt, yt)) if es else ms.fit(X, y)
        it = int(ms.get_best_iteration()) + 1 if es else n_iter
    else:
        ms = xgb.XGBClassifier(n_estimators=3000 if es else n_iter, **({"eval_metric": "auc", "early_stopping_rounds": 50} if es else {}), **XGB_KW)
        ms.fit(X, y, eval_set=[(Xt, yt)], verbose=False) if es else ms.fit(X, y, verbose=False)
        it = int(ms.best_iteration) + 1 if es else n_iter
    tick(f"{name} 완료 (반복 {it})")
    return {"m": ms, "es": es, "it": it}


def predict_member(name, M, X):
    if name in ("LightGBM", "LightGBM_B"):
        return np.mean([lgb_pred(m, X) for m in M["m"]], axis=0)
    if name == "CatBoost":
        return M["m"].predict_proba(X)[:, 1]
    xg = M["m"]
    return xg.predict_proba(X, iteration_range=(0, xg.best_iteration + 1))[:, 1] if M["es"] else xg.predict_proba(X)[:, 1]


cfg8 = json.load(open(f"{V8_DIR}/modelA_v8_설정과결과.json", encoding="utf-8"))
PARAMS = cfg8["params"]
tr = tr_all
ytr = tr["target"].to_numpy()
FEATS = FEATS9 + PROF_COLS
print(f"특성 {len(FEATS)}개 | 학습 행 {len(tr):,}")

M1 = {n: fit_member(n, tr) for n in MEMBERS}
Xva = va[FEATS]
P = {n: predict_member(n, M1[n], Xva) for n in MEMBERS}
tick("valid 단계 기본 모델 4종 완료 | 반복 수 " + str({n: M1[n]["it"] for n in MEMBERS}))

# 조합 후보: 단독 4, 동일가중 평균(2~4개) 11, tune에서 찾은 가중 평균 1, 로지스틱 스태킹 1
from itertools import combinations, product

COMBOS = {}
for n in MEMBERS:
    COMBOS[n] = {"type": "단독", "w": {n: 1.0}}
for k in range(2, len(MEMBERS) + 1):
    for sub in combinations(MEMBERS, k):
        COMBOS["평균(" + "+".join(sub) + ")"] = {"type": "평균", "w": {n: 1 / k for n in sub}}

grid = [w for w in product(np.arange(0, 1.01, 0.1), repeat=len(MEMBERS)) if abs(sum(w) - 1) < 1e-9]
best_w, best_t = None, -1
for w in grid:
    a = roc_auc_score(yt, sum(wi * P[n][is_tune] for wi, n in zip(w, MEMBERS)))
    if a > best_t:
        best_w, best_t = w, a
COMBOS["가중평균(tune 탐색)"] = {"type": "가중평균", "w": {n: round(float(wi), 1) for wi, n in zip(best_w, MEMBERS) if wi > 0}}
tick(f"가중평균 탐색 {len(grid)}개 조합 | tune AUC {best_t:.5f} | {COMBOS['가중평균(tune 탐색)']['w']}")

Z = np.column_stack([logit(P[n]) for n in MEMBERS])
meta = LogisticRegression(C=1.0, max_iter=300).fit(Z[is_tune], yt)
COMBOS["Stack4"] = {"type": "스태킹", "w": {n: float(c) for n, c in zip(MEMBERS, meta.coef_[0])}}
print("Stack4 가중치:", {n: round(float(c), 3) for n, c in zip(MEMBERS, meta.coef_[0])}, "절편", round(float(meta.intercept_[0]), 3))


def combo_pred(name, PP):
    c = COMBOS[name]
    if c["type"] == "스태킹":
        return meta.predict_proba(np.column_stack([logit(PP[n]) for n in MEMBERS]))[:, 1]
    return sum(w * PP[n] for n, w in c["w"].items())


cand = {n: combo_pred(n, P) for n in COMBOS}
res_all = table(yh, {n: p[is_hold] for n, p in cand.items()})
res_all.insert(1, "유형", [COMBOS[n]["type"] for n in res_all["모델"]])
res_all = res_all.sort_values("AUC", ascending=False).reset_index(drop=True)
print("\nvalid holdout 성능: 조합 후보 전체 (모델 선택에 쓰는 유일한 표)")
print(res_all.round(5).to_string(index=False))

ok = res_all[res_all["ECE"] <= ECE_MAX]
chosen = (ok if len(ok) else res_all).iloc[0]["모델"]
need = [n for n in MEMBERS if n in COMBOS[chosen]["w"]] if COMBOS[chosen]["type"] != "스태킹" else MEMBERS
print(f"\n선정 규칙: ECE {ECE_MAX} 이하 중 valid holdout AUC 최고 | 선정된 모델 A: {chosen} | 필요 모델 {need}")

imp = pd.Series(np.mean([m.booster_.feature_importance("gain") for m in M1["LightGBM"]["m"]], axis=0), index=FEATS)
grp_imp = {g: float(imp[[x for x in c if x in imp.index]].sum() / imp.sum()) for g, c in GROUPS.items()}

pop_lr = LogisticRegression().fit(np.log1p(tr[["s_cnt_now"]].to_numpy()), ytr)
p_pop_va = pop_lr.predict_proba(np.log1p(va[["s_cnt_now"]].to_numpy()))[:, 1]
u_va = va["user_rate_lag"].to_numpy(dtype=float)
u_fill = np.nanmean(u_va)
p_usr_va = np.where(np.isnan(u_va), u_fill, u_va)
p_v10_va = pd.read_parquet(f"{V10_DIR}/pred_valid_modelA_v10.parquet")["p_modelA_v10"].to_numpy()
res_va = table(yh, {f"모델A v11 ({chosen})": cand[chosen][is_hold], "v10 모델 A (LightGBM)": p_v10_va[is_hold], "인기도 기준선": p_pop_va[is_hold], "사용자 재청취율 기준선": p_usr_va[is_hold]})
print("\nvalid holdout: 선정 모델과 비교 대상")
print(res_va.round(5).to_string(index=False))

full = pd.concat([tr, va], ignore_index=True)
MF = {n: fit_member(n, full, max(int(M1[n]["it"] * ITER_SCALE), 50)) for n in need}
tick("train+valid 재학습 완료 | 반복 수 " + str({n: MF[n]["it"] for n in need}))
Xte = te[FEATS]
PT = {n: predict_member(n, MF[n], Xte) for n in need}
pA_te = combo_pred(chosen, PT)
p_pop_te = pop_lr.predict_proba(np.log1p(te[["s_cnt_now"]].to_numpy()))[:, 1]
u_te = te["user_rate_lag"].to_numpy(dtype=float)
p_usr_te = np.where(np.isnan(u_te), u_fill, u_te)
p_v10_te = pd.read_parquet(f"{V10_DIR}/pred_test_modelA_v10.parquet")["p_modelA_v10"].to_numpy()
res_te = table(yte, {f"모델A v11 ({chosen}, train+valid 학습)": pA_te, "v10 모델 A (LightGBM)": p_v10_te, "인기도 기준선": p_pop_te, "사용자 재청취율 기준선": p_usr_te})
print("\ntest 성능 (최종 모델 하나만 평가)")
print(res_te.round(5).to_string(index=False))
auc_te = float(res_te["AUC"].iloc[0])

chk = []
for lab, pb in [("인기도", p_pop_va[is_hold]), ("사용자 기준선", p_usr_va[is_hold]), ("v10 모델 A", p_v10_va[is_hold])]:
    am, ab, d, lo, hi = boot_diff(yh, user_h, cand[chosen][is_hold], pb)
    chk.append({"구간": "valid holdout", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
for lab, pb in [("인기도", p_pop_te), ("사용자 기준선", p_usr_te), ("v10 모델 A", p_v10_te)]:
    am, ab, d, lo, hi = boot_diff(yte, user_te, pA_te, pb)
    chk.append({"구간": "test", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
chk = pd.DataFrame(chk)
print("\n합격선 검증 (사용자 단위 부트스트랩)")
print(chk.round(4).to_string(index=False))

out_va = va[KEYS].copy()
out_va["p_modelA_v11"] = cand[chosen]
out_va["is_tune"] = is_tune
out_va.to_parquet(f"{OUT}/pred_valid_modelA_v11.parquet", index=False)
out_te = te[KEYS].copy()
out_te["p_modelA_v11"] = pA_te
out_te["rank"] = out_te.groupby("msno")["p_modelA_v11"].rank(method="first", ascending=False)
out_te.to_parquet(f"{OUT}/pred_test_modelA_v11.parquet", index=False)
top10 = out_te[out_te["rank"] <= 10].sort_values(["msno", "rank"])
top10.to_csv(f"{OUT}/recommend_top10_test_modelA_v11.csv", index=False)
print(f"\nTop-10 재청취율 {top10['target'].mean():.4f} vs test 전체 {yte.mean():.4f}")

joblib.dump({"models": {n: (MF[n]["m"] if n != "CatBoost" else None) for n in need}, "meta": meta, "combos": COMBOS, "chosen": chosen, "features": FEATS}, f"{OUT}/modelA_v11_models.joblib")
if "CatBoost" in MF:
    MF["CatBoost"]["m"].save_model(f"{OUT}/modelA_v11_catboost.cbm")
res_all.to_csv(f"{OUT}/result_조합후보_valid_holdout.csv", index=False)
res_va.to_csv(f"{OUT}/result_valid_holdout.csv", index=False)
res_te.to_csv(f"{OUT}/result_test.csv", index=False)
chk.to_csv(f"{OUT}/result_합격선검증.csv", index=False)
(imp / imp.sum()).sort_values(ascending=False).to_csv(f"{OUT}/result_특성중요도.csv", header=["gain비중"])
with open(f"{OUT}/modelA_v11_설정과결과.json", "w", encoding="utf-8") as f:
    json.dump({
        "source_사용": True, "선정": chosen, "선정_조합": COMBOS[chosen], "test_AUC": auc_te,
        "기본모델": {"LightGBM": {"params": PARAMS, "seeds": LGB_SEEDS}, "LightGBM_B": {"params": LGB_B_PARAMS, "seeds": LGB_B_SEEDS},
                  "CatBoost": {k: v for k, v in CAT_KW.items() if k != "cat_features"}, "XGBoost": XGB_KW},
        "valid반복수": {n: M1[n]["it"] for n in MEMBERS}, "재학습반복수": {n: MF[n]["it"] for n in need},
        "가중평균_tune_AUC": float(best_t), "stack4_가중치": dict(zip(MEMBERS, meta.coef_[0].tolist())), "stack4_절편": float(meta.intercept_[0]),
        "특성수": len(FEATS), "특성그룹": GROUPS, "그룹별_gain비중": grp_imp,
    }, f, ensure_ascii=False, indent=2, default=float)
tick(f"저장 완료: {os.path.abspath(OUT)}")
