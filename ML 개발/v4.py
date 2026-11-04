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
V3_DIR = "v3"
OUT = "v4"
N_ORIG = 7377418
BLOCKS = {
    "train_a": (0.2, 0.4),
    "train_b": (0.4, 0.6),
    "valid": (0.6, 0.8),
    "test": (0.8, 1.0),
}
SEED = 42
SVD_BIG = 64
SVD_GENRE = 8
RECENT_K = 50
ADOPT_GAIN = 0.001
LGB_SEEDS = [1, 2, 3]
AUC_TOL = 0.0003
ECE_MAX = 0.01
N_BOOT = 300

CAT = "primary_genre_code"
KEYS = ["row_order", "msno", "song_id", "target"]
REF = {"v3_valid_holdout": 0.63452, "v3_test": 0.62666}

os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def tick(msg):
    print(f"[{time.time() - T0:.0f}초] {msg}")


cfg = json.load(open(f"{V3_DIR}/modelA_v3_설정과결과.json", encoding="utf-8"))
FEATS0 = cfg["특성목록"]
PARAMS = cfg["optuna_best_params"]

df = pd.read_csv(DATA_PATH, engine="pyarrow", usecols=["row_order", "msno", "song_id", "main_artist", "is_various_artist", "primary_genre"])
df = df.sort_values("row_order", kind="stable").reset_index(drop=True)
ro = df["row_order"].to_numpy().astype(np.int64)
U = pd.factorize(df["msno"])[0].astype(np.int64)
S = pd.factorize(df["song_id"])[0].astype(np.int64)
A = pd.factorize(df["main_artist"])[0].astype(np.int64)
A[df["is_various_artist"].to_numpy() == 1] = -1
pg = df["primary_genre"].astype(str)
G = pd.factorize(pg)[0].astype(np.int64)
G[(pg == "unknown").to_numpy()] = -1
nU, NS, NA, NG = int(U.max()) + 1, int(S.max()) + 1, int(A.max()) + 1, int(G.max()) + 1


def cut(frac):
    return int(np.searchsorted(ro, frac * N_ORIG, side="left"))


def dot_cos(a, b, ok):
    dot = np.einsum("ij,ij->i", a, b)
    cos = dot / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-9)
    dot[~ok] = np.nan
    cos[~ok] = np.nan
    return dot.astype(np.float32), cos.astype(np.float32)


def svd_pair(items, n_items, s0, s1, comp, idf=False):
    hi = items[:s0]
    m = hi >= 0
    mat = sparse.csr_matrix((np.ones(m.sum(), dtype=np.float32), (U[:s0][m], hi[m])), shape=(nU, n_items))
    mat.data = np.log1p(mat.data)
    if idf:
        dfreq = np.asarray((mat > 0).sum(axis=0)).ravel()
        w = (np.log((nU + 1) / (dfreq + 1)) + 1).astype(np.float32)
        mat = mat @ sparse.diags(w)
    svd = TruncatedSVD(n_components=comp, n_iter=3, random_state=SEED)
    uv = svd.fit_transform(mat)
    iv = svd.components_.T
    qi = items[s0:s1_holder[0]]
    ok = qi >= 0
    dot, cos = dot_cos(uv[U[s0:s1_holder[0]]], iv[np.where(ok, qi, 0)], ok)
    return dot, cos, iv


def recent_cos(items, n_items, iv, s0, s1):
    hu, hi = U[:s0], items[:s0]
    rank = pd.Series(np.arange(s0)).groupby(hu).cumcount(ascending=False).to_numpy()
    m = (rank < RECENT_K) & (hi >= 0)
    R = sparse.csr_matrix((np.ones(m.sum(), dtype=np.float32), (hu[m], hi[m])), shape=(nU, n_items))
    rv = np.asarray(R @ iv)
    qi = items[s0:s1]
    ok = qi >= 0
    _, cos = dot_cos(rv[U[s0:s1]], iv[np.where(ok, qi, 0)], ok)
    return cos


s1_holder = [0]


