# v8: v7 + 경로 교차 지연 재청취율, 최근 구간 지연 재청취율, 초기 구간 학습 포함 점검, LightGBM Optuna 튜닝.
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
V7_DIR = "v7"
OUT = "v8"
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
W_LAG = 500000
ADOPT_GAIN = 0.001
N_TRIALS = 10
LGB_SEEDS = [1, 2, 3]
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
REF = {"v6_valid_holdout": 0.67484, "v6_test": 0.67331, "v7_valid_holdout": 0.70845}
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
del df
nU, NS, NA, NG = int(U.max()) + 1, int(S.max()) + 1, int(A.max()) + 1, int(G.max()) + 1
tick(f"데이터 로드 {N:,}행")


def cut(frac):
    return int(np.searchsorted(ro, frac * N_ORIG, side="left"))


def prior_cnt(K):
    out = pd.Series(K).groupby(K).cumcount().to_numpy().astype(np.float32)
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
# v8 신규: 경로 교차와 최근 구간(정답 확정 구간 중 최근 W_LAG행)
CROSS = {}
for nm, K in {
    "user_srcscreen_type": KUC * NT + T, "song_srcscreen": S * NC + C, "song_srctab": S * NR + R,
    "artist_srcscreen": np.where(A >= 0, A * NC + C, -1), "genre_srctype": np.where(G >= 0, G * NT + T, -1),
    "user_artist_srctype": np.where(KUA >= 0, KUA * NT + T, -1), "user_genre_srctype": np.where(KUG >= 0, KUG * NT + T, -1),
}.items():
    CROSS[f"{nm}_rate_lag"] = lagged_rate(K, K)
for nm, K in {"user": U, "user_srctype": KUT, "song": S, "srctype_screen": KTC}.items():
    CROSS[f"{nm}_rate_lag_recent"] = lagged_rate(K, K, W_LAG)
F.update(CROSS)
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
NEW = list(F)
CROSS_COLS = list(CROSS)
V7_NEW = [c for c in NEW if c not in CROSS_COLS]

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
GROUPS = {**cfg6["특성그룹"], "노출경로": SRC_COLS + V7_NEW, "경로교차·최근(v8)": CROSS_COLS}
FEATS = FEATS7 + CROSS_COLS
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


def fit_all(d, iters=None):
    es = iters is None
    X, y = d[FEATS], d["target"].to_numpy()
    Xt = va.loc[is_tune, FEATS]
    lgbs = [fit_lgb(d, s, None if es else iters["lgb"]) for s in LGB_SEEDS]
    tick(f"LightGBM {len(LGB_SEEDS)}개 완료")
    cat_kw = dict(learning_rate=0.1, depth=7, l2_leaf_reg=10, max_ctr_complexity=1, random_seed=SEED + 1, verbose=0, thread_count=-1, cat_features=CATS)
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


def hold_auc(d, feats, params=None):
    m = fit_lgb(d, 1, feats=feats, params=params)
    return roc_auc_score(yh, lgb_pred(m, va.loc[is_hold, feats])), m


auc_v7, _ = hold_auc(tr, FEATS7)
auc_cross, _ = hold_auc(tr, FEATS7 + CROSS_COLS)
use_cross = auc_cross - auc_v7 >= ADOPT_GAIN
FEATS = FEATS7 + CROSS_COLS if use_cross else FEATS7
tick(f"경로교차·최근 특성: holdout {auc_v7:.5f} -> {auc_cross:.5f} ({auc_cross - auc_v7:+.5f}) {'채택' if use_cross else '미채택'}")

auc_early, _ = hold_auc(tr_all, FEATS)
auc_base = auc_cross if use_cross else auc_v7
use_early = auc_early - auc_base >= ADOPT_GAIN
if use_early:
    tr = tr_all
    ytr = tr["target"].to_numpy()
tick(f"초기 구간(20~43%) 포함: holdout {auc_base:.5f} -> {auc_early:.5f} ({auc_early - auc_base:+.5f}) {'채택' if use_early else '미채택'} | 학습 행 {len(tr):,}")


