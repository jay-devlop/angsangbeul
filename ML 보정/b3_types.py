# 6~8장: 모델 A(v11) 구간별 검증, B1·B2 보정, 정책 1~3 비교.
# 아래 사전 설정은 결과를 보기 전에 고정했다. 보정 방식·강도는 검증 구간(valid holdout)에서만 고르고, test에서는 바꾸지 않는다.
import json
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

SEED, NB, OUT = 42, 1000, "B/results"
TOPK, MIN_CAND, POP_SHARE, MIN_LAG = 10, 20, 0.80, 20
# 2차 실행(격자 확장): 1차 실행에서 최적해가 격자 끝(λ=0.20, k=3)에 걸려 손실 한도가 제약으로 작동하지 않았다. 검증 구간 결과만 보고 격자를 넓혔다.
LAMBDAS = [0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50]   # B1 인기도 패널티 강도 후보
B2_OPTS = [(0, 0.0)] + [(k, t) for k in (1, 2, 3, 4, 5) for t in (0.30, 0.40, 0.50)]   # B2 (교체 곡 수, 최소 예측 확률) 후보
SETTINGS = [(l, k, t) for l in LAMBDAS for (k, t) in B2_OPTS]
LOSS_LIMITS, MAIN_L = [0.01, 0.02, 0.03, 0.05], 0.02              # 정확도(Top-10 재청취율) 손실 허용 한도 후보와 주 한도(절대값)
PREREG = {"1차_사전격자": {"B1_lambda": [0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20], "B2_k": [1, 2, 3]}, "격자확장_사유": "1차 실행에서 최적해가 격자 끝에 걸려 손실 한도가 제약으로 작동하지 않음(검증 구간 기준)",
          "TOPK": TOPK, "MIN_CAND": MIN_CAND, "비인기곡_기준": f"구간 시작 전까지의 청취 기록에서 청취의 {POP_SHARE * 100:.0f}%를 차지하는 상위 곡 밖의 곡", "B1_lambda": LAMBDAS, "B2_(k,tau)": B2_OPTS[1:],
          "손실한도_후보": LOSS_LIMITS, "주_손실한도": MAIN_L, "선정원칙": "한도 이내에서 통합 유효 발견@10 최대", "유형_판단유보_기준(정답 확정 청취 수)": MIN_LAG}
rng = np.random.default_rng(SEED)
COLS = ["row_order", "msno", "song_id", "target", "s_cnt_now", "is_new_artist", "is_various_artist", "is_new_genre", "primary_genre_code",
        "user_lag_n", "user_newartist_rate_lag", "user_ootgenre_rate_lag", "user_rate_lag", "user_unpop_rate_lag", "u_cnt_now", "u_nuniq_genre_now", "u_nuniq_artist_now", "u_newartist_ratio_now", "u_avg_pop_now", "u_local_share_now", "u_radio_share_now"]
MET = ["prec", "n_unpop", "n_newart", "n_newgen", "n_D", "e_unpop", "e_newart", "e_newgen", "e_D", "genres"]


SONG = pd.read_csv("data.csv", engine="pyarrow", usecols=["row_order", "song_id"])
N_ORIG_ = 7377418
POPINFO = {}


def pop_info(frac):
    """구간 시작(frac) 전까지의 기록에서 곡별 청취 수를 세고, 청취의 POP_SHARE를 덮는 상위 곡의 경계 청취 수를 구한다."""
    cnt = SONG.loc[SONG["row_order"] < frac * N_ORIG_, "song_id"].value_counts()
    cum = cnt.cumsum().to_numpy() / cnt.sum()
    bnd = int(cnt.iloc[int(np.searchsorted(cum, POP_SHARE))])
    return cnt, bnd


def load(blk):
    f = pd.read_parquet(f"A/v12/featv12_{blk}.parquet", columns=COLS)
    pc = ["row_order", "p_modelA_v11"] + (["is_tune"] if blk == "valid" else [])
    a = pd.read_parquet(f"A/v11/pred_{blk}_modelA_v11.parquet", columns=pc)
    assert (f["row_order"].to_numpy() == a["row_order"].to_numpy()).all()
    f["p"] = a["p_modelA_v11"].to_numpy()
    if blk == "valid":
        f["is_tune"] = a["is_tune"].to_numpy()
    cnt, bnd = pop_info(0.6 if blk == "valid" else 0.8)
    f["unpop"] = (f["song_id"].map(cnt).fillna(0).to_numpy() < bnd)
    POPINFO[blk] = {"경계_청취수": bnd, "비인기곡_비중": float(f["unpop"].mean())}
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



