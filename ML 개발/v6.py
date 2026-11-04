import json
import os
import time
import warnings

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from catboost import CatBoostClassifier
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score

warnings.filterwarnings("ignore", category=RuntimeWarning)

DATA_PATH = "data.csv"
OUT = "v6"
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
SVD_COMP = 24
W_SHORT = 20000
W_LONG = 300000
LGB_SEEDS = [1, 2, 3]
AUC_TOL = 0.0003
ECE_MAX = 0.01
ITER_SCALE = 1.15
N_BOOT = 300
RUN_SOURCE_VARIANT = True
TARGET_AUC = 0.70

CAT = "primary_genre_code"
KEYS = ["row_order", "msno", "song_id", "target"]
SRC_COLS = ["src_tab", "src_screen", "src_type"]
BIG = 1 << 23
LAG_ROWS = int(LAG_FRAC * N_ORIG)
REF = {"v4_valid_holdout": 0.63643, "v5_test": 0.64344, "v2_source_valid": 0.66721, "v2_source_test": 0.65193}
PARAMS = dict(learning_rate=0.05, num_leaves=63, max_depth=9, min_child_samples=300, subsample=0.7, colsample_bytree=0.7, reg_lambda=30.0)

os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def tick(msg):
    print(f"[{time.time() - T0:.0f}초] {msg}", flush=True)


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
    out = pd.Series(K).groupby(K).cumcount().to_numpy().astype(np.float32)
    out[K < 0] = np.nan
    return out


def prior_sum(K, x):
    x = np.asarray(x, dtype=float)
    out = (pd.Series(x).groupby(K).cumsum().to_numpy() - x).astype(np.float32)
    out[K < 0] = np.nan
    return out


def last_gap(K):
    out = np.full(N, np.nan, dtype=np.float32)
    idx = np.flatnonzero(K >= 0)
    o = idx[np.argsort(K[idx], kind="stable")]
    same = K[o][1:] == K[o][:-1]
    out[o[1:][same]] = np.log1p(ro[o][1:][same] - ro[o][:-1][same])
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
    f.to_parquet(f"{OUT}/featv6_{name}.parquet", index=False)
    B[name] = f
    tick(f"{name} 특성 생성 {len(f):,}행")
del df, F

FEATS = [c for c in B["valid"].columns if c not in KEYS and c not in SRC_COLS]
GROUPS = {
    "정적": list(STATIC),
    "누적": [c for c in FEATS if c.endswith("_now") or c in ("s_share_in_artist", "is_new_artist", "is_new_genre", "pop_vs_user")],
    "최근성": [c for c in FEATS if c.startswith("gap_") or "_w_" in c or "velocity" in c or "recent" in c or c.startswith("prev_same")],
    "지연정답": [c for c in FEATS if "_lag" in c or c == "rate_gap_user_song"],
    "취향SVD": [c for c in FEATS if c.startswith("svd_")],
}
print("모델 입력 특성 수:", len(FEATS), {k: len(v) for k, v in GROUPS.items()})

tr = pd.concat([B["train_a"], B["train_b"]], ignore_index=True)
tr = tr[tr["user_rate_lag"].notna()].reset_index(drop=True)
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


def fit_lgb(d, feats, seed, cats=(CAT,), n_est=None):
    kw = dict(subsample_freq=1, n_jobs=-1, random_state=SEED + seed, verbose=-1, **PARAMS)
    y = d["target"].to_numpy()
    if n_est is None:
        m = lgb.LGBMClassifier(n_estimators=3000, **kw)
        m.fit(d[feats], y, eval_set=[(va.loc[is_tune, feats], yt)], eval_metric="auc", categorical_feature=list(cats), callbacks=[lgb.early_stopping(50, verbose=False)])
    else:
        m = lgb.LGBMClassifier(n_estimators=n_est, **kw)
        m.fit(d[feats], y, categorical_feature=list(cats))
    return m


def lgb_pred(m, X):
    return m.predict_proba(X, num_iteration=m.best_iteration_)[:, 1] if m.best_iteration_ else m.predict_proba(X)[:, 1]