def objective(trial):
    params = dict(
        learning_rate=trial.suggest_float("learning_rate", 0.02, 0.1, log=True),
        num_leaves=trial.suggest_int("num_leaves", 31, 255, log=True),
        max_depth=trial.suggest_int("max_depth", 6, 12),
        min_child_samples=trial.suggest_int("min_child_samples", 100, 2000, log=True),
        subsample=trial.suggest_float("subsample", 0.5, 1.0),
        colsample_bytree=trial.suggest_float("colsample_bytree", 0.3, 0.9),
        reg_lambda=trial.suggest_float("reg_lambda", 1.0, 100.0, log=True),
    )
    m = fit_lgb(tr, 1, params=params)
    return m.best_score_["valid_0"]["auc"]


study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=SEED))
study.enqueue_trial(PARAMS)
study.optimize(objective, n_trials=N_TRIALS)
PARAMS = study.best_params
tick(f"Optuna 완료 tune AUC {study.best_value:.5f} | {PARAMS}")

M1 = fit_all(tr)
tick(f"valid 단계 학습 완료 | 반복 수 {M1['iters']}")
pl, pc, px = predict_all(M1, va[FEATS])
p_avg = (pl + pc + px) / 3
Z = np.column_stack([logit(pl), logit(pc), logit(px)])
meta = LogisticRegression(C=1.0, max_iter=200).fit(Z[is_tune], yt)
p_stack = meta.predict_proba(Z)[:, 1]
print("Stack3 가중치:", dict(zip(["LGB", "Cat", "XGB"], meta.coef_[0].round(3))), "절편", round(float(meta.intercept_[0]), 3))

imp = pd.Series(np.mean([m.booster_.feature_importance("gain") for m in M1["lgb"]], axis=0), index=FEATS)
grp_imp = {g: float(imp[[x for x in c if x in imp.index]].sum() / imp.sum()) for g, c in GROUPS.items()}
print("\n특성 그룹별 gain 비중:", {k: round(v, 3) for k, v in grp_imp.items()})
print("상위 15개 특성:\n" + (imp / imp.sum()).sort_values(ascending=False).head(15).round(4).to_string())

pop_lr = LogisticRegression().fit(np.log1p(tr[["s_cnt_now"]].to_numpy()), ytr)
p_pop_va = pop_lr.predict_proba(np.log1p(va[["s_cnt_now"]].to_numpy()))[:, 1]
u_va = va["user_rate_lag"].to_numpy(dtype=float)
u_fill = np.nanmean(u_va)
p_usr_va = np.where(np.isnan(u_va), u_fill, u_va)
p_v6_va = pd.read_parquet(f"{V6_DIR}/pred_valid_modelA_v6.parquet")["p_modelA_v6"].to_numpy()
p_v7_va = pd.read_parquet(f"{V7_DIR}/pred_valid_modelA_v7.parquet")["p_modelA_v7"].to_numpy()

cands = {"LightGBM": pl, "CatBoost": pc, "XGBoost": px, "평균3": p_avg, "Stack3": p_stack}
res_va = table(yh, {**{k: v[is_hold] for k, v in cands.items()}, "v7 모델 A": p_v7_va[is_hold], "v6 모델 A (source 미사용)": p_v6_va[is_hold], "인기도 기준선": p_pop_va[is_hold], "사용자 재청취율 기준선": p_usr_va[is_hold]})
print("\nvalid holdout 성능 (모델 선택에 쓰는 유일한 표)")
print(res_va.round(5).to_string(index=False))

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
p_v6_te = pd.read_parquet(f"{V6_DIR}/pred_test_modelA_v6.parquet")["p_modelA_v6"].to_numpy()
p_v7_te = pd.read_parquet(f"{V7_DIR}/pred_test_modelA_v7.parquet")["p_modelA_v7"].to_numpy()
res_te = table(yte, {f"모델A v8 ({chosen}, train+valid 학습)": pA_te, "v7 모델 A": p_v7_te, "v6 모델 A (source 미사용)": p_v6_te, "인기도 기준선": p_pop_te, "사용자 재청취율 기준선": p_usr_te})
print("\ntest 성능 (최종 모델 하나만 평가, 이미 여러 번 열었던 test라 참고용)")
print(res_te.round(5).to_string(index=False))
auc_te = float(res_te["AUC"].iloc[0])
print(f"목표 {TARGET_AUC}: {'달성' if auc_te >= TARGET_AUC else f'미달 ({auc_te - TARGET_AUC:+.4f})'}")