# ================= 사용자 유형 정의 비교 (A~E + 현행) =================
# 사전 규칙: 선택 지표 = 노출 수준을 맞춘 (차등 - 일괄) 통합 유효 발견 차이.
# 검증 holdout을 2-fold 교차 적합으로 평가하고, 평가 구간은 한 번만 확인한다.
from sklearn.cluster import KMeans

VH = Block(valid_all[~valid_all["is_tune"]])
TE = Block(test_all)
GV, GT = VH.grid(), TE.grid()
print("그리드 평가 완료", flush=True)
CUTA = json.load(open(f"{OUT}/policies.json", encoding="utf-8"))["유형_기준값"]["a"]
LIMITS = [0.01, 0.02]


def ufeat(B):
    return B.d.iloc[np.unique(B.uid, return_index=True)[1]].reset_index(drop=True)


UV, UT = ufeat(VH), ufeat(TE)
score = lambda U: ((U["user_newartist_rate_lag"] + U["user_ootgenre_rate_lag"] + U["user_unpop_rate_lag"]) / 3).to_numpy()
lag_ok = lambda U: (U["user_lag_n"].to_numpy() >= MIN_LAG)
qbin = lambda x, n: pd.qcut(pd.Series(x).rank(method="first"), n, labels=False).to_numpy()

KM_COLS = ["u_cnt_now", "u_nuniq_genre_now", "u_newartist_ratio_now", "u_avg_pop_now", "u_local_share_now", "u_radio_share_now", "user_rate_lag"]


def kmat(U, ref=None):
    X = U[KM_COLS].copy()
    X["u_cnt_now"] = np.log1p(X["u_cnt_now"])
    X["u_nuniq_genre_now"] = U["u_nuniq_genre_now"] / np.maximum(U["u_cnt_now"], 1)
    X["sc"] = score(U)
    return X.fillna(X.median() if ref is None else ref.median())


XV = kmat(UV)
MU, SD = XV.mean(), XV.std().replace(0, 1)
KM = KMeans(n_clusters=3, n_init=10, random_state=SEED).fit(((XV - MU) / SD).to_numpy())


def t_cur(U):
    a = ((U["user_newartist_rate_lag"] + U["user_ootgenre_rate_lag"]) / 2).to_numpy()
    t = np.where(a >= CUTA, 0, 1)
    t[~lag_ok(U)] = 2
    return t


def t_A(U):
    return qbin(score(U), 10)


def t_B(U):
    ok = lag_ok(U)
    sc = score(U)
    pct = np.full(len(U), np.nan)
    pct[ok] = pd.Series(sc[ok]).rank(pct=True).to_numpy()
    t = np.full(len(U), 2)
    t[ok & (pct >= 2 / 3)] = 0
    t[ok & (pct <= 1 / 3)] = 1
    return t


def t_C(U):
    return (qbin(score(U), 2) == 0).astype(int)


def t_D(U):
    return KM.predict(((kmat(U, XV) - MU) / SD).to_numpy())


def t_E(U):
    return qbin(U["u_cnt_now"].to_numpy(), 3)


SCHEMES = {"현행 3유형": t_cur, "A. 점수 10분위(연속에 가까움)": t_A, "B. 3유형 기준 개선": t_B, "C. 2유형": t_C, "D. 군집 3개": t_D, "E. 활동량 3분위": t_E}
base_idx = 0