def fit_all(d, iters=None):
    es = iters is None
    X, y = d[FEATS], d["target"].to_numpy()
    Xt = va.loc[is_tune, FEATS]
    lgbs = [fit_lgb(d, FEATS, s, n_est=None if es else iters["lgb"]) for s in LGB_SEEDS]
    tick(f"LightGBM {len(LGB_SEEDS)}개 완료")
    cat_kw = dict(learning_rate=0.08, depth=7, l2_leaf_reg=10, random_seed=SEED + 1, verbose=0, thread_count=-1, cat_features=[CAT])
    xgb_kw = dict(learning_rate=0.05, max_depth=8, min_child_weight=100, subsample=0.7, colsample_bytree=0.7, reg_lambda=10.0, tree_method="hist", n_jobs=-1, random_state=SEED)
    if es:
        cat = CatBoostClassifier(iterations=2000, eval_metric="AUC", od_type="Iter", od_wait=50, use_best_model=True, **cat_kw)
        cat.fit(X, y, eval_set=(Xt, yt))
        tick("CatBoost 완료")
        xg = xgb.XGBClassifier(n_estimators=3000, eval_metric="auc", early_stopping_rounds=50, **xgb_kw)
        xg.fit(X, y, eval_set=[(Xt, yt)], verbose=False)
        it = {"lgb": int(np.mean([m.best_iteration_ for m in lgbs])), "cat": int(cat.get_best_iteration()) + 1, "xgb": int(xg.best_iteration) + 1}
    else:
        cat = CatBoostClassifier(iterations=iters["cat"], **cat_kw)
        cat.fit(X, y)
        tick("CatBoost 완료")
        xg = xgb.XGBClassifier(n_estimators=iters["xgb"], **xgb_kw)
        xg.fit(X, y, verbose=False)
        it = iters
    tick("XGBoost 완료")
    return {"lgb": lgbs, "cat": cat, "xgb": xg, "es": es, "iters": it}


def predict_all(M, X):
    pl = np.mean([lgb_pred(m, X) for m in M["lgb"]], axis=0)
    pc = M["cat"].predict_proba(X)[:, 1]
    xg = M["xgb"]
    px = xg.predict_proba(X, iteration_range=(0, xg.best_iteration + 1))[:, 1] if M["es"] else xg.predict_proba(X)[:, 1]
    return pl, pc, px


M1 = fit_all(tr)
tick(f"valid 단계 학습 완료 | 반복 수 {M1['iters']}")
Xva = va[FEATS]
pl, pc, px = predict_all(M1, Xva)
p_avg = (pl + pc + px) / 3
Z = np.column_stack([logit(pl), logit(pc), logit(px)])
meta = LogisticRegression(C=1.0, max_iter=200).fit(Z[is_tune], yt)
p_stack = meta.predict_proba(Z)[:, 1]

imp = pd.Series(np.mean([m.booster_.feature_importance("gain") for m in M1["lgb"]], axis=0), index=FEATS)
grp_imp = {g: float(imp[c].sum() / imp.sum()) for g, c in GROUPS.items()}
print("\n특성 그룹별 gain 비중:", {k: round(v, 3) for k, v in grp_imp.items()})
print("상위 15개 특성:\n" + (imp / imp.sum()).sort_values(ascending=False).head(15).round(4).to_string())

pop_lr = LogisticRegression().fit(np.log1p(tr[["s_cnt_now"]].to_numpy()), ytr)
p_pop_va = pop_lr.predict_proba(np.log1p(va[["s_cnt_now"]].to_numpy()))[:, 1]
u_va = va["user_rate_lag"].to_numpy(dtype=float)
u_fill = np.nanmean(u_va)
p_usr_va = np.where(np.isnan(u_va), u_fill, u_va)

cands = {"LightGBM": pl, "CatBoost": pc, "XGBoost": px, "평균3": p_avg, "Stack3": p_stack}
res_va = table(yh, {**{k: v[is_hold] for k, v in cands.items()}, "인기도 기준선": p_pop_va[is_hold], "사용자 재청취율 기준선": p_usr_va[is_hold]})
print("\nvalid holdout 성능 (모델 선택에 쓰는 유일한 표)")
print(res_va.round(5).to_string(index=False))
print(f"(참고: v4 LightGBM valid holdout AUC {REF['v4_valid_holdout']})")

sel = res_va.set_index("모델").loc[list(cands)]
best_auc = sel["AUC"].max()
chosen = next((n for n in cands if sel.loc[n, "AUC"] >= best_auc - AUC_TOL and sel.loc[n, "ECE"] <= ECE_MAX), sel["AUC"].idxmax())
print(f"\n선정된 모델 A: {chosen}")

full = pd.concat([tr, va], ignore_index=True)
iters = {k: max(int(v * ITER_SCALE), 50) for k, v in M1["iters"].items()}
MF = fit_all(full, iters)
tick(f"train+valid 재학습 완료 | 반복 수 {iters}")
tl, tc, tx = predict_all(MF, te[FEATS])
combine = {
    "LightGBM": lambda a, b, c: a, "CatBoost": lambda a, b, c: b, "XGBoost": lambda a, b, c: c,
    "평균3": lambda a, b, c: (a + b + c) / 3,
    "Stack3": lambda a, b, c: meta.predict_proba(np.column_stack([logit(a), logit(b), logit(c)]))[:, 1],
}
pA_te = combine[chosen](tl, tc, tx)
p_pop_te = pop_lr.predict_proba(np.log1p(te[["s_cnt_now"]].to_numpy()))[:, 1]
u_te = te["user_rate_lag"].to_numpy(dtype=float)
p_usr_te = np.where(np.isnan(u_te), u_fill, u_te)
res_te = table(yte, {f"모델A v6 ({chosen}, train+valid 학습)": pA_te, "인기도 기준선": p_pop_te, "사용자 재청취율 기준선": p_usr_te})
print("\ntest 성능 (최종 모델 하나만 평가, 이미 여러 번 열었던 test라 참고용)")
print(res_te.round(5).to_string(index=False))
auc_te = float(res_te["AUC"].iloc[0])
print(f"(참고: v5 test AUC {REF['v5_test']}) | 목표 {TARGET_AUC}: {'달성' if auc_te >= TARGET_AUC else f'미달 ({auc_te - TARGET_AUC:+.4f})'}")