chk = []
for lab, pb in [("인기도", p_pop_va[is_hold]), ("사용자 기준선", p_usr_va[is_hold]), ("v7 모델 A", p_v7_va[is_hold]), ("v6 모델 A", p_v6_va[is_hold])]:
    am, ab, d, lo, hi = boot_diff(yh, user_h, cands[chosen][is_hold], pb)
    chk.append({"구간": "valid holdout", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
for lab, pb in [("인기도", p_pop_te), ("사용자 기준선", p_usr_te), ("v7 모델 A", p_v7_te), ("v6 모델 A", p_v6_te)]:
    am, ab, d, lo, hi = boot_diff(yte, user_te, pA_te, pb)
    chk.append({"구간": "test", "비교": lab, "AUC차이": d, "CI하한": lo, "CI상한": hi, "합격": bool(d > 0 and lo > 0)})
chk = pd.DataFrame(chk)
print("\n합격선 검증 (사용자 단위 부트스트랩)")
print(chk.round(4).to_string(index=False))

out_va = va[KEYS].copy()
out_va["p_modelA_v8"] = cands[chosen]
out_va["is_tune"] = is_tune
out_va.to_parquet(f"{OUT}/pred_valid_modelA_v8.parquet", index=False)
out_te = te[KEYS].copy()
out_te["p_modelA_v8"] = pA_te
out_te["rank"] = out_te.groupby("msno")["p_modelA_v8"].rank(method="first", ascending=False)
out_te.to_parquet(f"{OUT}/pred_test_modelA_v8.parquet", index=False)
top10 = out_te[out_te["rank"] <= 10].sort_values(["msno", "rank"])
top10.to_csv(f"{OUT}/recommend_top10_test_modelA_v8.csv", index=False)
print(f"\nTop-10 재청취율 {top10['target'].mean():.4f} vs test 전체 {yte.mean():.4f}")

joblib.dump({"lgb": MF["lgb"], "xgb": MF["xgb"], "meta": meta, "iters": MF["iters"], "features": FEATS, "chosen": chosen}, f"{OUT}/modelA_v8_models.joblib")
MF["cat"].save_model(f"{OUT}/modelA_v8_catboost.cbm")
res_va.to_csv(f"{OUT}/result_valid_holdout.csv", index=False)
res_te.to_csv(f"{OUT}/result_test.csv", index=False)
chk.to_csv(f"{OUT}/result_합격선검증.csv", index=False)
(imp / imp.sum()).sort_values(ascending=False).to_csv(f"{OUT}/result_특성중요도.csv", header=["gain비중"])
with open(f"{OUT}/modelA_v8_설정과결과.json", "w", encoding="utf-8") as f:
    json.dump({
        "source_사용": True, "선정": chosen, "경로교차_채택": bool(use_cross), "초기구간_채택": bool(use_early),
        "점검_holdout_AUC": {"v7특성": float(auc_v7), "교차추가": float(auc_cross), "초기구간포함": float(auc_early)}, "optuna_tune_AUC": float(study.best_value), "test_AUC": auc_te, "목표AUC": TARGET_AUC,
        "params": PARAMS, "반복수": MF["iters"], "stack3_가중치": meta.coef_[0].tolist(), "stack3_절편": float(meta.intercept_[0]),
        "특성수": len(FEATS), "특성그룹": GROUPS, "그룹별_gain비중": grp_imp, "참고": REF,
    }, f, ensure_ascii=False, indent=2, default=float)
tick(f"저장 완료: {os.path.abspath(OUT)}")
