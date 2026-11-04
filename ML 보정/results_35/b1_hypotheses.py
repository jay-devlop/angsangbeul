# 5장 근거 분석: H1~H4. data.csv(전처리본)의 row_order 순서와 이전 청취 이력만 사용한다. 관측된 상관은 인과가 아니다.
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

N_ORIG, SEED, NB = 7377418, 42, 500
rng = np.random.default_rng(SEED)
OUT = "B/results"

df = pd.read_csv("data.csv", engine="pyarrow", usecols=["row_order", "msno", "song_id", "source_system_tab", "primary_genre", "main_artist", "is_various_artist", "registration_init_time"])
df = df.sort_values("row_order", kind="stable").reset_index(drop=True)
fr = df["row_order"].to_numpy() / N_ORIG
U = pd.factorize(df["msno"])[0].astype(np.int64)
S = pd.factorize(df["song_id"])[0].astype(np.int64)
A = pd.factorize(df["main_artist"])[0].astype(np.int64)
A[df["is_various_artist"].to_numpy() == 1] = -1
pg = df["primary_genre"].astype(str)
G = pd.factorize(pg)[0].astype(np.int64)
G[(pg == "unknown").to_numpy()] = -1
tab = df["source_system_tab"].astype(str).to_numpy()
nU, NA, NG = U.max() + 1, A.max() + 1, G.max() + 1
first = np.unique(U, return_index=True)[1]
reg = pd.to_datetime(df["registration_init_time"].iloc[first]).to_numpy()
TEN = np.zeros(nU)
TEN[U[first]] = (pd.Timestamp(reg.max()) - pd.to_datetime(reg)).days.to_numpy(dtype=float)  # 가입 후 경과일(기준일은 데이터 내 최신 가입일)


def prior_cnt(K):
    out = pd.Series(K).groupby(K).cumcount().to_numpy()
    out[K < 0] = -1
    return out


KUA = np.where(A >= 0, U * NA + A, -1)
KUG = np.where(G >= 0, U * NG + G, -1)
new_a = (KUA >= 0) & (prior_cnt(KUA) == 0)
new_g = (KUG >= 0) & (prior_cnt(KUG) == 0)
unpop = prior_cnt(S) < 35
res = {}


def boot_ci(stat, n_users, nb=NB):
    v = np.array([stat(rng.integers(0, n_users, n_users)) for _ in range(nb)])
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def spear(x, y):
    return float(spearmanr(x, y)[0])


def spear_ci(x, y):
    n = len(x)
    return boot_ci(lambda ix: spear(x[ix], y[ix]), n)


# ---------- 공통: 유효 장르 청취만 모아 사용자별 n번째 청취 순번 ----------
vg = np.flatnonzero(G >= 0)
rank_f = pd.Series(np.arange(len(vg))).groupby(U[vg]).cumcount().to_numpy()
rank_b = pd.Series(np.arange(len(vg))).groupby(U[vg]).cumcount(ascending=False).to_numpy()
cnt_v = np.bincount(U[vg], minlength=nU)


def profile(sel_mask):
    idx = vg[sel_mask]
    d = pd.DataFrame({"u": U[idx], "g": G[idx]})
    c = d.groupby(["u", "g"]).size().rename("n").reset_index()
    nuniq = c.groupby("u").size()
    top = c.groupby("u")["n"].max()
    tot = c.groupby("u")["n"].sum()
    p = c["n"] / c["u"].map(tot)
    ent = (-p * np.log(p)).groupby(c["u"]).sum()
    return pd.DataFrame({"nuniq": nuniq, "top": top / tot, "ent": ent})


# ================= H1 =================
K = 50
f50 = profile(rank_f < K)
f50 = f50[cnt_v[f50.index] >= K]
ten = TEN[f50.index.to_numpy()]
h1 = {"교차_사용자수": int(len(f50))}
for m in ["nuniq", "top", "ent"]:
    x, y = ten, f50[m].to_numpy()
    h1[f"교차_spearman_{m}"] = {"rho": spear(x, y), "ci": spear_ci(x, y)}
