# 6~8장: 모델 A(v11) 구간별 검증, B1·B2 보정, 정책 1~3 비교.
# 아래 사전 설정은 결과를 보기 전에 고정했다. 보정 방식·강도는 검증 구간(valid holdout)에서만 고르고, test에서는 바꾸지 않는다.
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

SEED, NB, OUT = 42, 1000, "B/results"
TOPK, MIN_CAND, POP_CUT, MIN_LAG = 10, 20, 35, 20
# 2차 실행(격자 확장): 1차 실행에서 최적해가 격자 끝(λ=0.20, k=3)에 걸려 손실 한도가 제약으로 작동하지 않았다. 검증 구간 결과만 보고 격자를 넓혔다.
LAMBDAS = [0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]   # B1 인기도 패널티 강도 후보
B2_OPTS = [(0, 0.0)] + [(k, t) for k in (1, 2, 3, 4, 5) for t in (0.30, 0.40, 0.50)]   # B2 (교체 곡 수, 최소 예측 확률) 후보
SETTINGS = [(l, k, t) for l in LAMBDAS for (k, t) in B2_OPTS]
LOSS_LIMITS, MAIN_L = [0.01, 0.02, 0.03, 0.05], 0.02              # 정확도(Top-10 재청취율) 손실 허용 한도 후보와 주 한도(절대값)
PREREG = {"1차_사전격자": {"B1_lambda": [0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20], "B2_k": [1, 2, 3]}, "격자확장_사유": "1차 실행에서 최적해가 격자 끝에 걸려 손실 한도가 제약으로 작동하지 않음(검증 구간 기준)",
          "TOPK": TOPK, "MIN_CAND": MIN_CAND, "비인기곡_기준": f"곡 누적 청취 수 < {POP_CUT}", "B1_lambda": LAMBDAS, "B2_(k,tau)": B2_OPTS[1:],
          "손실한도_후보": LOSS_LIMITS, "주_손실한도": MAIN_L, "선정원칙": "한도 이내에서 통합 유효 발견@10 최대", "유형_판단유보_기준(정답 확정 청취 수)": MIN_LAG}
rng = np.random.default_rng(SEED)
COLS = ["row_order", "msno", "target", "s_cnt_now", "is_new_artist", "is_various_artist", "is_new_genre", "primary_genre_code",
        "user_lag_n", "user_newartist_rate_lag", "user_ootgenre_rate_lag", "user_rate_lag"]
MET = ["prec", "n_unpop", "n_newart", "n_newgen", "n_D", "e_unpop", "e_newart", "e_newgen", "e_D", "genres"]


def load(blk):
    f = pd.read_parquet(f"A/v12/featv12_{blk}.parquet", columns=COLS)
    pc = ["row_order", "p_modelA_v11"] + (["is_tune"] if blk == "valid" else [])
    a = pd.read_parquet(f"A/v11/pred_{blk}_modelA_v11.parquet", columns=pc)
    assert (f["row_order"].to_numpy() == a["row_order"].to_numpy()).all()
    f["p"] = a["p_modelA_v11"].to_numpy()
    if blk == "valid":
        f["is_tune"] = a["is_tune"].to_numpy()
    f["unpop"] = f["s_cnt_now"] < POP_CUT
    f["newart"] = (f["is_new_artist"] == 1) & (f["is_various_artist"] == 0)
    f["newgen"] = f["is_new_genre"] == 1
    return f


valid_all, test_all = load("valid"), load("test")
REF = np.sort(np.log1p(valid_all["s_cnt_now"].to_numpy()))          # 인기도 백분위 기준: 검증 구간 분포


