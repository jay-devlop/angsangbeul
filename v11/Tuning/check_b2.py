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
        "user_lag_n", "user_newartist_rate_lag", "user_ootgenre_rate_lag", "user_rate_lag"]
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
    f = pd.read_parquet(f"A/v11/featv11_{blk}.parquet", columns=COLS)
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



VH = Block(valid_all[~valid_all["is_tune"]])
TE = Block(test_all)
KS = list(range(1, 11))
TAUS = [0.1, 0.2, 0.3, 0.4, 0.5]
rows = []
base_v = VH.metrics(VH.select(0, 0, 0.0)).mean(0)
base_t = TE.metrics(TE.select(0, 0, 0.0)).mean(0)
for k in KS:
    for t in TAUS:
        mv = VH.metrics(VH.select(0, k, t)).mean(0)
        mt = TE.metrics(TE.select(0, k, t)).mean(0)
        rows.append({"k": k, "tau": t, "valid_loss_pp": (base_v[0] - mv[0]) * 100, "valid_eD_gain": mv[8] - base_v[8], "valid_newgen_eff": mv[7] - base_v[7], "valid_genres": mv[9],
                     "test_loss_pp": (base_t[0] - mt[0]) * 100, "test_eD_gain": mt[8] - base_t[8], "test_newgen_eff": mt[7] - base_t[7], "test_genres": mt[9]})
df = pd.DataFrame(rows)
df.to_csv(f"{OUT}/check_b2_wide_grid.csv", index=False)
pd.set_option("display.width", 200)
print("검증 구간 (B2 단독, 모델 A 대비)")
print(df.pivot(index="k", columns="tau", values="valid_loss_pp").round(2).to_string())
print(df.pivot(index="k", columns="tau", values="valid_eD_gain").round(3).to_string())
for L in (1.0, 2.0):
    ok = df[df.valid_loss_pp <= L]
    b = ok.loc[ok.valid_eD_gain.idxmax()]
    print(f"\n[한도 {L}%p] 검증 구간 최적: k={int(b.k)}, tau={b.tau} | 검증 손실 {b.valid_loss_pp:.2f}%p, 유효발견 +{b.valid_eD_gain:.3f} | 평가: 손실 {b.test_loss_pp:.2f}%p, 유효발견 +{b.test_eD_gain:.3f}")
    old = ok[(ok.k <= 5) & (ok.tau >= 0.3)]
    o = old.loc[old.valid_eD_gain.idxmax()]
    print(f"   (이전 격자 k<=5, tau>=0.3 최적: k={int(o.k)}, tau={o.tau} | 검증 유효발견 +{o.valid_eD_gain:.3f})")