chk = []
for lab, pb in [("인기도", p_pop_va[is_hold]), ("사용자 기준선", p_usr_va[is_hold])]:
    am, ab, d, lo, hi = boot_diff(yh, user_h, cands[chosen][is_hold], pb)
    chk.append({"구간": "valid holdout", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
for lab, pb in [("인기도", p_pop_te), ("사용자 기준선", p_usr_te)]:
    am, ab, d, lo, hi = boot_diff(yte, user_te, pA_te, pb)
    chk.append({"구간": "test", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
chk = pd.DataFrame(chk)
print("\n합격선 검증 (사용자 단위 부트스트랩)")
print(chk.round(4).to_string(index=False))

src_result = None
if RUN_SOURCE_VARIANT:
    feats_s = FEATS + SRC_COLS
    ms = fit_lgb(tr, feats_s, 1, cats=[CAT] + SRC_COLS)
    base = M1["lgb"][0]
    src_result = {
        "valid_holdout_AUC_source": float(roc_auc_score(yh, lgb_pred(ms, va.loc[is_hold, feats_s]))),
        "valid_holdout_AUC_기본": float(roc_auc_score(yh, lgb_pred(base, va.loc[is_hold, FEATS]))),
        "test_AUC_source": float(roc_auc_score(yte, lgb_pred(ms, te[feats_s]))),
        "test_AUC_기본": float(roc_auc_score(yte, lgb_pred(base, te[FEATS]))),
    }
    print("\nsource_* 포함 LightGBM 1개 (train만 학습, 참고용):", {k: round(v, 5) for k, v in src_result.items()})
    print("주의: source_*는 기획서 방침상 모델 입력에서 제외. 재생 시점에 정해지는 값이라 추천 단계에서는 쓸 수 없음.")

out_va = va[KEYS].copy()
out_va["p_modelA_v6"] = cands[chosen]
out_va["is_tune"] = is_tune
out_va.to_parquet(f"{OUT}/pred_valid_modelA_v6.parquet", index=False)
out_te = te[KEYS].copy()
out_te["p_modelA_v6"] = pA_te
out_te["rank"] = out_te.groupby("msno")["p_modelA_v6"].rank(method="first", ascending=False)
out_te.to_parquet(f"{OUT}/pred_test_modelA_v6.parquet", index=False)
top10 = out_te[out_te["rank"] <= 10].sort_values(["msno", "rank"])
top10.to_csv(f"{OUT}/recommend_top10_test_modelA_v6.csv", index=False)
print(f"\nTop-10 재청취율 {top10['target'].mean():.4f} vs test 전체 {yte.mean():.4f}")

joblib.dump({"lgb": MF["lgb"], "xgb": MF["xgb"], "meta": meta, "iters": MF["iters"], "features": FEATS, "chosen": chosen}, f"{OUT}/modelA_v6_models.joblib")
MF["cat"].save_model(f"{OUT}/modelA_v6_catboost.cbm")
res_va.to_csv(f"{OUT}/result_valid_holdout.csv", index=False)
res_te.to_csv(f"{OUT}/result_test.csv", index=False)
chk.to_csv(f"{OUT}/result_합격선검증.csv", index=False)
(imp / imp.sum()).sort_values(ascending=False).to_csv(f"{OUT}/result_특성중요도.csv", header=["gain비중"])
with open(f"{OUT}/modelA_v6_설정과결과.json", "w", encoding="utf-8") as f:
    json.dump({
        "선정": chosen, "test_AUC": auc_te, "목표AUC": TARGET_AUC, "LAG_ROWS": LAG_ROWS,
        "W_SHORT": W_SHORT, "W_LONG": W_LONG, "params": PARAMS, "반복수": MF["iters"],
        "특성수": len(FEATS), "특성그룹": GROUPS, "그룹별_gain비중": grp_imp,
        "source_비교": src_result, "참고": REF,
    }, f, ensure_ascii=False, indent=2, default=float)
tick(f"저장 완료: {os.path.abspath(OUT)}")