def choose(G, users, t, T, L):
    S_ = G.shape[0]
    base = G[base_idx][users, 0].mean()
    P, E, w = np.zeros((T, S_)), np.zeros((T, S_)), np.zeros(T)
    for k in range(T):
        m = users & (t == k)
        w[k] = m.sum()
        mm = m if m.sum() else users
        P[k], E[k] = G[:, mm, 0].mean(1), G[:, mm, 8].mean(1)
    w = w / w.sum()
    if T == 1:
        ok = (base - P[0]) <= L + 1e-12
        return np.array([int(np.flatnonzero(ok)[np.argmax(E[0][ok])])])
    if T <= 3:
        shape = lambda k: [-1 if i == k else 1 for i in range(T)]
        Pt = sum(w[k] * P[k].reshape(shape(k)) for k in range(T))
        Et = sum(w[k] * E[k].reshape(shape(k)) for k in range(T))
        Em = np.where((base - Pt) <= L + 1e-12, Et, -1)
        return np.array(np.unravel_index(np.argmax(Em), Em.shape))
    ar = np.arange(T)
    loss_of = lambda s: base - (w * P[ar, s]).sum()
    s = E.argmax(1)
    if loss_of(s) > L:
        lo, hi = 0.0, 100.0
        for _ in range(60):
            mid = (lo + hi) / 2
            s = (E + mid * P).argmax(1)
            if loss_of(s) <= L:
                hi = mid
            else:
                lo = mid
        s = (E + hi * P).argmax(1)
    for _ in range(20):
        moved = False
        for k in range(T):
            rest_P = (w * P[ar, s]).sum() - w[k] * P[k, s[k]]
            rest_E = (w * E[ar, s]).sum() - w[k] * E[k, s[k]]
            tot_loss = base - (rest_P + w[k] * P[k])
            tot_E = np.where(tot_loss <= L + 1e-12, rest_E + w[k] * E[k], -1)
            j = int(np.argmax(tot_E))
            if tot_E[j] > (w * E[ar, s]).sum() + 1e-12:
                s[k] = j
                moved = True
        if not moved:
            break
    return s


def apply(G, t, s):
    M = np.zeros((G.shape[1], G.shape[2]))
    for k in range(len(s)):
        m = t == k
        M[m] = G[s[k]][m]
    return M


def matched(G, M):
    ex = G[:, :, 4].mean(1)
    j = int(np.argmin(np.abs(ex - M[:, 4].mean())))
    D = M - G[j]
    ci = boot_mean(D[:, [0, 8]])
    return {"노출": float(M[:, 4].mean()), "매칭설정": SETTINGS[j], "prec차이": float(D[:, 0].mean()), "prec_ci": [float(ci[0, 0]), float(ci[1, 0])],
            "eD차이": float(D[:, 8].mean()), "eD_ci": [float(ci[0, 1]), float(ci[1, 1])], "일괄대비%": float(D[:, 8].mean() / G[j][:, 8].mean() * 100)}


fold = np.random.default_rng(11).integers(0, 2, VH.nU)
out = {}
for name, fn in SCHEMES.items():
    tv, tt = fn(UV), fn(UT)
    T = int(max(tv.max(), tt.max())) + 1
    res_s = {"유형수": T, "검증_사용자수": np.bincount(tv, minlength=T).tolist(), "평가_사용자수": np.bincount(tt, minlength=T).tolist()}
    for L in LIMITS:
        Mv = np.zeros((VH.nU, len(MET)))
        for f_ in (0, 1):
            sel, ev = fold != f_, fold == f_
            s = choose(GV, sel, tv, T, L)
            for k in range(T):
                m = ev & (tv == k)
                Mv[m] = GV[s[k]][m]
        cv = matched(GV, Mv)
        s_full = choose(GV, np.ones(VH.nU, bool), tv, T, L)
        Mt = apply(GT, tt, s_full)
        ct = matched(GT, Mt)
        ct["test_손실%p"] = float((GT[base_idx][:, 0].mean() - Mt[:, 0].mean()) * 100)
        ct["test_유효발견증가"] = float(Mt[:, 8].mean() - GT[base_idx][:, 8].mean())
        res_s[f"{L}"] = {"검증_교차적합": cv, "평가": ct, "선택설정": [SETTINGS[int(x)] for x in s_full]}
    out[name] = res_s
    print(name, "완료", flush=True)
json.dump(out, open(f"{OUT}/type_schemes.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=float)
for L in LIMITS:
    print(f"\n=== 한도 {L * 100:.0f}%p: 노출 맞춤 (차등-일괄) 통합 유효 발견 차이 ===")
    for name, r in sorted(out.items(), key=lambda kv: -kv[1][str(L)]["검증_교차적합"]["eD차이"]):
        v, t = r[str(L)]["검증_교차적합"], r[str(L)]["평가"]
        print(f"{name:30s} 유형{r['유형수']:2d} | 검증(교차적합) {v['eD차이']:+.3f} [{v['eD_ci'][0]:+.3f},{v['eD_ci'][1]:+.3f}] ({v['일괄대비%']:+.1f}%) | 평가(참고) {t['eD차이']:+.3f} [{t['eD_ci'][0]:+.3f},{t['eD_ci'][1]:+.3f}] ({t['일괄대비%']:+.1f}%) 손실 {t['test_손실%p']:.2f}%p")