class Block:
    def __init__(self, d, z_cut=None):
        cnt = d.groupby("msno")["row_order"].transform("size")
        d = d[cnt >= MIN_CAND].reset_index(drop=True)
        self.uid, self.users = pd.factorize(d["msno"])
        self.nU = len(self.users)
        self.cnt = np.bincount(self.uid)
        self.start = np.concatenate([[0], np.cumsum(self.cnt)[:-1]])
        self.p, self.y = d["p"].to_numpy(), d["target"].to_numpy().astype(float)
        self.pct = np.searchsorted(REF, np.log1p(d["s_cnt_now"].to_numpy())) / len(REF)
        self.unpop, self.newart, self.newgen = d["unpop"].to_numpy(), d["newart"].to_numpy(), d["newgen"].to_numpy()
        self.D = self.unpop | self.newart | self.newgen
        self.genre = d["primary_genre_code"].to_numpy().astype(np.int64)
        fi = np.unique(self.uid, return_index=True)[1]
        u = d.iloc[fi]
        self.lag_n = u["user_lag_n"].to_numpy()
        self.a = ((u["user_newartist_rate_lag"] + u["user_ootgenre_rate_lag"]) / 2).to_numpy()                    # 절대형: 새 아티스트·취향 밖 장르 재청취율
        self.z = ((u["user_newartist_rate_lag"] + u["user_ootgenre_rate_lag"]) / 2 - u["user_rate_lag"]).to_numpy()   # 상대형: 자기 평균 대비
        self.d = d

    def set_types(self, kind, cut):
        t = np.where((self.z if kind == "z" else self.a) >= cut, 0, 1)
        t[self.lag_n < MIN_LAG] = 2
        self.typ = t

    def select(self, lam, k, tau):
        score = self.p - lam * self.pct
        uid = self.uid

        def pos_of(sc, ids=None, u=None):
            u = uid if u is None else u
            o = np.lexsort((-sc, u))
            c = np.bincount(u, minlength=self.nU)
            s0 = np.concatenate([[0], np.cumsum(c)[:-1]])
            pos = np.empty(len(o), int)
            pos[o] = np.arange(len(o)) - s0[u[o]]
            return pos

        if k == 0:
            return pos_of(score) < TOPK
        idx2 = np.flatnonzero(self.newgen & (self.p >= tau))
        forced = np.zeros(len(score), bool)
        if len(idx2):
            p2 = pos_of(score[idx2], u=uid[idx2])
            forced[idx2[p2 < k]] = True
        nf = np.bincount(uid[forced], minlength=self.nU)
        sc3 = np.where(forced, -1e9, score)
        return forced | ((pos_of(sc3) < (TOPK - nf[uid])) & ~forced)

    def metrics(self, sel):
        u, y = self.uid[sel], self.y[sel]
        bc = lambda m, w=None: np.bincount(u[m], weights=None if w is None else w[m], minlength=self.nU).astype(float)
        un, na, ng, dd = self.unpop[sel], self.newart[sel], self.newgen[sel], self.D[sel]
        ones = y == 1
        g = self.genre[sel]
        key = np.unique(u[g > 0] * 100000 + g[g > 0])
        M = np.column_stack([bc(np.ones(len(u), bool), y) / TOPK, bc(un), bc(na), bc(ng), bc(dd), bc(un & ones), bc(na & ones), bc(ng & ones), bc(dd & ones),
                             np.bincount(key // 100000, minlength=self.nU)])
        return M

    def grid(self):
        return np.stack([self.metrics(self.select(*s)) for s in SETTINGS])    # (설정, 사용자, 지표)


def boot_mean(Dm, nb=NB):
    n = len(Dm)
    out = np.empty((nb, Dm.shape[1]))
    for i in range(nb):
        out[i] = Dm[rng.integers(0, n, n)].mean(0)
    return np.percentile(out, [2.5, 97.5], axis=0)


print("검증/평가 블록 준비", flush=True)
VH = Block(valid_all[~valid_all["is_tune"]])
TE = Block(test_all)
# 사용자 유형: 이전 청취 이력만으로 정의. 기준값은 검증 구간(전체 사용자)의 중앙값
VA_full = Block(valid_all)
CUTS = {k: float(np.median((VA_full.z if k == "z" else VA_full.a)[VA_full.lag_n >= MIN_LAG])) for k in ("z", "a")}
TYPE_NAMES = ["탐색 친화형", "익숙함 선호형", "판단 유보형"]
res = {"사전설정": PREREG, "유형_기준값": CUTS, "사용자수": {"valid_holdout": int(VH.nU), "test": int(TE.nU)}}


def type_validity(B):
    out = {}
    for i, n in enumerate(TYPE_NAMES):
        m = (B.typ[B.uid] == i)
        r = {"사용자수": int((B.typ == i).sum()), "행수": int(m.sum()), "전체 재청취율": float(B.y[m].mean())}
        for nm, f in [("새 아티스트", B.newart), ("취향 밖 장르", B.newgen), ("비인기곡", B.unpop)]:
            r[f"{nm} 재청취율"] = float(B.y[m & f].mean())
            r[f"{nm} 비중"] = float((m & f).sum() / m.sum())
        out[n] = r
    c = {}
    for nm, f in [("새 아티스트", B.newart), ("취향 밖 장르", B.newgen), ("비인기곡", B.unpop)]:
        num = np.bincount(B.uid[f], weights=B.y[f], minlength=B.nU)
        den = np.bincount(B.uid[f], minlength=B.nU).astype(float)
        a, b = (B.typ == 0), (B.typ == 1)
        st = lambda ix: num[ix][a[ix]].sum() / den[ix][a[ix]].sum() - num[ix][b[ix]].sum() / den[ix][b[ix]].sum()
        v = np.array([st(rng.integers(0, B.nU, B.nU)) for _ in range(300)])
        c[nm] = {"차이": float(st(np.arange(B.nU))), "ci": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]}
    out["탐색−익숙 재청취율 차이"] = c
    return out


# 유형 정의 후보 두 가지를 검증 구간에서만 평가해 채택 정의를 정한다.
# 채택 규칙: 검증 구간에서 '탐색 친화형'의 새 아티스트·취향 밖 장르 재청취율이 '익숙함 선호형'보다 높고 95% 신뢰구간 하한이 0보다 큰 정의
res["유형_유효성"] = {}
passed = {}
for kind in ("z", "a"):
    for b in (VH, TE):
        b.set_types(kind, CUTS[kind])
    vv, tt = type_validity(VH), type_validity(TE)
    cd = vv["탐색−익숙 재청취율 차이"]
    passed[kind] = bool(cd["새 아티스트"]["ci"][0] > 0 and cd["취향 밖 장르"]["ci"][0] > 0)
    res["유형_유효성"][kind] = {"valid_holdout": vv, "test": tt, "검증구간_통과": passed[kind]}
ADOPT = "z" if (passed["z"] and not passed["a"]) else "a"
res["유형_채택"] = {"정의": ADOPT, "통과여부": passed}
for b in (VH, TE):
    b.set_types(ADOPT, CUTS[ADOPT])
res["유형_분포"] = {n: {"valid_holdout": int((VH.typ == i).sum()), "test": int((TE.typ == i).sum())} for i, n in enumerate(TYPE_NAMES)}
print("유형 유효성 계산 완료", res["유형_채택"], flush=True)

# ---------- 그리드 평가 ----------
GV, GT = VH.grid(), TE.grid()
print("그리드 평가 완료", flush=True)
mv, mt = GV.mean(1), GT.mean(1)                      # (설정, 지표)
rows = []
for i, (l, k, t) in enumerate(SETTINGS):
    r = {"lambda": l, "k": k, "tau": t if k else None}
    r.update({f"valid_{m}": float(mv[i, j]) for j, m in enumerate(MET)})
    r.update({f"test_{m}": float(mt[i, j]) for j, m in enumerate(MET)})
    rows.append(r)
pd.DataFrame(rows).to_csv(f"{OUT}/grid_settings.csv", index=False)
base = 0   # (0,0,0) = 모델 A 그대로


def pick(mean_prec, mean_e, L, allowed=None):
    ok = (mean_prec[base] - mean_prec <= L + 1e-12)
    if allowed is not None:
        ok &= allowed
    cand = np.flatnonzero(ok)
    return int(cand[np.argmax(mean_e[cand])])


is_b1 = np.array([s[1] == 0 for s in SETTINGS])
is_b2 = np.array([s[0] == 0 for s in SETTINGS])
PREC, EDI = 0, 8
pol = {}
for L in LOSS_LIMITS:
    p2 = pick(mv[:, PREC], mv[:, EDI], L)
    b1 = pick(mv[:, PREC], mv[:, EDI], L, is_b1)
    b2 = pick(mv[:, PREC], mv[:, EDI], L, is_b2)
    # 정책 3: 유형별 설정을 따로 고름. 전체 정확도 손실이 한도 이내가 되도록 3개 유형의 조합을 전수 탐색
    w = np.array([(VH.typ == t).sum() for t in range(3)], float)
    w /= w.sum()
    pv = np.stack([GV[:, VH.typ == t, PREC].mean(1) for t in range(3)])          # (유형, 설정)
    ev = np.stack([GV[:, VH.typ == t, EDI].mean(1) for t in range(3)])
    P = w[0] * pv[0][:, None, None] + w[1] * pv[1][None, :, None] + w[2] * pv[2][None, None, :]
    E = w[0] * ev[0][:, None, None] + w[1] * ev[1][None, :, None] + w[2] * ev[2][None, None, :]
    ok = (mv[base, PREC] - P) <= L + 1e-12
    Em = np.where(ok, E, -1)
    s3 = np.unravel_index(np.argmax(Em), Em.shape)
    pol[L] = {"정책2": p2, "B1만": b1, "B2만": b2, "정책3": tuple(int(x) for x in s3)}
print("정책 선정 완료", flush=True)


def stype_metrics(B, G, s3):
    M = np.zeros((B.nU, len(MET)))
    for t in range(3):
        m = B.typ == t
        M[m] = G[s3[t]][m]
    return M


def summarize(M):
    return {m: float(M[:, j].mean()) for j, m in enumerate(MET)}


out = {}
for L in LOSS_LIMITS:
    s = pol[L]
    Av, Tv = GV[base], GT[base]
    d = {"설정": {"정책2": SETTINGS[s["정책2"]], "B1만": SETTINGS[s["B1만"]], "B2만": SETTINGS[s["B2만"]], "정책3": {TYPE_NAMES[t]: SETTINGS[s["정책3"][t]] for t in range(3)}}}
    for blk, G, B in [("valid_holdout", GV, VH), ("test", GT, TE)]:
        A_ = G[base]
        M = {"정책1(A)": A_, "A+B1": G[s["B1만"]], "A+B2": G[s["B2만"]], "정책2(일괄)": G[s["정책2"]], "정책3(차등)": stype_metrics(B, G, s["정책3"])}
        d[blk] = {k: summarize(v) for k, v in M.items()}
        if blk == "test":
            comp = {}
            for a, b in [("정책2(일괄)", "정책1(A)"), ("정책3(차등)", "정책1(A)"), ("정책3(차등)", "정책2(일괄)"), ("A+B1", "정책1(A)"), ("A+B2", "정책1(A)")]:
                D = M[a] - M[b]
                ci = boot_mean(D)
                comp[f"{a} − {b}"] = {m: {"차이": float(D[:, j].mean()), "ci": [float(ci[0, j]), float(ci[1, j])]} for j, m in enumerate(MET)}
            d["test_비교"] = comp
            # 유형별 test 결과
            d["test_유형별"] = {TYPE_NAMES[t]: {"사용자수": int((B.typ == t).sum()),
                                              **{k: {m: float(v[B.typ == t][:, j].mean()) for j, m in [(0, "prec"), (8, "e_D"), (4, "n_D")]} for k, v in M.items() if k in ("정책1(A)", "정책2(일괄)", "정책3(차등)")}} for t in range(3)}
    out[str(L)] = d
res["정책"] = out

# ---------- 노출 수준을 맞춘 비교(주 한도): 정책2 중 노출(통합 n_D)이 정책3과 가장 비슷한 설정 ----------
s = pol[MAIN_L]
M3 = stype_metrics(TE, GT, s["정책3"])
E3 = M3[:, 4].mean()
j = int(np.argmin(np.abs(mt[:, 4] - E3)))
D = M3 - GT[j]
ci = boot_mean(D)
res["노출_맞춤_비교"] = {"정책3_노출": float(E3), "정책2_매칭설정": SETTINGS[j], "정책2_노출": float(mt[j, 4]),
                    "정책3−정책2": {m: {"차이": float(D[:, q].mean()), "ci": [float(ci[0, q]), float(ci[1, q])]} for q, m in enumerate(MET)},
                    "정책2": summarize(GT[j]), "정책3": summarize(M3)}

# ---------- 트레이드오프 곡선(B1 단독, B2 단독) ----------
res["B1_곡선"] = [{"lambda": SETTINGS[i][0], **{f"valid_{m}": float(mv[i, q]) for q, m in enumerate(MET)}, **{f"test_{m}": float(mt[i, q]) for q, m in enumerate(MET)}} for i in range(len(SETTINGS)) if is_b1[i]]
res["B2_곡선"] = [{"k": SETTINGS[i][1], "tau": SETTINGS[i][2], **{f"valid_{m}": float(mv[i, q]) for q, m in enumerate(MET)}, **{f"test_{m}": float(mt[i, q]) for q, m in enumerate(MET)}} for i in range(len(SETTINGS)) if is_b2[i]]
res["B2_후보_충족_사용자비율"] = {f"tau={t}": float(np.mean([((TE.p >= t) & TE.newgen)[TE.uid == u].any() for u in range(0, TE.nU, 7)])) for t in (0.30, 0.40, 0.50)}


# ---------- 6장: 모델 A 구간별 검증 ----------
tr = pd.concat([pd.read_parquet(f"A/v12/featv12_{b}.parquet", columns=["target", "s_cnt_now", "user_rate_lag"]) for b in ("train_a", "train_b")])
tr = tr[tr["user_rate_lag"].notna()]
pop_lr = LogisticRegression().fit(np.log1p(tr[["s_cnt_now"]].to_numpy()), tr["target"].to_numpy())
T = test_all
p_pop = pop_lr.predict_proba(np.log1p(T[["s_cnt_now"]].to_numpy()))[:, 1]
y, pA, user = T["target"].to_numpy(), T["p"].to_numpy(), pd.factorize(T["msno"])[0]


def boot_auc_diff(m, nb=300):
    yy, a, b, uu = y[m].astype(float), pA[m], p_pop[m], user[m]
    codes, uniq = pd.factorize(uu)
    nu = len(uniq)
    ga = np.unique(a, return_inverse=True)[1]
    gb = np.unique(b, return_inverse=True)[1]

    def wauc(g, w):
        k = g.max() + 1
        pos = np.bincount(g, weights=w * yy, minlength=k)
        neg = np.bincount(g, weights=w * (1 - yy), minlength=k)
        below = np.cumsum(neg) - neg
        return (pos * (below + 0.5 * neg)).sum() / (pos.sum() * neg.sum())

    one = np.ones(len(yy))
    d0 = wauc(ga, one) - wauc(gb, one)
    ds = np.empty(nb)
    for i in range(nb):
        w = np.bincount(rng.integers(0, nu, nu), minlength=nu).astype(float)[codes]
        ds[i] = wauc(ga, w) - wauc(gb, w)
    return float(wauc(ga, one)), float(wauc(gb, one)), float(d0), [float(np.percentile(ds, 2.5)), float(np.percentile(ds, 97.5))]


seg = {"전체": np.ones(len(T), bool), "비인기곡": T["unpop"].to_numpy(), "새 아티스트": T["newart"].to_numpy(), "취향 밖 장르": T["newgen"].to_numpy()}
seg["그 외(세 구간 모두 아님)"] = ~(seg["비인기곡"] | seg["새 아티스트"] | seg["취향 밖 장르"])
segs = []
for n, m in seg.items():
    a, b, d0, ci = boot_auc_diff(m)
    segs.append({"구간": n, "행수": int(m.sum()), "비중": float(m.mean()), "실제 재청취율": float(y[m].mean()), "모델A 평균예측": float(pA[m].mean()),
                 "AUC_모델A": a, "AUC_인기도": b, "AUC차이": d0, "ci": ci, "합격": bool(ci[0] > 0)})
res["모델A_구간별"] = segs
json.dump(res, open(f"{OUT}/policies.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=float)
print("저장 완료", flush=True)

# ---------- 추가: 모든 손실 한도에서 노출 수준을 맞춘 비교 ----------
# 위의 모든 계산이 끝난 뒤 별도 난수로 수행하므로 기존 결과 파일의 값은 바뀌지 않는다.
rng = np.random.default_rng(SEED + 7)
matched = {}
for L in LOSS_LIMITS:
    s = pol[L]
    M3 = stype_metrics(TE, GT, s["정책3"])
    E3 = M3[:, 4].mean()
    j = int(np.argmin(np.abs(mt[:, 4] - E3)))
    D = M3 - GT[j]
    ci = boot_mean(D)
    matched[str(L)] = {"정책3_노출": float(E3), "정책2_매칭설정": SETTINGS[j], "정책2_노출": float(mt[j, 4]),
                       "정책3−정책2": {m: {"차이": float(D[:, q].mean()), "ci": [float(ci[0, q]), float(ci[1, q])]} for q, m in enumerate(MET)},
                       "정책2": summarize(GT[j]), "정책3": summarize(M3)}
json.dump(matched, open(f"{OUT}/matched_exposure.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=float)
print("노출 맞춤(전 한도) 저장 완료", flush=True)
