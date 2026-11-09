import json
import os
import time
import warnings

import joblib
import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from catboost import CatBoostClassifier
from scipy import sparse
from sklearn.decomposition import TruncatedSVD
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score

warnings.filterwarnings("ignore", category=RuntimeWarning)
optuna.logging.set_verbosity(optuna.logging.WARNING)

DATA_PATH = "data.csv"
SRC_DIR = "v2"
OUT = "v3"
N_ORIG = 7377418
BLOCKS = {
    "train_a": (0.2, 0.4),
    "train_b": (0.4, 0.6),
    "valid": (0.6, 0.8),
    "test": (0.8, 1.0),
}
SEED = 42
SVD_COMP = 24
SVD_ADOPT_GAIN = 0.001
N_TRIALS = 12
LGB_SEEDS = [1, 2, 3]
AUC_TOL = 0.0003
ECE_MAX = 0.01
USE_MEMBERSHIP_DAYS = True
USE_SOURCE = False
N_BOOT = 300

CAT = "primary_genre_code"
KEYS = ["row_order", "msno", "song_id", "target"]
SRC_COLS = ["src_tab", "src_screen", "src_type"]
SVD_COLS = ["svd_song_dot", "svd_song_cos", "svd_artist_dot", "svd_artist_cos"]
REF = {"v1_valid_g0": 0.66515, "v1_test_g0": 0.6528, "v1_test_g30": 0.6199, "v2_valid": 0.63098, "v2_test": 0.62308}

os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def tick(msg):
    print(f"[{time.time() - T0:.0f}초] {msg}")


df = pd.read_csv(DATA_PATH, engine="pyarrow", usecols=["row_order", "msno", "song_id", "main_artist", "is_various_artist"])
df = df.sort_values("row_order", kind="stable").reset_index(drop=True)
ro = df["row_order"].to_numpy().astype(np.int64)
U = pd.factorize(df["msno"])[0].astype(np.int64)
S = pd.factorize(df["song_id"])[0].astype(np.int64)
A = pd.factorize(df["main_artist"])[0].astype(np.int64)
A[df["is_various_artist"].to_numpy() == 1] = -1
nU, NS, NA = int(U.max()) + 1, int(S.max()) + 1, int(A.max()) + 1


def cut(frac):
    return int(np.searchsorted(ro, frac * N_ORIG, side="left"))


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
        qi0 = np.where(ok, qi, 0)
        a, b = uv[qu], iv[qi0]
        dot = np.einsum("ij,ij->i", a, b)
        cos = dot / np.maximum(np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1), 1e-9)
        dot[~ok] = np.nan
        cos[~ok] = np.nan
        out[f"svd_{tag}_dot"] = dot.astype(np.float32)
        out[f"svd_{tag}_cos"] = cos.astype(np.float32)
    return out


B = {}
for name, (lo, hi) in BLOCKS.items():
    f = pd.read_parquet(f"{SRC_DIR}/featv2lag_{name}.parquet")
    s0, s1 = cut(lo), cut(hi)
    assert len(f) == s1 - s0 and (f["row_order"].to_numpy() == ro[s0:s1]).all()
    for k, v in svd_feats(s0, s1).items():
        f[k] = v
    B[name] = f
    f.to_parquet(f"{OUT}/featv3_{name}.parquet", index=False)
    tick(f"{name} 취향 유사도 특성 추가 완료")

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

FEATS_BASE = [c for c in va.columns if c not in KEYS and c not in SRC_COLS and c not in SVD_COLS]
if not USE_MEMBERSHIP_DAYS:
    FEATS_BASE.remove("membership_days")
CATS = [CAT] + (SRC_COLS if USE_SOURCE else [])
if USE_SOURCE:
    FEATS_BASE = FEATS_BASE + SRC_COLS


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


DEFAULT_PARAMS = dict(learning_rate=0.03, num_leaves=31, max_depth=6, min_child_samples=500, subsample=0.7, colsample_bytree=0.6, reg_lambda=10.0)


def fit_lgb(feats, params, seed):
    m = lgb.LGBMClassifier(n_estimators=1500, subsample_freq=1, n_jobs=-1, random_state=SEED + seed, verbose=-1, **params)
    m.fit(
        tr[feats], ytr, eval_set=[(va.loc[is_tune, feats], yt)], eval_metric="auc",
        categorical_feature=[c for c in CATS if c in feats], callbacks=[lgb.early_stopping(40, verbose=False)],
    )
    return m


def lgb_pred(m, X):
    return m.predict_proba(X, num_iteration=m.best_iteration_)[:, 1]


