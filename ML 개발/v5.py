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
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, roc_auc_score

warnings.filterwarnings("ignore", category=RuntimeWarning)

V4_DIR = "v4"
OUT = "v5"
SEED = 42
ALPHAS = [0.0, 1.0, 3.0]
ADOPT_GAIN = 0.001
LGB_SEEDS = [1, 2, 3]
ITER_SCALE = 1.15
N_BOOT = 300

CAT = "primary_genre_code"
KEYS = ["row_order", "msno", "song_id", "target"]
REF = {"v4_valid_holdout_LightGBM": 0.63643, "v4_test": 0.62809}

os.makedirs(OUT, exist_ok=True)
T0 = time.time()


def tick(msg):
    print(f"[{time.time() - T0:.0f}초] {msg}")


cfg = json.load(open(f"{V4_DIR}/modelA_v4_설정과결과.json", encoding="utf-8"))
FEATS, PARAMS = cfg["특성목록"], cfg["params"]

B = {n: pd.read_parquet(f"{V4_DIR}/featv4_{n}.parquet") for n in ["train_a", "train_b", "valid", "test"]}
tr = pd.concat([B["train_a"], B["train_b"]], ignore_index=True)
tr = tr[tr["user_rate_lag"].notna()].reset_index(drop=True)
va, te = B["valid"], B["test"]
yv, yte = va["target"].to_numpy(), te["target"].to_numpy()

