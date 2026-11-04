import json
import os
import time
import warnings

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.ensemble import AdaBoostClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score
from sklearn.tree import DecisionTreeClassifier

warnings.filterwarnings("ignore", category=RuntimeWarning)

DATA_PATH = "data.csv"
OUT = "v2"
N_ORIG = 7377418
BLOCKS = {
    "train_a": (0.2, 0.4),
    "train_b": (0.4, 0.6),
    "valid": (0.6, 0.8),
    "test": (0.8, 1.0),
}
POP_BOUND = {"train_a": 12, "train_b": 21, "valid": 28, "test": 35}
LAG_FRAC = 0.43
SMOOTH_M = 5
SEED = 42
TRAIN_N = None
SLOW_N = 200000
LGB_SEEDS = [1, 2, 3]
DROP_TRAIN_NO_HISTORY = True
USE_MEMBERSHIP_DAYS = True
RUN_SOURCE_VARIANT = True
EVAL_TEST = True
SAVE_FEATURES = True
N_BOOT = 300

CAT = "primary_genre_code"
KEYS = ["row_order", "msno", "song_id", "target"]
SRC_COLS = ["src_tab", "src_screen", "src_type"]
BIG = 1 << 23
LAG_ROWS = int(LAG_FRAC * N_ORIG)
V1_REF = {"valid_holdout_AUC": 0.66515, "test_g0_AUC": 0.6528, "test_g30_AUC": 0.6199}

os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def tick(msg):
    print(f"[{time.time() - T0:.0f}초] {msg}")


usecols = [
    "row_order", "msno", "song_id", "target",
    "source_system_tab", "source_screen_name", "source_type",
    "song_length_min", "is_short", "is_long", "primary_genre", "n_genres",
    "main_artist", "n_artists", "is_various_artist", "language",
    "bd_clean", "age_group", "gender", "registration_init_time", "expiration_date",
]
df = pd.read_csv(DATA_PATH, engine="pyarrow", usecols=usecols)
df = df.sort_values("row_order", kind="stable").reset_index(drop=True)
ro = df["row_order"].to_numpy().astype(np.int64)
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
Y = df["target"].to_numpy(dtype=float)
SRC = {
    c: pd.factorize(df[s].astype(str))[0].astype(np.int64) + 1
    for c, s in zip(SRC_COLS, ["source_system_tab", "source_screen_name", "source_type"])
}

nU = int(U.max()) + 1
NS = int(S.max()) + 1
NA = int(A.max()) + 1
NG = int(G.max()) + 1
KUS = U * NS + S
KUA = np.where(A >= 0, U * NA + A, -1)
KUG = np.where(G >= 0, U * NG + G, -1)

first = np.unique(U, return_index=True)[1]
mem = df.iloc[first]
days = (pd.to_datetime(mem["expiration_date"]) - pd.to_datetime(mem["registration_init_time"])).dt.days.to_numpy(dtype=float)
MEM_DAYS = np.full(nU, np.nan)
MEM_DAYS[U[first]] = days


def prior_cnt(keys):
    return pd.Series(keys).groupby(keys).cumcount().to_numpy()


prior_song = prior_cnt(S)
prior_ua = prior_cnt(KUA)
prior_ug = prior_cnt(KUG)
valid_a = A >= 0
valid_g = G >= 0
new_a = valid_a & (prior_ua == 0)
oot_g = valid_g & (prior_ug == 0)
log_pop = np.log1p(prior_song)
pop_thr = np.interp(ro / N_ORIG, [0.2, 0.4, 0.6, 0.8], [12, 21, 28, 35])
pop_seg = prior_song >= pop_thr
unpop_seg = ~pop_seg
tick("행 단위 누적 횟수 계산 완료")

thr = np.maximum(ro - LAG_ROWS, 0)
k_all = np.searchsorted(ro, thr, side="left")
cumY = np.concatenate([[0.0], np.cumsum(Y)])
prior_all = np.where(k_all > 0, cumY[k_all] / np.maximum(k_all, 1), np.nan)


def lagged_rate(hist_key, look_key):
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
    return rate.astype(np.float32)


LAGR = {
    "user_rate_lag": lagged_rate(U, U),
    "song_rate_lag": lagged_rate(S, S),
    "user_artist_rate_lag": lagged_rate(KUA, KUA),
    "user_genre_rate_lag": lagged_rate(KUG, KUG),
}
for nm, m in {"pop": pop_seg, "unpop": unpop_seg, "newartist": new_a, "ootgenre": oot_g}.items():
    LAGR[f"user_{nm}_rate_lag"] = lagged_rate(np.where(m, U, -1), U)