m0 = fit_lgb(FEATS_BASE, DEFAULT_PARAMS, 1)
auc_base = roc_auc_score(yh, lgb_pred(m0, va.loc[is_hold, FEATS_BASE]))
feats_svd = FEATS_BASE + SVD_COLS
m1 = fit_lgb(feats_svd, DEFAULT_PARAMS, 1)
auc_svd = roc_auc_score(yh, lgb_pred(m1, va.loc[is_hold, feats_svd]))
use_svd = (auc_svd - auc_base) >= SVD_ADOPT_GAIN
FEATS = feats_svd if use_svd else FEATS_BASE
tick(f"취향 유사도 특성 비교 valid holdout AUC {auc_base:.5f} -> {auc_svd:.5f} ({auc_svd - auc_base:+.5f}), 채택 기준 +{SVD_ADOPT_GAIN}: {'채택' if use_svd else '미채택'}")
print("모델 입력 특성 수:", len(FEATS))


def objective(trial):
    params = dict(
        learning_rate=trial.suggest_float("learning_rate", 0.02, 0.1, log=True),
        num_leaves=trial.suggest_int("num_leaves", 15, 127),
        max_depth=trial.suggest_int("max_depth", 4, 10),
        min_child_samples=trial.suggest_int("min_child_samples", 100, 1500),
        subsample=trial.suggest_float("subsample", 0.6, 1.0),
        colsample_bytree=trial.suggest_float("colsample_bytree", 0.4, 1.0),
        reg_lambda=trial.suggest_float("reg_lambda", 1.0, 50.0, log=True),
    )
    m = fit_lgb(FEATS, params, 1)
    return m.best_score_["valid_0"]["auc"]


study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=SEED))
study.enqueue_trial(DEFAULT_PARAMS)
study.optimize(objective, n_trials=N_TRIALS)
best_params = study.best_params
tick(f"Optuna 완료 tune AUC {study.best_value:.5f} | {best_params}")

lgb_models = [fit_lgb(FEATS, best_params, s) for s in LGB_SEEDS]
Xva, Xt = va[FEATS], va.loc[is_tune, FEATS]
p_lgb = np.mean([lgb_pred(m, Xva) for m in lgb_models], axis=0)
tick(f"LightGBM 튜닝판 시드 {len(LGB_SEEDS)}개 완료")

cat = CatBoostClassifier(
    iterations=1500, learning_rate=0.06, depth=5, l2_leaf_reg=10, random_seed=SEED + 1,
    verbose=0, thread_count=-1, cat_features=[c for c in CATS if c in FEATS], eval_metric="AUC",
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
print(f"(참고: v2 모델 A valid holdout AUC {REF['v2_valid']})")

order = list(cands.keys())
sel = res_va.set_index("모델").loc[order]
best_auc = sel["AUC"].max()
chosen = next(n for n in order if sel.loc[n, "AUC"] >= best_auc - AUC_TOL and sel.loc[n, "ECE"] <= ECE_MAX)
print(f"\n선정 규칙: 최고 holdout AUC와 {AUC_TOL} 이내, ECE {ECE_MAX} 이하 중 앞 순서(단순한 쪽) 우선")
print("선정된 모델 A:", chosen)


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
print("\ntest 성능 (선정된 모델만, 선택에 사용하지 않음, v1에서 한 번 열었던 test)")
print(res_te.round(5).to_string(index=False))
print(f"(참고: v2 test AUC {REF['v2_test']}, v1 test g0 {REF['v1_test_g0']}, g30 {REF['v1_test_g30']})")

chk = []
for label, pm, pb, y_, u_ in [
    ("valid holdout", p_stack if chosen == "Stack3" else cands[chosen], None, yh, user_h),
]:
    pass
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
out_va["p_modelA_v3"] = cands[chosen]
out_va["is_tune"] = is_tune
out_va.to_parquet(f"{OUT}/pred_valid_modelA_v3.parquet", index=False)
out_te = te[KEYS].copy()
out_te["p_modelA_v3"] = pA_te
out_te["rank"] = out_te.groupby("msno")["p_modelA_v3"].rank(method="first", ascending=False)
out_te.to_parquet(f"{OUT}/pred_test_modelA_v3.parquet", index=False)
out_te[out_te["rank"] <= 10].sort_values(["msno", "rank"]).to_csv(f"{OUT}/recommend_top10_test_modelA_v3.csv", index=False)

joblib.dump({"lgb": lgb_models, "xgb": xg, "meta": meta, "features": FEATS, "chosen": chosen}, f"{OUT}/modelA_v3_models.joblib")
cat.save_model(f"{OUT}/modelA_v3_catboost.cbm")
res_va.to_csv(f"{OUT}/result_valid_holdout.csv", index=False)
res_te.to_csv(f"{OUT}/result_test.csv", index=False)
chk.to_csv(f"{OUT}/result_합격선검증.csv", index=False)
with open(f"{OUT}/modelA_v3_설정과결과.json", "w", encoding="utf-8") as f:
    json.dump({
        "선정": chosen, "취향유사도_채택": bool(use_svd), "취향유사도_valid_AUC": [float(auc_base), float(auc_svd)],
        "optuna_best_params": best_params, "optuna_tune_AUC": float(study.best_value),
        "특성수": len(FEATS), "특성목록": FEATS, "USE_SOURCE": USE_SOURCE, "참고": REF,
    }, f, ensure_ascii=False, indent=2, default=float)
tick(f"저장 완료: {os.path.abspath(OUT)}")