users = va["msno"].unique()
rng = np.random.default_rng(SEED)
tune_users = set(rng.choice(users, len(users) // 2, replace=False))
is_tune = va["msno"].isin(tune_users).to_numpy()
is_hold = ~is_tune
yt, yh = yv[is_tune], yv[is_hold]
user_h, user_te = va["msno"].to_numpy()[is_hold], te["msno"].to_numpy()
Xva, Xt, Xh = va[FEATS], va.loc[is_tune, FEATS], va.loc[is_hold, FEATS]
tick(f"학습 행 {len(tr):,} | 특성 {len(FEATS)}개")


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


def weights(d, alpha):
    r = d["row_order"].to_numpy().astype(float)
    return 1 + alpha * (r - r.min()) / (r.max() - r.min())


def fit_lgb(d, w, seed, n_est=None):
    kw = dict(subsample_freq=1, n_jobs=-1, random_state=SEED + seed, verbose=-1, **PARAMS)
    y = d["target"].to_numpy()
    if n_est is None:
        m = lgb.LGBMClassifier(n_estimators=1500, **kw)
        m.fit(d[FEATS], y, sample_weight=w, eval_set=[(Xt, yt)], eval_metric="auc", categorical_feature=[CAT], callbacks=[lgb.early_stopping(40, verbose=False)])
    else:
        m = lgb.LGBMClassifier(n_estimators=n_est, **kw)
        m.fit(d[FEATS], y, sample_weight=w, categorical_feature=[CAT])
    return m


def lgb_pred(m, X, es):
    return m.predict_proba(X, num_iteration=m.best_iteration_)[:, 1] if es else m.predict_proba(X)[:, 1]


def fit_all(d, w, iters=None):
    es = iters is None
    X, y = d[FEATS], d["target"].to_numpy()
    lgbs = [fit_lgb(d, w, s, None if es else iters["lgb"]) for s in LGB_SEEDS]
    cat_kw = dict(learning_rate=0.06, depth=5, l2_leaf_reg=10, random_seed=SEED + 1, verbose=0, thread_count=-1, cat_features=[CAT])
    xgb_kw = dict(learning_rate=0.03, max_depth=6, min_child_weight=100, subsample=0.7, colsample_bytree=0.6, reg_lambda=10.0, tree_method="hist", n_jobs=-1, random_state=SEED)
    if es:
        cat = CatBoostClassifier(iterations=1500, eval_metric="AUC", od_type="Iter", od_wait=40, use_best_model=True, **cat_kw)
        cat.fit(X, y, sample_weight=w, eval_set=(Xt, yt))
        xg = xgb.XGBClassifier(n_estimators=1500, eval_metric="auc", early_stopping_rounds=40, **xgb_kw)
        xg.fit(X, y, sample_weight=w, eval_set=[(Xt, yt)], verbose=False)
        it = {"lgb": int(np.mean([m.best_iteration_ for m in lgbs])), "cat": int(cat.get_best_iteration()) + 1, "xgb": int(xg.best_iteration) + 1}
    else:
        cat = CatBoostClassifier(iterations=iters["cat"], **cat_kw)
        cat.fit(X, y, sample_weight=w)
        xg = xgb.XGBClassifier(n_estimators=iters["xgb"], **xgb_kw)
        xg.fit(X, y, sample_weight=w, verbose=False)
        it = iters
    return {"lgb": lgbs, "cat": cat, "xgb": xg, "es": es, "iters": it}


def predict_all(M, X):
    pl = np.mean([lgb_pred(m, X, M["es"]) for m in M["lgb"]], axis=0)
    pc = M["cat"].predict_proba(X)[:, 1]
    xg = M["xgb"]
    px = xg.predict_proba(X, iteration_range=(0, xg.best_iteration + 1))[:, 1] if M["es"] else xg.predict_proba(X)[:, 1]
    return pl, pc, px


auc_alpha = {}
for a in ALPHAS:
    m = fit_lgb(tr, weights(tr, a), 1)
    auc_alpha[a] = roc_auc_score(yh, lgb_pred(m, Xh, True))
    tick(f"최근 가중치 alpha={a}: valid holdout AUC {auc_alpha[a]:.5f}")
best_a = max(auc_alpha, key=auc_alpha.get)
alpha = best_a if auc_alpha[best_a] - auc_alpha[0.0] >= ADOPT_GAIN else 0.0
print(f"최근 가중치 채택: alpha={alpha} (기준 +{ADOPT_GAIN}, alpha=0 대비 {auc_alpha[best_a] - auc_alpha[0.0]:+.5f})")

med = tr["row_order"].median()
old = tr[tr["row_order"] < med].reset_index(drop=True)
m_old = fit_lgb(old, weights(old, alpha), 1)
auc_old = roc_auc_score(yh, lgb_pred(m_old, Xh, True))
auc_full = auc_alpha[alpha]
gain_recent = auc_full - auc_old
retrain = gain_recent >= ADOPT_GAIN
print(f"최근 데이터 효과 점검: 오래된 절반만 {auc_old:.5f} vs 전체 {auc_full:.5f} ({gain_recent:+.5f}) -> valid 포함 재학습 {'채택' if retrain else '미채택'}")
print("주의: 이 점검은 데이터 양 차이와 섞여 있어 참고용 근거입니다.")

M1 = fit_all(tr, weights(tr, alpha))
tick(f"valid 단계 모델 학습 완료 | 반복 수 {M1['iters']}")
pl, pc, px = predict_all(M1, Xva)
p_avg = (pl + pc + px) / 3

pop_lr = LogisticRegression().fit(np.log1p(tr[["song_cnt"]].to_numpy()), tr["target"].to_numpy())
p_pop_va = pop_lr.predict_proba(np.log1p(va[["song_cnt"]].to_numpy()))[:, 1]
u_va = va["user_rate_lag"].to_numpy(dtype=float)
u_fill = np.nanmean(u_va)
p_usr_va = np.where(np.isnan(u_va), u_fill, u_va)

res_va = table(yh, {"LightGBM": pl[is_hold], "CatBoost": pc[is_hold], "XGBoost": px[is_hold], "평균(모델 A v5)": p_avg[is_hold], "인기도 기준선": p_pop_va[is_hold], "사용자 재청취율 기준선": p_usr_va[is_hold]})
print("\nvalid holdout 성능 (train만 학습한 모델, valid 점수는 이 표만 해당)")
print(res_va.round(5).to_string(index=False))
print(f"(참고: v4 LightGBM valid holdout AUC {REF['v4_valid_holdout_LightGBM']})")

if retrain:
    full = pd.concat([tr, va], ignore_index=True)
    iters = {k: max(int(v * ITER_SCALE), 50) for k, v in M1["iters"].items()}
    MF = fit_all(full, weights(full, alpha), iters)
    tick(f"train+valid 재학습 완료 | 반복 수 {iters}")
else:
    MF = M1

Xte = te[FEATS]
tl, tc, tx = predict_all(MF, Xte)
pA_te = (tl + tc + tx) / 3
p_pop_te = pop_lr.predict_proba(np.log1p(te[["song_cnt"]].to_numpy()))[:, 1]
u_te = te["user_rate_lag"].to_numpy(dtype=float)
p_usr_te = np.where(np.isnan(u_te), u_fill, u_te)
res_te = table(yte, {f"모델A v5 ({'train+valid' if retrain else 'train'} 학습)": pA_te, "인기도 기준선": p_pop_te, "사용자 재청취율 기준선": p_usr_te})
print("\ntest 성능 (최종 모델 하나만 평가, 이미 여러 번 열었던 test라 참고용)")
print(res_te.round(5).to_string(index=False))
print(f"(참고: v4 test AUC {REF['v4_test']})")

chk = []
for lab, pb in [("인기도", p_pop_va[is_hold]), ("사용자 기준선", p_usr_va[is_hold])]:
    am, ab, d, lo, hi = boot_diff(yh, user_h, p_avg[is_hold], pb)
    chk.append({"구간": "valid holdout", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
for lab, pb in [("인기도", p_pop_te), ("사용자 기준선", p_usr_te)]:
    am, ab, d, lo, hi = boot_diff(yte, user_te, pA_te, pb)
    chk.append({"구간": "test", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
chk = pd.DataFrame(chk)
print("\n합격선 검증 (사용자 단위 부트스트랩)")
print(chk.round(4).to_string(index=False))

out_va = va[KEYS].copy()
out_va["p_modelA_v5"] = p_avg
out_va["is_tune"] = is_tune
out_va.to_parquet(f"{OUT}/pred_valid_modelA_v5.parquet", index=False)
out_te = te[KEYS].copy()
out_te["p_modelA_v5"] = pA_te
out_te["rank"] = out_te.groupby("msno")["p_modelA_v5"].rank(method="first", ascending=False)
out_te.to_parquet(f"{OUT}/pred_test_modelA_v5.parquet", index=False)
out_te[out_te["rank"] <= 10].sort_values(["msno", "rank"]).to_csv(f"{OUT}/recommend_top10_test_modelA_v5.csv", index=False)

joblib.dump({"lgb": MF["lgb"], "xgb": MF["xgb"], "iters": MF["iters"], "es": MF["es"], "features": FEATS}, f"{OUT}/modelA_v5_models.joblib")
MF["cat"].save_model(f"{OUT}/modelA_v5_catboost.cbm")
res_va.to_csv(f"{OUT}/result_valid_holdout.csv", index=False)
res_te.to_csv(f"{OUT}/result_test.csv", index=False)
chk.to_csv(f"{OUT}/result_합격선검증.csv", index=False)
with open(f"{OUT}/modelA_v5_설정과결과.json", "w", encoding="utf-8") as f:
    json.dump({
        "alpha": alpha, "alpha별_valid_AUC": {str(k): float(v) for k, v in auc_alpha.items()},
        "최근데이터_점검": {"오래된절반": float(auc_old), "전체": float(auc_full), "차이": float(gain_recent)},
        "train+valid_재학습": bool(retrain), "반복수": MF["iters"], "특성수": len(FEATS), "참고": REF,
    }, f, ensure_ascii=False, indent=2, default=float)
tick(f"저장 완료: {os.path.abspath(OUT)}")