q = pd.qcut(pd.Series(ten), 4, labels=["최근 가입(Q1)", "Q2", "Q3", "오래된 가입(Q4)"])
h1["교차_사분위"] = f50.groupby(q.to_numpy(), observed=True).agg(사용자수=("nuniq", "size"), 평균_고유장르수=("nuniq", "mean"), 평균_최다장르비중=("top", "mean"), 평균_엔트로피=("ent", "mean")).round(4).reset_index().rename(columns={"index": "가입시기"}).to_dict("records")
l50 = profile(rank_b < K)
both = f50.index.intersection(l50.index)
both = both[cnt_v[both] >= 2 * K]
dn = (l50.loc[both, "nuniq"] - f50.loc[both, "nuniq"]).to_numpy()
dt = (l50.loc[both, "top"] - f50.loc[both, "top"]).to_numpy()
de = (l50.loc[both, "ent"] - f50.loc[both, "ent"]).to_numpy()
h1["사용자내_사용자수"] = int(len(both))
for nm, v in [("고유장르수", dn), ("최다장르비중", dt), ("엔트로피", de)]:
    h1[f"사용자내_후반−초반_{nm}"] = {"평균": float(v.mean()), "ci": boot_ci(lambda ix, v=v: v[ix].mean(), len(v)), "줄어든_사용자비율": float((v < 0).mean())}
res["H1"] = h1

# ================= H2 =================
Ke = 50
e = profile((rank_f < Ke) & (fr[vg] < 0.5))
cnt_e = np.bincount(U[vg][fr[vg] < 0.5], minlength=nU)
e = e[cnt_e[e.index] >= Ke]
w_mid = (fr >= 0.5) & (fr < 0.75)
w_late = fr >= 0.75
n_early = np.bincount(U[fr < 0.5], minlength=nU)
n_mid = np.bincount(U[w_mid], minlength=nU)
n_late = np.bincount(U[w_late], minlength=nU)
ix = e.index.to_numpy()
ix = ix[n_mid[ix] >= 1]
e = e.loc[ix]
chg = np.log((n_late[ix] + 1) / (n_mid[ix] + 1))
churn = (n_late[ix] == 0).astype(float)
ctrl = np.column_stack([np.ones(len(ix)), np.log(n_mid[ix] + 1), np.log(n_early[ix] + 1)])


def resid(y):
    b = np.linalg.lstsq(ctrl, y, rcond=None)[0]
    return y - ctrl @ b


h2 = {"사용자수": int(len(ix))}
for m, lab in [("top", "최다장르비중"), ("ent", "엔트로피(낮을수록 편중)")]:
    x = e[m].to_numpy()
    h2[f"spearman_{lab}_vs_활동변화"] = {"rho": spear(x, chg), "ci": spear_ci(x, chg)}
    h2[f"통제후_spearman_{lab}"] = {"rho": spear(resid(x), resid(chg)), "ci": boot_ci(lambda i, x=x: spear(resid(x)[i], resid(chg)[i]), len(x), 200)}
qq = pd.qcut(e["top"], 4, labels=["Q1 분산", "Q2", "Q3", "Q4 편중"], duplicates="drop")
h2["편중도_사분위"] = pd.DataFrame({"q": qq.to_numpy(), "이탈": churn, "활동변화": chg}).groupby("q", observed=True).agg(사용자수=("이탈", "size"), 이탈률=("이탈", "mean"), 평균_활동변화=("활동변화", "mean")).round(4).reset_index().to_dict("records")
res["H2"] = h2