tick(f"지연 정답 재청취율 {len(LAGR)}종 계산 완료 (지연 {LAG_ROWS:,}행)")


def count_lookup(hist, q):
    h = hist[hist >= 0]
    uk, c = np.unique(h, return_counts=True)
    if len(uk) == 0:
        return np.zeros(len(q)), uk, c
    p = np.minimum(np.searchsorted(uk, q), len(uk) - 1)
    found = (q >= 0) & (uk[p] == q)
    return np.where(found, c[p], 0).astype(float), uk, c


def safe_ratio(a, b):
    out = np.full(len(a), np.nan)
    np.divide(a, b, out=out, where=b > 0)
    return out


def build(name):
    lo, hi = BLOCKS[name]
    s0, s1 = cut(lo), cut(hi)
    assert s0 > 0 and ro[s0 - 1] < lo * N_ORIG and ro[s0 - 1] < ro[s0]
    sl = slice(s0, s1)
    bu, bs = U[sl], S[sl]

    uc = np.bincount(U[:s0], minlength=nU).astype(float)
    sc = np.bincount(S[:s0], minlength=NS).astype(float)
    _, us_uk, _ = count_lookup(KUS[:s0], KUS[sl])
    ua_cnt, ua_uk, _ = count_lookup(KUA[:s0], KUA[sl])
    ug_cnt, ug_uk, ug_c = count_lookup(KUG[:s0], KUG[sl])

    nuniq_song = np.bincount(us_uk // NS, minlength=nU)
    nusers_song = np.bincount(us_uk % NS, minlength=NS)
    nuniq_artist = np.bincount(ua_uk // NA, minlength=nU)
    ug_u = ug_uk // NG
    tot = np.bincount(ug_u, weights=ug_c, minlength=nU)
    p = ug_c / tot[ug_u]
    ent = np.bincount(ug_u, weights=-p * np.log(p), minlength=nU)
    top = np.zeros(nU)
    np.maximum.at(top, ug_u, p)
    nuniq_genre = np.bincount(ug_u, minlength=nU)

    def ucount(mask):
        return np.bincount(U[:s0][mask[:s0]], minlength=nU).astype(float)

    n_pop, n_unpop = ucount(pop_seg), ucount(unpop_seg)
    n_new, n_oot = ucount(new_a), ucount(oot_g)
    n_va, n_vg = ucount(valid_a), ucount(valid_g)
    pop_sum = np.bincount(U[:s0], weights=log_pop[:s0], minlength=nU)

    user_cnt = uc[bu]
    song_cnt = sc[bs]
    is_pop = (song_cnt >= POP_BOUND[name]).astype(np.int8)
    d = df.iloc[sl]

    f = pd.DataFrame({
        "row_order": ro[sl],
        "msno": d["msno"].to_numpy(),
        "song_id": d["song_id"].to_numpy(),
        "target": d["target"].to_numpy(),
        "song_length_min": d["song_length_min"].to_numpy(np.float32),
        "is_short": d["is_short"].to_numpy(),
        "is_long": d["is_long"].to_numpy(),
        "n_genres": d["n_genres"].to_numpy(),
        "n_artists": d["n_artists"].to_numpy(),
        "language": d["language"].to_numpy(),
        "is_various_artist": d["is_various_artist"].to_numpy(),
        "bd_clean": d["bd_clean"].to_numpy(np.float32),
        "age_group": d["age_group"].to_numpy(),
        "primary_genre_code": G[sl] + 1,
        "gender_code": d["gender"].map({"male": 1, "female": 2}).fillna(0).to_numpy().astype(np.int8),
        "membership_days": MEM_DAYS[bu],
        "user_cnt": user_cnt,
        "user_nuniq_song": nuniq_song[bu],
        "user_nuniq_artist": nuniq_artist[bu],
        "user_nuniq_genre": nuniq_genre[bu],
        "song_cnt": song_cnt,
        "song_nusers": nusers_song[bs],
        "is_popular": is_pop,
        "user_artist_cnt": ua_cnt,
        "user_genre_cnt": ug_cnt,
        "user_artist_ratio": np.divide(ua_cnt, user_cnt, out=np.zeros_like(ua_cnt), where=user_cnt > 0),
        "user_genre_ratio": np.divide(ug_cnt, user_cnt, out=np.zeros_like(ug_cnt), where=user_cnt > 0),
        "user_genre_entropy": ent[bu],
        "user_top_genre_share": top[bu],
        "is_new_artist": ((A[sl] >= 0) & (ua_cnt == 0)).astype(np.int8),
        "is_out_of_taste_genre": ((G[sl] >= 0) & (ug_cnt == 0)).astype(np.int8),
        "user_pop_n": n_pop[bu],
        "user_unpop_n": n_unpop[bu],
        "user_newartist_n": n_new[bu],
        "user_ootgenre_n": n_oot[bu],
        "user_new_artist_ratio": safe_ratio(n_new, n_va)[bu],
        "user_new_genre_ratio": safe_ratio(n_oot, n_vg)[bu],
        "user_unpop_ratio": safe_ratio(n_unpop, uc)[bu],
        "user_avg_song_pop": safe_ratio(pop_sum, uc)[bu],
    })
    for k, v in LAGR.items():
        f[k] = v[sl]
    f["user_popseg_rate_lag"] = np.where(is_pop == 1, LAGR["user_pop_rate_lag"][sl], LAGR["user_unpop_rate_lag"][sl])
    for c in SRC_COLS:
        f[c] = SRC[c][sl]

    fc = f.select_dtypes("float64").columns
    f[fc] = f[fc].astype("float32")
    if SAVE_FEATURES:
        f.to_parquet(f"{OUT}/featv2lag_{name}.parquet", index=False)
    return f


B = {name: build(name) for name in BLOCKS}
tick("블록별 특성 생성 완료 " + ", ".join(f"{k} {len(v):,}" for k, v in B.items()))

FEATS = [c for c in B["valid"].columns if c not in KEYS and c not in SRC_COLS]
if not USE_MEMBERSHIP_DAYS:
    FEATS.remove("membership_days")
print("모델 입력 특성 수:", len(FEATS))

tr = pd.concat([B["train_a"], B["train_b"]], ignore_index=True)
n_before = len(tr)
if DROP_TRAIN_NO_HISTORY:
    tr = tr[tr["user_rate_lag"].notna()].reset_index(drop=True)
if TRAIN_N is not None and TRAIN_N < len(tr):
    tr = tr.sample(n=TRAIN_N, random_state=SEED).reset_index(drop=True)
va, te = B["valid"], B["test"]
print(f"학습 행 {len(tr):,} (정답 이력이 없어 제외한 행 {n_before - len(tr):,})")

ytr = tr["target"].to_numpy()
yv = va["target"].to_numpy()
yte = te["target"].to_numpy()
users = va["msno"].unique()
rng = np.random.default_rng(SEED)
tune_users = set(rng.choice(users, len(users) // 2, replace=False))
is_tune = va["msno"].isin(tune_users).to_numpy()
is_hold = ~is_tune
yt, yh = yv[is_tune], yv[is_hold]
user_h = va["msno"].to_numpy()[is_hold]
user_te = te["msno"].to_numpy()


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
        rows.append({
            "모델": n,
            "AUC": roc_auc_score(y, p),
            "logloss": log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)),
            "ECE": ece(y, p),
            "평균예측": p.mean(),
            "실제평균": float(np.mean(y)),
        })
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


Xtr, Xva = tr[FEATS], va[FEATS]
Xt = va.loc[is_tune, FEATS]
Xte = te[FEATS] if EVAL_TEST else None


def fit_lgb(seed, feats, cats):
    m = lgb.LGBMClassifier(
        n_estimators=1500, learning_rate=0.03, num_leaves=31, max_depth=6,
        min_child_samples=500, subsample=0.7, subsample_freq=1, colsample_bytree=0.6,
        reg_lambda=10.0, n_jobs=-1, random_state=SEED + seed, verbose=-1,
    )
    m.fit(
        tr[feats], ytr, eval_set=[(va.loc[is_tune, feats], yt)], eval_metric="auc",
        categorical_feature=cats, callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    return m


def lgb_pred(m, X):
    return m.predict_proba(X, num_iteration=m.best_iteration_)[:, 1]


lgb_models, lgb_va, lgb_te = [], [], []
for s in LGB_SEEDS:
    m = fit_lgb(s, FEATS, [CAT])
    lgb_models.append(m)
    lgb_va.append(lgb_pred(m, Xva))
    if EVAL_TEST:
        lgb_te.append(lgb_pred(m, Xte))
    tick(f"LightGBM seed {s} 완료 (반복 {m.best_iteration_}) holdout AUC {roc_auc_score(yh, lgb_va[-1][is_hold]):.5f}")

cat = CatBoostClassifier(
    iterations=1500, learning_rate=0.06, depth=5, l2_leaf_reg=10, random_seed=SEED + 1,
    verbose=0, thread_count=-1, cat_features=[CAT], eval_metric="AUC",
    od_type="Iter", od_wait=40, use_best_model=True,
)
cat.fit(Xtr, ytr, eval_set=(Xt, yt))
cat_va = cat.predict_proba(Xva)[:, 1]
cat_te = cat.predict_proba(Xte)[:, 1] if EVAL_TEST else None
tick(f"CatBoost 완료 (반복 {cat.get_best_iteration()}) holdout AUC {roc_auc_score(yh, cat_va[is_hold]):.5f}")

sub = np.random.default_rng(SEED).choice(len(tr), min(SLOW_N, len(tr)), replace=False)
ada = AdaBoostClassifier(
    estimator=DecisionTreeClassifier(max_depth=4, min_samples_leaf=200),
    n_estimators=60, learning_rate=0.5, random_state=SEED,
)
ada.fit(Xtr.fillna(-1).iloc[sub], ytr[sub])
ada_va = ada.predict_proba(Xva.fillna(-1))[:, 1]
ada_te = ada.predict_proba(Xte.fillna(-1))[:, 1] if EVAL_TEST else None
tick(f"AdaBoost 완료 holdout AUC {roc_auc_score(yh, ada_va[is_hold]):.5f}")

P_va = {"AdaBoost": ada_va, "LightGBM_v2": np.mean(lgb_va, axis=0), "CatBoost_v2": cat_va}
members = list(P_va.keys())
Z_va = np.column_stack([logit(P_va[k]) for k in members])
meta = LogisticRegression(C=1.0, max_iter=200).fit(Z_va[is_tune], yt)
pA_va = meta.predict_proba(Z_va)[:, 1]
print("스태킹 계수:", dict(zip(members, meta.coef_[0].round(3))))

pop_lr = LogisticRegression().fit(np.log1p(tr[["song_cnt"]].to_numpy()), ytr)
p_pop_va = pop_lr.predict_proba(np.log1p(va[["song_cnt"]].to_numpy()))[:, 1]
u_va = va["user_rate_lag"].to_numpy(dtype=float)
u_fill = np.nanmean(u_va)
p_usr_va = np.where(np.isnan(u_va), u_fill, u_va)

preds_va = {**{k: v[is_hold] for k, v in P_va.items()}, "모델A_v2": pA_va[is_hold], "인기도 기준선": p_pop_va[is_hold], "사용자 재청취율 기준선": p_usr_va[is_hold]}
res_va = table(yh, preds_va)
print("\nvalid holdout 성능")
print(res_va.round(5).to_string(index=False))
print(f"(v1 참고: 모델 A valid holdout AUC {V1_REF['valid_holdout_AUC']})")

chk_rows = []
am, ab, d, lo, hi = boot_diff(yh, user_h, pA_va[is_hold], p_pop_va[is_hold])
chk_rows.append({"구간": "valid holdout", "비교": "인기도", "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
am, ab, d, lo, hi = boot_diff(yh, user_h, pA_va[is_hold], p_usr_va[is_hold])
chk_rows.append({"구간": "valid holdout", "비교": "사용자 기준선", "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})

res_te = None
if EVAL_TEST:
    P_te = {"AdaBoost": ada_te, "LightGBM_v2": np.mean(lgb_te, axis=0), "CatBoost_v2": cat_te}
    Z_te = np.column_stack([logit(P_te[k]) for k in members])
    pA_te = meta.predict_proba(Z_te)[:, 1]
    p_pop_te = pop_lr.predict_proba(np.log1p(te[["song_cnt"]].to_numpy()))[:, 1]
    u_te = te["user_rate_lag"].to_numpy(dtype=float)
    p_usr_te = np.where(np.isnan(u_te), u_fill, u_te)
    res_te = table(yte, {**P_te, "모델A_v2": pA_te, "인기도 기준선": p_pop_te, "사용자 재청취율 기준선": p_usr_te})
    print("\ntest 성능 (v1에서 이미 한 번 열었던 test라 낙관적일 수 있음)")
    print(res_te.round(5).to_string(index=False))
    print(f"(v1 참고: test g0 AUC {V1_REF['test_g0_AUC']}, test g30 AUC {V1_REF['test_g30_AUC']})")
    for label, pb in [("인기도", p_pop_te), ("사용자 기준선", p_usr_te)]:
        am, ab, d, lo, hi = boot_diff(yte, user_te, pA_te, pb)
        chk_rows.append({"구간": "test", "비교": label, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})

chk = pd.DataFrame(chk_rows)
print("\n합격선 검증 (사용자 단위 부트스트랩)")
print(chk.round(4).to_string(index=False))

src_result = None
if RUN_SOURCE_VARIANT:
    feats_s = FEATS + SRC_COLS
    ms = fit_lgb(LGB_SEEDS[0], feats_s, [CAT] + SRC_COLS)
    ps_va = lgb_pred(ms, va[feats_s])
    base_va = lgb_va[0]
    am, ab, d, lo, hi = boot_diff(yh, user_h, ps_va[is_hold], base_va[is_hold])
    src_result = {"valid_holdout_AUC_source": am, "valid_holdout_AUC_기본": ab, "차이": d, "CI": [lo, hi]}
    print(f"\nsource_* 포함 LightGBM: valid holdout AUC {am:.5f} vs 미포함 {ab:.5f}, 차이 {d:+.5f}, CI [{lo:.5f}, {hi:.5f}]")
    if EVAL_TEST:
        ps_te = lgb_pred(ms, te[feats_s])
        src_result["test_AUC_source"] = float(roc_auc_score(yte, ps_te))
        src_result["test_AUC_기본"] = float(roc_auc_score(yte, lgb_te[0]))
        print(f"source_* 포함 test AUC {src_result['test_AUC_source']:.5f} vs 미포함 {src_result['test_AUC_기본']:.5f}")
    print("주의: source_*는 곡이 재생될 때 정해지는 값이라 B1·B2 후보곡 재정렬 단계에서는 쓸 수 없음. 참고용 비교입니다.")

out_va = va[["row_order", "msno", "song_id", "target"]].copy()
out_va["p_modelA_v2"] = pA_va
out_va["is_tune"] = is_tune
out_va.to_parquet(f"{OUT}/pred_valid_modelA_v2.parquet", index=False)

if EVAL_TEST:
    out_te = te[["row_order", "msno", "song_id", "target"]].copy()
    out_te["p_modelA_v2"] = pA_te
    out_te["rank"] = out_te.groupby("msno")["p_modelA_v2"].rank(method="first", ascending=False)
    top10 = out_te[out_te["rank"] <= 10].sort_values(["msno", "rank"])
    ucnt = out_te.groupby("msno").size()
    elig = ucnt[ucnt >= 10].index
    print(f"\n후보 10곡 이상 사용자 {len(elig)}명 | 상위 10곡 재청취율 {top10[top10['msno'].isin(elig)]['target'].mean():.4f} vs 전체 후보 {out_te[out_te['msno'].isin(elig)]['target'].mean():.4f}")
    out_te.to_parquet(f"{OUT}/pred_test_modelA_v2.parquet", index=False)
    top10.to_csv(f"{OUT}/recommend_top10_test_modelA_v2.csv", index=False)

joblib.dump({"ada": ada, "lgb": lgb_models, "meta": meta, "members": members, "features": FEATS}, f"{OUT}/modelA_v2_models.joblib")
cat.save_model(f"{OUT}/modelA_v2_catboost.cbm")
res_va.to_csv(f"{OUT}/result_valid_holdout.csv", index=False)
if res_te is not None:
    res_te.to_csv(f"{OUT}/result_test.csv", index=False)
chk.to_csv(f"{OUT}/result_합격선검증.csv", index=False)
with open(f"{OUT}/modelA_v2_설정과결과.json", "w", encoding="utf-8") as f:
    json.dump({
        "LAG_FRAC": LAG_FRAC, "LAG_ROWS": LAG_ROWS, "SMOOTH_M": SMOOTH_M,
        "TRAIN_N": TRAIN_N, "학습행수": int(len(tr)), "LGB_SEEDS": LGB_SEEDS,
        "DROP_TRAIN_NO_HISTORY": DROP_TRAIN_NO_HISTORY, "USE_MEMBERSHIP_DAYS": USE_MEMBERSHIP_DAYS,
        "특성수": len(FEATS), "특성목록": FEATS, "스태킹_구성": members,
        "스태킹_계수": dict(zip(members, meta.coef_[0].round(4).tolist())),
        "source_비교": src_result, "v1_참고": V1_REF,
    }, f, ensure_ascii=False, indent=2, default=float)
tick(f"저장 완료: {os.path.abspath(OUT)}")