def new_groups(s0, s1):
    s1_holder[0] = s1
    g = {}
    sd, sc, iv_s = svd_pair(S, NS, s0, s1, SVD_BIG)
    ad, ac, iv_a = svd_pair(A, NA, s0, s1, SVD_BIG)
    g["svd64"] = {"svd64_song_dot": sd, "svd64_song_cos": sc, "svd64_artist_dot": ad, "svd64_artist_cos": ac}
    td, tc, _ = svd_pair(A, NA, s0, s1, 24, idf=True)
    g["tfidf_artist"] = {"tfidf_artist_dot": td, "tfidf_artist_cos": tc}
    gd, gc, _ = svd_pair(G, NG, s0, s1, min(SVD_GENRE, NG - 1))
    g["genre_svd"] = {"genre_svd_dot": gd, "genre_svd_cos": gc}
    g["recent"] = {
        "recent_artist_cos": recent_cos(A, NA, iv_a, s0, s1),
        "recent_song_cos": recent_cos(S, NS, iv_s, s0, s1),
    }
    w = max(s0 // 4, 1)
    rec = slice(s0 - w, s0)
    qs, qa, qu = S[s0:s1], A[s0:s1], U[s0:s1]
    s_tot = np.bincount(S[:s0], minlength=NS)
    s_rec = np.bincount(S[rec], minlength=NS)
    a_hist, a_rec_arr = A[:s0], A[rec]
    a_tot = np.bincount(a_hist[a_hist >= 0], minlength=NA)
    a_rec = np.bincount(a_rec_arr[a_rec_arr >= 0], minlength=NA)
    qa0 = np.where(qa >= 0, qa, 0)
    g["trend"] = {
        "song_recent_cnt": s_rec[qs].astype(np.float32),
        "song_recent_share": (s_rec[qs] / (s_tot[qs] + 1)).astype(np.float32),
        "artist_recent_share": np.where(qa >= 0, a_rec[qa0] / (a_tot[qa0] + 1), np.nan).astype(np.float32),
    }
    u_tot = np.bincount(U[:s0], minlength=nU)
    u_rec = np.bincount(U[rec], minlength=nU)
    g["activity"] = {
        "user_recent_cnt": u_rec[qu].astype(np.float32),
        "user_recent_share": (u_rec[qu] / (u_tot[qu] + 1)).astype(np.float32),
    }
    return g


B = {}
GROUP_COLS = {}
for name, (lo, hi) in BLOCKS.items():
    s0, s1 = cut(lo), cut(hi)
    f = pd.read_parquet(f"{V3_DIR}/featv3_{name}.parquet")
    assert len(f) == s1 - s0 and (f["row_order"].to_numpy() == ro[s0:s1]).all()
    for gname, cols in new_groups(s0, s1).items():
        GROUP_COLS[gname] = list(cols.keys())
        for k, v in cols.items():
            f[k] = v
    B[name] = f
    f.to_parquet(f"{OUT}/featv4_{name}.parquet", index=False)
    tick(f"{name} 새 특성 그룹 {len(GROUP_COLS)}개 추가 완료")

tr = pd.concat([B["train_a"], B["train_b"]], ignore_index=True)
tr = tr[tr["user_rate_lag"].notna()].reset_index(drop=True)
va, te = B["valid"], B["test"]
ytr, yv, yte = tr["target"].to_numpy(), va["target"].to_numpy(), te["target"].to_numpy()

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


def fit_lgb(feats, seed):
    m = lgb.LGBMClassifier(n_estimators=1500, subsample_freq=1, n_jobs=-1, random_state=SEED + seed, verbose=-1, **PARAMS)
    m.fit(
        tr[feats], ytr, eval_set=[(va.loc[is_tune, feats], yt)], eval_metric="auc",
        categorical_feature=[CAT], callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    return m


def lgb_pred(m, X):
    return m.predict_proba(X, num_iteration=m.best_iteration_)[:, 1]


def holdout_auc(feats):
    m = fit_lgb(feats, 1)
    return roc_auc_score(yh, lgb_pred(m, va.loc[is_hold, feats]))


auc0 = holdout_auc(FEATS0)
tick(f"기준(v3 특성 {len(FEATS0)}개) valid holdout AUC {auc0:.5f}")

gains = {}
for gname, cols in GROUP_COLS.items():
    gains[gname] = holdout_auc(FEATS0 + cols) - auc0
    tick(f"그룹 {gname} 단독 추가: {gains[gname]:+.5f}")

FEATS, auc_cur, adopted, log_rows = list(FEATS0), auc0, [], []
for gname in sorted(gains, key=gains.get, reverse=True):
    if gains[gname] <= 0:
        log_rows.append({"그룹": gname, "단독이득": gains[gname], "누적이득": np.nan, "채택": False})
        continue
    a = holdout_auc(FEATS + GROUP_COLS[gname])
    ok = (a - auc_cur) >= ADOPT_GAIN
    log_rows.append({"그룹": gname, "단독이득": gains[gname], "누적이득": a - auc_cur, "채택": bool(ok)})
    if ok:
        FEATS += GROUP_COLS[gname]
        auc_cur = a
        adopted.append(gname)
print("\n새 특성 그룹 채택 결과 (valid holdout, 기준 +%.3f 이상 채택)" % ADOPT_GAIN)
print(pd.DataFrame(log_rows).round(5).to_string(index=False))
print("채택된 그룹:", adopted if adopted else "없음 (v3와 동일)")
print(f"특성 수 {len(FEATS0)} -> {len(FEATS)} | valid holdout AUC {auc0:.5f} -> {auc_cur:.5f}")

Xva, Xt = va[FEATS], va.loc[is_tune, FEATS]
lgb_models = [fit_lgb(FEATS, s) for s in LGB_SEEDS]
p_lgb = np.mean([lgb_pred(m, Xva) for m in lgb_models], axis=0)
tick("LightGBM 시드 평균 완료")

cat = CatBoostClassifier(
    iterations=1500, learning_rate=0.06, depth=5, l2_leaf_reg=10, random_seed=SEED + 1,
    verbose=0, thread_count=-1, cat_features=[CAT], eval_metric="AUC",
    od_type="Iter", od_wait=40, use_best_model=True,
)
cat.fit(tr[FEATS], ytr, eval_set=(Xt, yt))
p_cat = cat.predict_proba(Xva)[:, 1]
tick("CatBoost 완료")

xg = xgb.XGBClassifier(
    n_estimators=1500, learning_rate=0.03, max_depth=6, min_child_weight=100, subsample=0.7,
    colsample_bytree=0.6, reg_lambda=10.0, tree_method="hist", n_jobs=-1, random_state=SEED,
    eval_metric="auc", early_stopping_rounds=40,
)
xg.fit(tr[FEATS], ytr, eval_set=[(Xt, yt)], verbose=False)


def xgb_pred(X):
    return xg.predict_proba(X, iteration_range=(0, xg.best_iteration + 1))[:, 1]


p_xgb = xgb_pred(Xva)
tick("XGBoost 완료")

Z = np.column_stack([logit(p_lgb), logit(p_cat), logit(p_xgb)])
meta = LogisticRegression(C=1.0, max_iter=200).fit(Z[is_tune], yt)
p_stack = meta.predict_proba(Z)[:, 1]

pop_lr = LogisticRegression().fit(np.log1p(tr[["song_cnt"]].to_numpy()), ytr)
p_pop_va = pop_lr.predict_proba(np.log1p(va[["song_cnt"]].to_numpy()))[:, 1]
u_va = va["user_rate_lag"].to_numpy(dtype=float)
u_fill = np.nanmean(u_va)
p_usr_va = np.where(np.isnan(u_va), u_fill, u_va)

cands = {"LightGBM_tuned": p_lgb, "CatBoost": p_cat, "XGBoost": p_xgb, "Stack3": p_stack}
res_va = table(yh, {**{k: v[is_hold] for k, v in cands.items()}, "인기도 기준선": p_pop_va[is_hold], "사용자 재청취율 기준선": p_usr_va[is_hold]})
print("\nvalid holdout 성능 (모델 선택에 쓰는 유일한 표)")
print(res_va.round(5).to_string(index=False))
print(f"(참고: v3 Stack3 valid holdout AUC {REF['v3_valid_holdout']})")

order = list(cands.keys())
sel = res_va.set_index("모델").loc[order]
best_auc = sel["AUC"].max()
chosen = next(n for n in order if sel.loc[n, "AUC"] >= best_auc - AUC_TOL and sel.loc[n, "ECE"] <= ECE_MAX)
print(f"\n선정된 모델 A: {chosen}")


def test_pred(name):
    Xte = te[FEATS]
    pl = np.mean([lgb_pred(m, Xte) for m in lgb_models], axis=0)
    if name == "LightGBM_tuned":
        return pl
    pc = cat.predict_proba(Xte)[:, 1]
    px = xgb_pred(Xte)
    if name == "CatBoost":
        return pc
    if name == "XGBoost":
        return px
    return meta.predict_proba(np.column_stack([logit(pl), logit(pc), logit(px)]))[:, 1]


pA_te = test_pred(chosen)
p_pop_te = pop_lr.predict_proba(np.log1p(te[["song_cnt"]].to_numpy()))[:, 1]
u_te = te["user_rate_lag"].to_numpy(dtype=float)
p_usr_te = np.where(np.isnan(u_te), u_fill, u_te)
res_te = table(yte, {f"모델A({chosen})": pA_te, "인기도 기준선": p_pop_te, "사용자 재청취율 기준선": p_usr_te})
print("\ntest 성능 (선정된 모델만, 선택에 사용하지 않음, 이미 열었던 test)")
print(res_te.round(5).to_string(index=False))
print(f"(참고: v3 test AUC {REF['v3_test']})")

chk = []
pA_va_h = cands[chosen][is_hold]
for lab, pb in [("인기도", p_pop_va[is_hold]), ("사용자 기준선", p_usr_va[is_hold])]:
    am, ab, d, lo, hi = boot_diff(yh, user_h, pA_va_h, pb)
    chk.append({"구간": "valid holdout", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
for lab, pb in [("인기도", p_pop_te), ("사용자 기준선", p_usr_te)]:
    am, ab, d, lo, hi = boot_diff(yte, user_te, pA_te, pb)
    chk.append({"구간": "test", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
chk = pd.DataFrame(chk)
print("\n합격선 검증 (사용자 단위 부트스트랩)")
print(chk.round(4).to_string(index=False))

out_va = va[KEYS].copy()
out_va["p_modelA_v4"] = cands[chosen]
out_va["is_tune"] = is_tune
out_va.to_parquet(f"{OUT}/pred_valid_modelA_v4.parquet", index=False)
out_te = te[KEYS].copy()
out_te["p_modelA_v4"] = pA_te
out_te["rank"] = out_te.groupby("msno")["p_modelA_v4"].rank(method="first", ascending=False)
out_te.to_parquet(f"{OUT}/pred_test_modelA_v4.parquet", index=False)
out_te[out_te["rank"] <= 10].sort_values(["msno", "rank"]).to_csv(f"{OUT}/recommend_top10_test_modelA_v4.csv", index=False)

joblib.dump({"lgb": lgb_models, "xgb": xg, "meta": meta, "features": FEATS, "chosen": chosen}, f"{OUT}/modelA_v4_models.joblib")
cat.save_model(f"{OUT}/modelA_v4_catboost.cbm")
res_va.to_csv(f"{OUT}/result_valid_holdout.csv", index=False)
res_te.to_csv(f"{OUT}/result_test.csv", index=False)
chk.to_csv(f"{OUT}/result_합격선검증.csv", index=False)
pd.DataFrame(log_rows).to_csv(f"{OUT}/result_특성그룹채택.csv", index=False)
with open(f"{OUT}/modelA_v4_설정과결과.json", "w", encoding="utf-8") as f:
    json.dump({
        "선정": chosen, "채택그룹": adopted, "기준AUC": float(auc0), "채택후AUC": float(auc_cur),
        "특성수": len(FEATS), "특성목록": FEATS, "params": PARAMS, "참고": REF,
    }, f, ensure_ascii=False, indent=2, default=float)
tick(f"저장 완료: {os.path.abspath(OUT)}")