# ================= H3 =================
grp = np.full(len(U), -1)
grp[np.isin(tab, ["discover", "radio", "explore"])] = 0
grp[tab == "search"] = 1
grp[tab == "my library"] = 2
m = (fr >= 0.2) & (grp >= 0)
GN = ["추천·큐레이션 경로(discover·radio·explore)", "직접 탐색(search)", "내 라이브러리(my library)"]
flags = {"새 아티스트": new_a, "취향 밖 장르": new_g, "비인기곡": unpop}
size = np.zeros((3, nU))
fl = {k: np.zeros((3, nU)) for k in flags}
for g in range(3):
    mg = m & (grp == g)
    size[g] = np.bincount(U[mg], minlength=nU)
    for k, v in flags.items():
        fl[k][g] = np.bincount(U[mg & v], minlength=nU)
h3 = {"그룹": GN, "풀링": {}, "사용자내_추천−직접탐색": {}}
for k in flags:
    sh = [float(fl[k][g].sum() / size[g].sum()) for g in range(3)]
    ci = []
    for g in range(3):
        ci.append(boot_ci(lambda ix, g=g, k=k: fl[k][g][ix].sum() / size[g][ix].sum(), nU, 300))
    h3["풀링"][k] = {"비율": sh, "ci": ci}
    ok = (size[0] >= 10) & (size[1] >= 10)
    d = fl[k][0][ok] / size[0][ok] - fl[k][1][ok] / size[1][ok]
    h3["사용자내_추천−직접탐색"][k] = {"사용자수": int(ok.sum()), "평균차": float(d.mean()), "ci": boot_ci(lambda ix, d=d: d[ix].mean(), len(d)), "추천이_더_낮은_사용자비율": float((d < 0).mean())}
h3["청취수"] = [int(size[g].sum()) for g in range(3)]
res["H3"] = h3

# ================= H4 =================
n_hist = np.bincount(U[fr < 0.4], minlength=nU)
w_b = (fr >= 0.4) & (fr < 0.6)
n_b = np.bincount(U[w_b], minlength=nU)
tried = np.bincount(U[w_b & new_g], minlength=nU) >= 1
n_a = np.bincount(U[fr >= 0.6], minlength=nU)
n_a2 = np.bincount(U[fr >= 0.8], minlength=nU)
pop = np.flatnonzero((n_hist >= 50) & (n_b >= 1))
t, nb_, nh_ = tried[pop], n_b[pop], n_hist[pop]
ret = (n_a2[pop] > 0).astype(float)
ratio = np.log((n_a[pop] / 2 + 1) / (nb_ + 1))
sb = pd.qcut(nb_, 5, labels=False, duplicates="drop")
sh = pd.qcut(nh_, 5, labels=False, duplicates="drop")
strata = (sb * 10 + sh).astype(int)
ns = strata.max() + 1


def att(ix, y):
    s, tt, yy = strata[ix], t[ix], y[ix]
    ct = np.bincount(s[tt], minlength=ns)
    cc = np.bincount(s[~tt], minlength=ns)
    mt = np.bincount(s[tt], weights=yy[tt], minlength=ns) / np.maximum(ct, 1)
    mc = np.bincount(s[~tt], weights=yy[~tt], minlength=ns) / np.maximum(cc, 1)
    ok = (ct > 0) & (cc > 0)
    return float(((mt - mc)[ok] * ct[ok]).sum() / ct[ok].sum())


allix = np.arange(len(pop))
h4 = {"사용자수": int(len(pop)), "새_장르_시도_사용자수": int(t.sum()), "시도_사용자비율": float(t.mean())}
for nm, y in [("후기_활동유지율(80~100%구간 청취有)", ret), ("활동변화(log 비율)", ratio)]:
    raw = float(y[t].mean() - y[~t].mean())
    h4[nm] = {"시도군": float(y[t].mean()), "비시도군": float(y[~t].mean()), "단순차": raw,
              "통제후_차": att(allix, y), "통제후_ci": boot_ci(lambda ix, y=y: att(ix, y), len(pop), 300)}
res["H4"] = h4

json.dump(res, open(f"{OUT}/hypotheses.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=float)
print(json.dumps(res, ensure_ascii=False, indent=1, default=float)[:6000])
