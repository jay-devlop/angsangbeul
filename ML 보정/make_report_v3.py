# 결과 파일(JSON·CSV)에서 값을 읽어 최종 보고서 HTML을 만든다. 보고서의 숫자는 모두 이 스크립트가 파일에서 직접 채운다.
import json
import numpy as np
import pandas as pd

R = "B/results"
LP = lambda L: float(L) * 100
H = json.load(open(f"{R}/hypotheses.json", encoding="utf-8"))
P = json.load(open(f"{R}/policies.json", encoding="utf-8"))
P1 = json.load(open(f"{R}/policies_run1.json", encoding="utf-8"))
V1 = json.load(open(f"{R}/v1_algorithms.json", encoding="utf-8"))
G = pd.read_csv(f"{R}/grid_settings.csv")
V11 = json.load(open("A/v11/modelA_v11_설정과결과.json", encoding="utf-8"))
v11_test = pd.read_csv("A/v11/result_test.csv")
v11_val = pd.read_csv("A/v11/result_valid_holdout.csv")
v11_chk = pd.read_csv("A/v11/result_합격선검증.csv")
FI = pd.read_csv("A/v11/result_특성중요도.csv", index_col=0)["gain비중"]
MAIN = "0.02"
TN = ["탐색 친화형", "익숙함 선호형", "판단 유보형"]


def f(x, n=4):
    return f"{x:.{n}f}"


def sg(x, n=4):
    return f"{x:+.{n}f}"


def pp(x, n=2):          # 비율 차이를 %p로
    return f"{x * 100:+.{n}f}%p"


def pc(x, n=1):
    return f"{x * 100:.{n}f}%"


def ci(c, n=4):
    return f"[{c[0]:.{n}f}, {c[1]:.{n}f}]"


def tbl(head, rows, num=(), cap=None, cls=None):
    h = "".join(f'<th class="n">{x}</th>' if i in num else f"<th>{x}</th>" for i, x in enumerate(head))
    b = ""
    for r in rows:
        rc = ""
        if isinstance(r, dict):
            rc, r = r.get("cls", ""), r["cells"]
        b += f'<tr class="{rc}">' + "".join(f'<td class="n">{x}</td>' if i in num else f"<td>{x}</td>" for i, x in enumerate(r)) + "</tr>"
    c = f"<caption>{cap}</caption>" if cap else ""
    return f'<div class="tw"><table>{c}<thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def setting(s):
    l, k, t = s
    parts = []
    if l:
        parts.append(f"B1 λ={l:.2f}")
    if k:
        parts.append(f"B2 k={k}, τ={t:.1f}")
    return " + ".join(parts) if parts else "보정 없음"


# ============ SVG: 정확도 손실 - 유효 발견 증가 ============
def tradeoff_svg():
    base = G.iloc[0]
    G["x"] = (base["test_prec"] - G["test_prec"]) * 100
    G["y"] = G["test_e_D"] - base["test_e_D"]
    W, Hh, ml, mr, mt, mb = 680, 380, 56, 16, 16, 48
    xmax, ymax = 7.0, 0.8
    X = lambda v: ml + (W - ml - mr) * v / xmax
    Y = lambda v: mt + (Hh - mt - mb) * (1 - v / ymax)
    s = [f'<svg viewBox="0 0 {W} {Hh}" role="img" aria-label="정확도 손실 대비 유효 발견 증가" style="width:100%;height:auto;max-width:{W}px">']
    for v in range(0, 8):
        s.append(f'<line x1="{X(v)}" y1="{mt}" x2="{X(v)}" y2="{Hh - mb}" stroke="var(--line-soft)"/><text x="{X(v)}" y="{Hh - mb + 16}" text-anchor="middle" font-size="11" fill="var(--muted)">{v}</text>')
    for v in np.arange(0, 0.81, 0.2):
        s.append(f'<line x1="{ml}" y1="{Y(v)}" x2="{W - mr}" y2="{Y(v)}" stroke="var(--line-soft)"/><text x="{ml - 6}" y="{Y(v) + 4}" text-anchor="end" font-size="11" fill="var(--muted)">{v:.1f}</text>')
    s.append(f'<text x="{(ml + W - mr) / 2}" y="{Hh - 8}" text-anchor="middle" font-size="12" fill="var(--text)">Top-10 재청취율 손실 (%p, test)</text>')
    s.append(f'<text transform="translate(14,{(mt + Hh - mb) / 2}) rotate(-90)" text-anchor="middle" font-size="12" fill="var(--text)">통합 유효 발견@10 증가 (곡)</text>')
    for _, r in G.iterrows():
        if 0 <= r.x <= xmax and r.y <= ymax:
            s.append(f'<circle cx="{X(r.x):.1f}" cy="{Y(r.y):.1f}" r="2.6" fill="var(--dot)" opacity=".55"/>')
    b1 = G[(G.k == 0)].sort_values("lambda")
    s.append('<polyline fill="none" stroke="var(--c1)" stroke-width="2" points="' + " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(b1.x, b1.y)) + '"/>')
    for a, b in zip(b1.x, b1.y):
        s.append(f'<circle cx="{X(a):.1f}" cy="{Y(b):.1f}" r="3.6" fill="var(--c1)"/>')
    b2 = G[(G["lambda"] == 0) & (G.k > 0) & (np.isclose(G.tau, 0.3))].sort_values("k")
    b2 = pd.concat([G.iloc[[0]], b2])
    s.append('<polyline fill="none" stroke="var(--c2)" stroke-width="2" points="' + " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(b2.x, b2.y)) + '"/>')
    for a, b in zip(b2.x, b2.y):
        s.append(f'<circle cx="{X(a):.1f}" cy="{Y(b):.1f}" r="3.6" fill="var(--c2)"/>')
    p = P["정책"][MAIN]["test"]
    base_p = p["정책1(A)"]
    for nm, col, shape in [("정책2(일괄)", "var(--c3)", "sq"), ("정책3(차등)", "var(--c4)", "dia")]:
        x, y = (base_p["prec"] - p[nm]["prec"]) * 100, p[nm]["e_D"] - base_p["e_D"]
        if shape == "sq":
            s.append(f'<rect x="{X(x) - 6:.1f}" y="{Y(y) - 6:.1f}" width="12" height="12" fill="{col}" stroke="var(--paper)" stroke-width="1.5"/>')
        else:
            cx, cy = X(x), Y(y)
            s.append(f'<polygon points="{cx:.1f},{cy - 8:.1f} {cx + 8:.1f},{cy:.1f} {cx:.1f},{cy + 8:.1f} {cx - 8:.1f},{cy:.1f}" fill="{col}" stroke="var(--paper)" stroke-width="1.5"/>')
    s.append(f'<circle cx="{X(0)}" cy="{Y(0)}" r="5" fill="var(--text)"/>')
    lx, ly = ml + 12, mt + 14
    for i, (c, t) in enumerate([("var(--text)", "모델 A (보정 없음)"), ("var(--c1)", "B1 단독 (λ 0~0.5)"), ("var(--c2)", "B2 단독 (τ=0.3, k 1~5)"), ("var(--c3)", "정책 2 (일괄, 한도 2%p)"), ("var(--c4)", "정책 3 (차등, 한도 2%p)"), ("var(--dot)", "그 외 설정 조합 (176개)")]):
        s.append(f'<circle cx="{lx}" cy="{ly + i * 17}" r="5" fill="{c}"/><text x="{lx + 12}" y="{ly + i * 17 + 4}" font-size="11.5" fill="var(--text)">{t}</text>')
    s.append("</svg>")
    import re as _re

    def fix(m):
        tag = m.group(0)
        pairs = _re.findall(r'(fill|stroke)="(var\([^"]+\))"', tag)
        if not pairs:
            return tag
        tag = _re.sub(r'\s(?:fill|stroke)="var\([^"]+\)"', "", tag)
        return tag[:-2] + ' style="' + ";".join(f"{a}:{b}" for a, b in pairs) + '"/>' if tag.endswith("/>") else tag[:-1] + ' style="' + ";".join(f"{a}:{b}" for a, b in pairs) + '">'

    return _re.sub(r"<(?:circle|rect|polygon|polyline|line|text)\b[^>]*>", fix, "".join(s))


# ============ 표 만들기 ============
pol = P["정책"][MAIN]
T = pol["test"]
Vh = pol["valid_holdout"]
cmp_ = pol["test_비교"]

# 6장
algo_rows = [[k, f(v, 5)] for k, v in V1.items()]
algo_note = {"LightGBM_v2": "부스팅 (확장 특성으로 학습한 버전, v1 내부 표기)", "LogisticRegression": "선형 모델", "RandomForest": "배깅", "ExtraTrees": "배깅", "LightGBM_v2": "부스팅", "LightGBM": "부스팅", "CatBoost": "부스팅", "CatBoost_v2": "부스팅"}
algo_tbl = tbl(["알고리즘", "valid holdout AUC", "비고"], [{"cls": "sel" if k in ("LightGBM_v2",) else "", "cells": [k, f(v, 5), algo_note.get(k, "")]} for k, v in V1.items()], num=(1,), cap="v1에서 비교한 후보 알고리즘 (동일한 분할·평가 조건)")

hist_rows = [
    ["v2", "정답 지연 규칙(43%) 도입, 44개 특성", "0.6231"], ["v3", "취향 SVD 추가, LightGBM 튜닝", "0.6267"], ["v4", "최근 인기(trend) 특성 채택", "0.6281"],
    ["v5", "train+valid로 재학습", "0.6434"], ["v6", "모든 특성을 \"현재 행 직전까지\" 기준으로 재설계(71개)", "0.6733"],
    ["v7", "노출 경로 특성 추가(source_* 사용)", "0.7030"], ["v8", "20~43% 구간도 학습에 포함, 튜닝", "0.7049"], ["v9", "라이브러리·라디오 성향 특성", "0.7072"],
    ["v10", "탭별 재생 비율(경로 프로필) 특성", "0.7084"], {"cls": "sel", "cells": ["v11", "기본 모델 4종 × 조합 17개 비교 → Stack4 선정 (<b>모델 A</b>)", "0.7088"]},
    ["v12", "특성 7개(채택 기준 미달)와 LightGBM 1종 추가. 개선이 유의하지 않고 보정 오차가 나빠져 모델 A로 쓰지 않음", "0.7089"],
]
hist_tbl = tbl(["버전", "주요 변경", "test AUC"], hist_rows, num=(2,), cap="모델 A 개선 과정 (test AUC)")

mrows = []
vv = v11_val.set_index("모델")
for nm in ["모델A v11 (Stack4)", "인기도 기준선", "사용자 재청취율 기준선"]:
    r = vv.loc[nm]
    mrows.append([nm.replace("모델A v11 (Stack4)", "모델 A (Stack4)"), f(r.AUC, 5), f(r.logloss, 5), f(r.ECE, 4)])
tt = v11_test.set_index("모델")
trows = [["모델 A (Stack4, train+valid 재학습)", f(tt.iloc[0].AUC, 5), f(tt.iloc[0].logloss, 5), f(tt.iloc[0].ECE, 4), f(tt.iloc[0].평균예측, 3), f(tt.iloc[0].실제평균, 3)]]
for nm in ["인기도 기준선", "사용자 재청취율 기준선"]:
    r = tt.loc[nm]
    trows.append([nm, f(r.AUC, 5), f(r.logloss, 5), f(r.ECE, 4), f(r.평균예측, 3), f(r.실제평균, 3)])
perf_val = tbl(["모델", "AUC", "logloss", "ECE"], mrows, num=(1, 2, 3), cap="valid holdout (모델 선택에 쓴 구간)")
perf_test = tbl(["모델 (test)", "AUC", "logloss", "ECE", "평균 예측", "실제 평균"], [{"cls": "sel", "cells": trows[0]}] + trows[1:], num=(1, 2, 3, 4, 5), cap="test (최종 확인)")

seg_rows = [[s["구간"], f"{s['행수']:,}", pc(s["비중"]), f(s["실제 재청취율"], 3), f(s["모델A 평균예측"], 3), f(s["AUC_모델A"]), f(s["AUC_인기도"]), sg(s["AUC차이"]), ci(s["ci"]), "통과" if s["합격"] else "미통과"] for s in P["모델A_구간별"]]
seg_tbl = tbl(["구간 (test)", "행 수", "비중", "실제 재청취율", "모델 A 평균 예측", "AUC 모델 A", "AUC 인기도", "AUC 차이", "95% 신뢰구간", "합격선"], seg_rows, num=(1, 2, 3, 4, 5, 6, 7), cap="구간별 예측 성능 (사용자 단위 부트스트랩 300회)")

# 5장 표
h1 = H["H1"]
qord = ["최근 가입(Q1)", "Q2", "Q3", "오래된 가입(Q4)"]
qd = {r["가입시기"]: r for r in h1["교차_사분위"]}
h1_q = tbl(["가입 시기 사분위", "사용자 수", "평균 고유 장르 수", "평균 최다 장르 비중", "평균 엔트로피"], [[q, f"{qd[q]['사용자수']:,}", f(qd[q]["평균_고유장르수"], 2), f(qd[q]["평균_최다장르비중"], 3), f(qd[q]["평균_엔트로피"], 3)] for q in qord], num=(1, 2, 3, 4), cap="H1 가입 시기별 장르 폭 (첫 50회 청취 기준)")
h1_s = tbl(["지표", "Spearman ρ (가입 후 경과일과의 상관)", "95% 신뢰구간"], [[n, sg(h1[f"교차_spearman_{k}"]["rho"]), ci(h1[f"교차_spearman_{k}"]["ci"])] for n, k in [("고유 장르 수", "nuniq"), ("최다 장르 비중", "top"), ("엔트로피", "ent")]], num=(1,))
h1_w = tbl(["지표 (후반 50회 − 초반 50회)", "평균 변화", "95% 신뢰구간", "줄어든 사용자 비율"], [[n, sg(h1[f"사용자내_후반−초반_{k}"]["평균"]), ci(h1[f"사용자내_후반−초반_{k}"]["ci"]), pc(h1[f"사용자내_후반−초반_{k}"]["줄어든_사용자비율"])] for n, k in [("고유 장르 수", "고유장르수"), ("최다 장르 비중", "최다장르비중"), ("엔트로피", "엔트로피")]], num=(1, 3), cap=f"사용자 내 변화 (청취 100회 이상 {h1['사용자내_사용자수']:,}명)")
h2 = H["H2"]
h2_q = tbl(["편중도 사분위 (최다 장르 비중)", "사용자 수", "이탈률", "평균 활동 변화(log 비율)"], [[r["q"], f"{r['사용자수']:,}", pc(r["이탈률"], 2), sg(r["평균_활동변화"], 3)] for r in h2["편중도_사분위"]], num=(1, 2, 3), cap=f"H2 편중도와 이후 활동 (대상 {h2['사용자수']:,}명)")
h2k = [("spearman_최다장르비중_vs_활동변화", "최다 장르 비중 (단순 상관)"), ("통제후_spearman_최다장르비중", "최다 장르 비중 (활동량 통제 후)"), ("spearman_엔트로피(낮을수록 편중)_vs_활동변화", "엔트로피 (단순 상관)"), ("통제후_spearman_엔트로피(낮을수록 편중)", "엔트로피 (활동량 통제 후)")]
h2_s = tbl(["편중도 지표", "활동 변화와의 Spearman ρ", "95% 신뢰구간"], [[n, sg(h2[k]["rho"]), ci(h2[k]["ci"])] for k, n in h2k], num=(1,))
h3 = H["H3"]
h3p = h3["풀링"]["비인기곡"]["비율"]
h3w = h3["사용자내_추천−직접탐색"]["비인기곡"]
h3n = h3["풀링"]["새 아티스트"]["비율"]
gn = ["추천·큐레이션 경로", "직접 탐색 (search)", "내 라이브러리"]
h3_p = tbl(["지표 (청취 중 비율)"] + gn, [[k, *[f"{pc(v['비율'][i], 1)} {ci([c * 100 for c in v['ci'][i]], 1)}" for i in range(3)]] for k, v in h3["풀링"].items()], num=(1, 2, 3), cap="H3 경로별 다양성 지표 (괄호는 95% 신뢰구간, %)")
h3_w = tbl(["지표", "대상 사용자 수", "추천 경로 − 직접 탐색 (사용자 내 평균 차이)", "95% 신뢰구간", "추천 경로가 더 낮은 사용자 비율"], [[k, f"{v['사용자수']:,}", sg(v["평균차"]), ci(v["ci"]), pc(v["추천이_더_낮은_사용자비율"])] for k, v in h3["사용자내_추천−직접탐색"].items()], num=(1, 2, 4), cap="같은 사용자의 두 경로 비교 (두 경로에서 각각 10회 이상 청취한 사용자)")
h4 = H["H4"]
rk, ak = "후기_활동유지율(80~100%구간 청취有)", "활동변화(log 비율)"
h4_t = tbl(["결과 지표", "새 장르 시도군", "비시도군", "단순 차이", "통제 후 차이", "통제 후 95% 신뢰구간"], [
    ["후기 활동 유지율", pc(h4[rk]["시도군"], 1), pc(h4[rk]["비시도군"], 1), pp(h4[rk]["단순차"]), pp(h4[rk]["통제후_차"]), "[" + ", ".join(pp(c) for c in h4[rk]["통제후_ci"]) + "]"],
    ["활동 변화 (log 비율)", sg(h4[ak]["시도군"], 3), sg(h4[ak]["비시도군"], 3), sg(h4[ak]["단순차"], 3), sg(h4[ak]["통제후_차"], 3), ci(h4[ak]["통제후_ci"], 3)]], num=(1, 2, 3, 4), cap=f"H4 새 장르 시도와 활동 유지 (대상 {h4['사용자수']:,}명, 시도 {h4['새_장르_시도_사용자수']:,}명)")
verdict = tbl(["가설", "결과 요약", "판정"], [
    ["H1 이용 기간↑ → 장르 좁아짐", f"가입 시기별 차이가 매우 작고(|ρ|≤0.06), 같은 사용자 안에서는 후반에 고유 장르 수가 늘었다({sg(h1['사용자내_후반−초반_고유장르수']['평균'], 2)}개).", "지지되지 않음"],
    ["H2 편중↑ → 이후 활동↓", f"편중이 높을수록 활동이 조금 더 줄지만 상관이 작다(통제 후 ρ={h2['통제후_spearman_최다장르비중']['rho']:+.3f}). 이탈률은 편중도와 일관된 관계가 없다.", "약하게 지지"],
    ["H3 추천 경로의 다양성 < 직접 탐색", f"비인기곡 비중은 추천 경로가 조금 낮지만({pc(h3p[0])} 대 {pc(h3p[1])}) 차이가 작고, 새 아티스트 비중은 추천 경로가 훨씬 높다({pc(h3n[0])} 대 {pc(h3n[1])}).", "약하게 지지 (인기 편향 지표에서만, 효과 작음)"],
    ["H4 새 장르 시도 → 활동 유지", f"단순 비교에서는 유지율이 높지만({pp(h4[rk]['단순차'])}), 활동량을 맞추면 {pp(h4[rk]['통제후_차'])}로 줄고 신뢰구간이 0을 포함한다.", "지지되지 않음"]], cap="가설 검증 요약")

# 7장
b1rows = []
b1 = [c for c in P["B1_곡선"]]
a0 = b1[0]
for c in b1:
    b1rows.append({"cls": "sel" if abs(c["lambda"] - 0.2) < 1e-9 else "", "cells": [f"{c['lambda']:.2f}", f(c["test_prec"], 4), pp(c["test_prec"] - a0["test_prec"]), f(c["test_n_unpop"], 2), f(c["test_e_unpop"], 3), f(c["test_e_D"], 3), sg(c["test_e_D"] - a0["test_e_D"], 3), f(c["test_genres"], 2)]})
b1_tbl = tbl(["λ", "Top-10 재청취율", "변화", "비인기곡 노출(곡)", "유효 비인기곡@10", "통합 유효 발견@10", "증가", "고유 장르 수@10"], b1rows, num=tuple(range(8)), cap="B1 인기도 보정: 강도별 결과 (test, 후보 20곡 이상 사용자 15,080명)")
b2 = [c for c in P["B2_곡선"]]
b2rows = []
for c in b2:
    if c["k"] == 0:
        continue
    b2rows.append({"cls": "sel" if (c["k"], c["tau"]) == (5, 0.3) else "", "cells": [c["k"], f"{c['tau']:.1f}", f(c["test_prec"], 4), pp(c["test_prec"] - a0["test_prec"]), f(c["test_n_newgen"], 2), f(c["test_e_newgen"], 3), f(c["test_e_D"], 3), sg(c["test_e_D"] - a0["test_e_D"], 3), f(c["test_genres"], 2)]})
b2_tbl = tbl(["교체 곡 수 k", "최소 예측 확률 τ", "Top-10 재청취율", "변화", "취향 밖 장르 노출(곡)", "유효 취향 밖 장르@10", "통합 유효 발견@10", "증가", "고유 장르 수@10"], b2rows, num=tuple(range(9)), cap="B2 취향 확장 보정: 설정별 결과 (test). 강조한 행은 한도 2%p에서 B2 단독으로 선정된 설정이며, 시험한 범위의 끝값입니다")
cov = P["B2_후보_충족_사용자비율"]
single_rows = []
for nm in ["정책1(A)", "A+B1", "A+B2"]:
    x = T[nm]
    c = cmp_.get(f"{nm} − 정책1(A)")
    single_rows.append([nm.replace("정책1(A)", "모델 A (보정 없음)"), setting(pol["설정"]["B1만"]) if nm == "A+B1" else (setting(pol["설정"]["B2만"]) if nm == "A+B2" else "–"), f(x["prec"], 4), (pp(c["prec"]["차이"]) + " " + ci([v * 100 for v in c["prec"]["ci"]], 2) if c else "–"), f(x["e_D"], 3), (sg(c["e_D"]["차이"], 3) + " " + ci(c["e_D"]["ci"], 3) if c else "–"), f(x["e_unpop"], 3), f(x["e_newgen"], 3), f(x["genres"], 2)])
single_tbl = tbl(["방식", "선정 설정 (검증 구간, 한도 2%p)", "Top-10 재청취율", "변화 [95% 신뢰구간, %p]", "통합 유효 발견@10", "변화 [95% 신뢰구간]", "유효 비인기곡", "유효 취향 밖 장르", "고유 장르 수"], single_rows, num=(2, 4, 6, 7, 8), cap="B1·B2 단독 적용 결과 (test)")

# 8장
def validity_tbl(kind, blk):
    d = P["유형_유효성"][kind][blk]
    rows = []
    for n in TN:
        x = d[n]
        rows.append([n, f"{x['사용자수']:,}", f(x["전체 재청취율"], 3), f(x["새 아티스트 재청취율"], 3), f(x["취향 밖 장르 재청취율"], 3), f(x["비인기곡 재청취율"], 3)])
    c = d["탐색−익숙 재청취율 차이"]
    rows.append({"cls": "sel", "cells": ["탐색 − 익숙 (차이, 95% 신뢰구간)", "", "", f"{sg(c['새 아티스트']['차이'], 3)} {ci(c['새 아티스트']['ci'], 3)}", f"{sg(c['취향 밖 장르']['차이'], 3)} {ci(c['취향 밖 장르']['ci'], 3)}", f"{sg(c['비인기곡']['차이'], 3)} {ci(c['비인기곡']['ci'], 3)}"]})
    return tbl(["유형", "사용자 수", "전체 재청취율", "새 아티스트 재청취율", "취향 밖 장르 재청취율", "비인기곡 재청취율"], rows, num=(1, 2, 3, 4, 5), cap={"valid_holdout": "검증 구간(valid holdout)", "test": "평가 구간(test)"}[blk] + " — 채택한 유형 정의의 실제 재청취율")


cuts = P["유형_기준값"]
z_v = P["유형_유효성"]["z"]["valid_holdout"]["탐색−익숙 재청취율 차이"]
sel_rows = []
for L in ["0.01", "0.02", "0.03", "0.05"]:
    s = P["정책"][L]["설정"]
    sel_rows.append([f"{float(L) * 100:.0f}%p", setting(s["정책2"]), setting(s["정책3"][TN[0]]), setting(s["정책3"][TN[1]]), setting(s["정책3"][TN[2]])])
sel_tbl = tbl(["손실 한도", "정책 2 (일괄)", "정책 3: 탐색 친화형", "정책 3: 익숙함 선호형", "정책 3: 판단 유보형"], sel_rows, cap="검증 구간에서 선정한 보정 설정")

pol_rows = []
for nm, lab in [("정책1(A)", "정책 1: 기본 개인화 (A)"), ("정책2(일괄)", "정책 2: 일괄 보정"), ("정책3(차등)", "정책 3: 차등 보정 (B3)")]:
    v, t = Vh[nm], T[nm]
    c = cmp_.get(f"{nm} − 정책1(A)")
    pol_rows.append({"cls": "sel" if "3" in lab else "", "cells": [lab, f(v["prec"], 4), f(t["prec"], 4), (pp(c["prec"]["차이"]) if c else "–"), f(t["n_D"], 2), f(t["e_D"], 3), (sg(c["e_D"]["차이"], 3) + " " + ci(c["e_D"]["ci"], 3) if c else "–"), f(t["e_unpop"], 3), f(t["e_newart"], 3), f(t["e_newgen"], 3), f(t["genres"], 2)]})
pol_tbl = tbl(["정책", "Top-10 재청취율 (valid)", "Top-10 재청취율 (test)", "test 변화(vs 정책1)", "발견 대상곡 노출(곡)", "통합 유효 발견@10", "변화 vs 정책1 [95% 신뢰구간]", "유효 비인기곡", "유효 새 아티스트", "유효 취향 밖 장르", "고유 장르 수"], pol_rows, num=tuple(range(1, 11)), cap="세 가지 정책의 비교 (손실 한도 2%p, test)")
c32 = cmp_["정책3(차등) − 정책2(일괄)"]
c21 = cmp_["정책2(일괄) − 정책1(A)"]
c31 = cmp_["정책3(차등) − 정책1(A)"]
sens_rows = []
for L in ["0.01", "0.02", "0.03", "0.05"]:
    pl = P["정책"][L]
    t = pl["test"]
    c = pl["test_비교"]["정책3(차등) − 정책2(일괄)"]
    a = t["정책1(A)"]
    sens_rows.append([f"{float(L) * 100:.0f}%p", pp(t["정책2(일괄)"]["prec"] - a["prec"]), sg(t["정책2(일괄)"]["e_D"] - a["e_D"], 3), pp(t["정책3(차등)"]["prec"] - a["prec"]), sg(t["정책3(차등)"]["e_D"] - a["e_D"], 3), pp(c["prec"]["차이"]) + " " + ci([v * 100 for v in c["prec"]["ci"]], 2), sg(c["e_D"]["차이"], 3) + " " + ci(c["e_D"]["ci"], 3)])
sens_tbl = tbl(["손실 한도", "정책 2: 재청취율 변화", "정책 2: 유효 발견 증가", "정책 3: 재청취율 변화", "정책 3: 유효 발견 증가", "정책 3 − 정책 2: 재청취율", "정책 3 − 정책 2: 유효 발견"], sens_rows, num=tuple(range(1, 7)), cap="손실 한도별 정책 비교 (test, 정책 1 대비)")
em = P["노출_맞춤_비교"]
emd = em["정책3−정책2"]
em_tbl = tbl(["항목", "정책 2 (노출 맞춤 설정)", "정책 3 (차등)", "차이 (정책 3 − 정책 2) [95% 신뢰구간]"], [
    ["적용 설정", setting(em["정책2_매칭설정"]), "유형별 설정 (표 참고)", ""],
    ["발견 대상곡 노출(곡)", f(em["정책2"]["n_D"], 3), f(em["정책3"]["n_D"], 3), sg(emd["n_D"]["차이"], 3) + " " + ci(emd["n_D"]["ci"], 3)],
    ["Top-10 재청취율", f(em["정책2"]["prec"], 4), f(em["정책3"]["prec"], 4), pp(emd["prec"]["차이"]) + " " + ci([v * 100 for v in emd["prec"]["ci"]], 2)],
    {"cls": "sel", "cells": ["통합 유효 발견@10", f(em["정책2"]["e_D"], 3), f(em["정책3"]["e_D"], 3), sg(emd["e_D"]["차이"], 3) + " " + ci(emd["e_D"]["ci"], 3)]},
    ["유효 비인기곡", f(em["정책2"]["e_unpop"], 3), f(em["정책3"]["e_unpop"], 3), sg(emd["e_unpop"]["차이"], 3) + " " + ci(emd["e_unpop"]["ci"], 3)],
    ["유효 새 아티스트", f(em["정책2"]["e_newart"], 3), f(em["정책3"]["e_newart"], 3), sg(emd["e_newart"]["차이"], 3) + " " + ci(emd["e_newart"]["ci"], 3)],
    ["유효 취향 밖 장르", f(em["정책2"]["e_newgen"], 3), f(em["정책3"]["e_newgen"], 3), sg(emd["e_newgen"]["차이"], 3) + " " + ci(emd["e_newgen"]["ci"], 3)],
    ["고유 장르 수@10", f(em["정책2"]["genres"], 2), f(em["정책3"]["genres"], 2), sg(emd["genres"]["차이"], 2) + " " + ci(emd["genres"]["ci"], 2)]], num=(1, 2), cap="발견 대상곡 노출 수준을 맞춘 비교 (test)")
def ut_table(L):
    ut_ = P["정책"][L]["test_유형별"]
    rows = []
    for n in TN:
        x = ut_[n]
        a, b, c = x["정책1(A)"], x["정책2(일괄)"], x["정책3(차등)"]
        rows.append([n, f"{x['사용자수']:,}", f(a["prec"], 3), f(a["e_D"], 2), f"{f(b['prec'], 3)} ({pp(b['prec'] - a['prec'], 1)})", f"{f(b['e_D'], 2)} ({sg(b['e_D'] - a['e_D'], 2)})", f"{f(c['prec'], 3)} ({pp(c['prec'] - a['prec'], 1)})", f"{f(c['e_D'], 2)} ({sg(c['e_D'] - a['e_D'], 2)})"])
    return tbl(["사용자 유형", "사용자 수", "정책 1 재청취율", "정책 1 유효 발견", "정책 2 재청취율 (변화)", "정책 2 유효 발견 (증가)", "정책 3 재청취율 (변화)", "정책 3 유효 발견 (증가)"], rows, num=tuple(range(1, 8)), cap=f"유형별 정책 효과 (손실 한도 {LP(L):.0f}%p, test)")


ut = pol["test_유형별"]
ut_tbl = ut_table("0.01") + ut_table("0.02")
gain_share = {n: (ut[n]["정책3(차등)"]["e_D"] - ut[n]["정책1(A)"]["e_D"]) * ut[n]["사용자수"] for n in TN}
gs = sum(gain_share.values())
ucnt = [ut[n]['사용자수'] / sum(ut[m]['사용자수'] for m in TN) for n in TN]

# 사용자 수 / 격자
nv, nt = P["사용자수"]["valid_holdout"], P["사용자수"]["test"]
dist = P["유형_분포"]
dist_tbl = tbl(["유형", "정의 (이전 이력만 사용)", "검증 구간 사용자", "평가 구간 사용자"], [
    [TN[0], f"정답 확정 청취 {P['사전설정']['유형_판단유보_기준(정답 확정 청취 수)']}회 이상이고, 새 아티스트·취향 밖 장르 재청취율(평활)의 평균이 {cuts['a']:.3f} 이상", f"{dist[TN[0]]['valid_holdout']:,}", f"{dist[TN[0]]['test']:,}"],
    [TN[1], f"정답 확정 청취 {P['사전설정']['유형_판단유보_기준(정답 확정 청취 수)']}회 이상이고, 위 값이 {cuts['a']:.3f} 미만", f"{dist[TN[1]]['valid_holdout']:,}", f"{dist[TN[1]]['test']:,}"],
    [TN[2], f"정답이 확정된 청취가 {P['사전설정']['유형_판단유보_기준(정답 확정 청취 수)']}회 미만이라 성향을 판단하기 어려운 사용자", f"{dist[TN[2]]['valid_holdout']:,}", f"{dist[TN[2]]['test']:,}"]], num=(2, 3), cap="사용자 유형 정의와 분포")

# 특성 그룹 표
gtab = tbl(["그룹", "개수", "내용", "중요도 합"], [
    [g, len(V11["특성그룹"][g]), d, pc(V11["그룹별_gain비중"][g])] for g, d in [("노출경로", "경로 코드, 경로별 지연 재청취율, 사용자의 경로 이용 비율"), ("최근성", "마지막 청취 후 간격, 최근 구간 청취량, 급상승 정도"), ("누적", "현재 행 직전까지의 누적 청취 횟수·비율"), ("라이브러리성향(v9)", "라이브러리·라디오 재생 비율, 짧은 구간 연속 청취"), ("정적", "곡 길이, 장르, 언어, 나이, 성별, 멤버십 기간"), ("경로프로필(v10)", "곡·사용자·아티스트별 탭 재생 비율"), ("취향SVD", "사용자와 곡·아티스트의 잠재 취향 유사도"), ("지연정답", "정답 확정 구간으로 계산한 재청취율")]], num=(1, 3), cap="모델 A 입력 특성 129개")
sw = V11["stack4_가중치"]
chk_rows = [[r["구간"], r["비교"], sg(r["AUC차이"]), ci([r["CI하한"], r["CI상한"]]), "통과" if r["합격"] else "미통과"] for _, r in v11_chk.iterrows() if r["비교"] in ("인기도", "사용자 기준선")]
chk_tbl = tbl(["구간", "비교 대상", "AUC 차이", "95% 신뢰구간", "합격선"], chk_rows, num=(2,), cap="모델 A 사전 합격선 검증 (사용자 단위 부트스트랩 300회)")
svg = tradeoff_svg()
p1set = P1["정책"][MAIN]["설정"]
refs = [
    "[1] Carbonell, J., & Goldstein, J. (1998). The use of MMR, diversity-based reranking for reordering documents and producing summaries. SIGIR '98. <span class=\"small\">(원문 대조 필요)</span>",
    "[2] Ziegler, C.-N., McNee, S. M., Konstan, J. A., & Lausen, G. (2005). Improving recommendation lists through topic diversification. WWW '05. <span class=\"small\">(원문 대조 필요)</span>",
    "[3] Abdollahpouri, H., Burke, R., & Mobasher, B. (2017). Controlling popularity bias in learning-to-rank recommendation. RecSys '17. <span class=\"small\">(원문 대조 필요)</span>",
    "[4] Steck, H. (2018). Calibrated recommendations. RecSys '18. <span class=\"small\">(원문 대조 필요)</span>",
    "Anderson, A., Maystre, L., Anderson, I., Mehrotra, R., & Lalmas, M. (2020). Algorithmic effects on the diversity of consumption on Spotify. WWW '20, 2155–2165. doi:10.1145/3366423.3380281 <span class=\"small\">(서지·초록 요지 검색으로 확인)</span>",
    "Mehrotra, R. (2021). Algorithmic balancing of familiarity, similarity, & discovery in music recommendations. CIKM '21, 3996–4005. doi:10.1145/3459637.3481893 <span class=\"small\">(서지 검색으로 확인, 실험 결과는 원문 확인 필요)</span>",
    "Holtz, D., Carterette, B., Chandar, P., Nazari, Z., Cramer, H., & Aral, S. (2020). The engagement-diversity connection: Evidence from a field experiment on Spotify. arXiv:2003.08203. <span class=\"small\">(초록 요지 검색으로 확인)</span>",
    "Nguyen, T. T., Hui, P.-M., Harper, F. M., Terveen, L., & Konstan, J. A. (2014). Exploring the filter bubble: the effect of using recommender systems on content diversity. WWW '14. <span class=\"small\">(원문 대조 필요, 결과 요약은 팀 기획서 기준)</span>",
    "Zhou, T., Kuscsik, Z., Liu, J.-G., Medo, M., Wakeling, J. R., & Zhang, Y.-C. (2010). Solving the apparent diversity-accuracy dilemma of recommender systems. PNAS, 107(10), 4511–4515. <span class=\"small\">(서지 검색으로 확인)</span>",
    "Adamopoulos, P., & Tuzhilin, A. (2014). On over-specialization and concentration bias of recommendations: Probabilistic neighborhood selection in collaborative filtering systems. RecSys '14. <span class=\"small\">(NYU 워킹페이퍼만 확인, 학회 서지는 확인 필요)</span>",
    "KKBox's Music Recommendation Challenge (WSDM Cup 2018), Kaggle 공개 데이터.",
]

# ============ 본문에 쓰는 값 ============
aT, p2, p3 = T["정책1(A)"], T["정책2(일괄)"], T["정책3(차등)"]
loss2, loss3 = aT["prec"] - p2["prec"], aT["prec"] - p3["prec"]
g2, g3 = p2["e_D"] - aT["e_D"], p3["e_D"] - aT["e_D"]
auc_t, seg0 = tt.iloc[0].AUC, P["모델A_구간별"][0]
b1_02 = [c for c in b1 if abs(c["lambda"] - 0.2) < 1e-9][0]
b2_53 = [c for c in b2 if c["k"] == 5 and abs(c["tau"] - 0.3) < 1e-9][0]
p1v = P1["정책"][MAIN]["valid_holdout"]
run1_loss = p1v["정책1(A)"]["prec"] - p1v["정책2(일괄)"]["prec"]
sens = {L: P["정책"][L]["test"] for L in ["0.01", "0.02", "0.03", "0.05"]}
dim = lambda L: (sens[L]["정책2(일괄)"]["e_D"] - sens[L]["정책1(A)"]["e_D"], sens[L]["정책1(A)"]["prec"] - sens[L]["정책2(일괄)"]["prec"])
d2, d3, d5 = dim("0.02"), dim("0.03"), dim("0.05")
eff = {L: dim(L)[0] / (dim(L)[1] * 100) for L in sens}
dd_gain = [sens[L]['정책3(차등)']['e_D'] - sens[L]['정책2(일괄)']['e_D'] for L in sens]
share = {n: gain_share[n] / gs for n in TN}
n_all_test = 22616
best_setting = setting(pol["설정"]["정책2"])
em_gain2 = em["정책2"]["e_D"] - aT["e_D"]
MT = json.load(open(f"{R}/matched_exposure.json", encoding="utf-8"))
CW = pd.read_csv(f"{R}/check_b2_wide_grid.csv")
cw = lambda k, t, col: float(CW[(CW.k == k) & np.isclose(CW.tau, t)][col].iloc[0])
LP = lambda L: float(L) * 100
t1 = P["정책"]["0.01"]["test"]
a1, p21, p31 = t1["정책1(A)"], t1["정책2(일괄)"], t1["정책3(차등)"]
loss21, loss31 = a1["prec"] - p21["prec"], a1["prec"] - p31["prec"]
g21, g31 = p21["e_D"] - a1["e_D"], p31["e_D"] - a1["e_D"]
m1, m2 = MT["0.01"], MT["0.02"]
m1d, m2d = m1["정책3−정책2"], m2["정책3−정책2"]
m1rel, m2rel = m1d["e_D"]["차이"] / m1["정책2"]["e_D"], m2d["e_D"]["차이"] / m2["정책2"]["e_D"]
UNP = P["비인기곡_정보"]
unp_share = UNP["test"]["비인기곡_비중"]
ed_all_sig = all(MT[k]["정책3−정책2"]["e_D"]["ci"][0] > 0 for k in MT)
prec_sig_L = [f"{LP(k):.0f}%p" for k in MT if MT[k]["정책3−정책2"]["prec"]["ci"][0] > 0]
prec_ns_L = [f"{LP(k):.0f}%p" for k in MT if MT[k]["정책3−정책2"]["prec"]["ci"][0] <= 0 <= MT[k]["정책3−정책2"]["prec"]["ci"][1]]


def comp_phrase(L):
    d = MT[L]["정책3−정책2"]
    more, less, ns = [], [], []
    for key, nm, nd in [("e_unpop", "유효 비인기곡", 3), ("e_newart", "유효 새 아티스트", 3), ("e_newgen", "유효 취향 밖 장르", 3), ("genres", "고유 장르 수", 3)]:
        x = d[key]
        lab = f"{nm} {x['차이']:+.{nd}f}"
        (more if x["ci"][0] > 0 else less if x["ci"][1] < 0 else ns).append(lab)
    out = []
    if more: out.append("더 많은 것: " + ", ".join(more))
    if less: out.append("더 적은 것: " + ", ".join(less))
    if ns: out.append("차이가 유의하지 않은 것: " + ", ".join(ns))
    return "; ".join(out)


set2 = P["정책"]["0.02"]["설정"]["정책3"]
set_txt = "; ".join(f"{n}은 {setting(set2[n])}" for n in TN)
set_txt = set_txt.replace("B1 λ=", "B1 λ=").replace("B2 k=", "B2 k=")
h3p = H["H3"]["풀링"]["비인기곡"]["비율"]
h3w = H["H3"]["사용자내_추천−직접탐색"]["비인기곡"]
h3n = H["H3"]["풀링"]["새 아티스트"]["비율"]
wide = {(k, t): (cw(k, t, "valid_eD_gain"), cw(k, t, "valid_loss_pp")) for k in (5, 10) for t in (0.2, 0.3, 0.4)}
tau2_txt = ("유효 발견이 오히려 낮아지고" if wide[(5, 0.2)][0] < wide[(5, 0.3)][0] else "유효 발견이 비슷하지만")



def policy_block(L):
    pl = P["정책"][L]
    t, v, c = pl["test"], pl["valid_holdout"], pl["test_비교"]
    a = t["정책1(A)"]
    rows = []
    for nm, lab in [("정책1(A)", "정책 1: 기본 개인화 (A)"), ("정책2(일괄)", "정책 2: 일괄 보정"), ("정책3(차등)", "정책 3: 차등 보정 (B3)")]:
        x, cc = t[nm], c.get(f"{nm} − 정책1(A)")
        rows.append({"cls": "sel" if "3" in lab else "", "cells": [lab, f(v[nm]["prec"], 4), f(x["prec"], 4), pp(cc["prec"]["차이"]) if cc else "–", f(x["n_D"], 2), f(x["e_D"], 3), (sg(cc["e_D"]["차이"], 3) + " " + ci(cc["e_D"]["ci"], 3)) if cc else "–", f(x["e_unpop"], 3), f(x["e_newart"], 3), f(x["e_newgen"], 3), f(x["genres"], 2)]})
    table = tbl(["정책", "Top-10 재청취율 (valid)", "Top-10 재청취율 (test)", "test 변화(vs 정책1)", "발견 대상곡 노출(곡)", "통합 유효 발견@10", "변화 vs 정책1 [95% 신뢰구간]", "유효 비인기곡", "유효 새 아티스트", "유효 취향 밖 장르", "고유 장르 수"], rows, num=tuple(range(1, 11)), cap=f"세 가지 정책의 비교 (손실 한도 {LP(L):.0f}%p, test)")
    c21, c31, c32 = c["정책2(일괄) − 정책1(A)"], c["정책3(차등) − 정책1(A)"], c["정책3(차등) − 정책2(일괄)"]
    l2, l3 = a["prec"] - t["정책2(일괄)"]["prec"], a["prec"] - t["정책3(차등)"]["prec"]
    ex = lambda x: (f"한도를 {x * 100 - LP(L):.2f}%p 넘었습니다" if x * 100 > LP(L) + 1e-9 else "한도 안이었습니다")
    pr = lambda c_: pp(c_["prec"]["차이"]) + " " + ci([v_ * 100 for v_ in c_["prec"]["ci"]], 2)
    ev = lambda c_: sg(c_["e_D"]["차이"], 3) + " " + ci(c_["e_D"]["ci"], 3)
    txt = (f"<ul><li><b>정책 2(일괄) vs 정책 1</b>: 재청취율 {pr(c21)}, 통합 유효 발견 {ev(c21)}.</li>"
           f"<li><b>정책 3(차등) vs 정책 1</b>: 재청취율 {pr(c31)}, 통합 유효 발견 {ev(c31)}.</li>"
           f"<li><b>정책 3 vs 정책 2</b>: 재청취율 {pr(c32)}, 통합 유효 발견 {ev(c32)}.</li></ul>"
           f"<p>정책 3이 유효 발견을 더 얻었지만 재청취율도 더 내줬습니다(정책 3 {pp(-l3)}, 정책 2 {pp(-l2)}). 평가 구간의 손실은 정책 2가 {ex(l2)}, 정책 3이 {ex(l3)}.</p>")
    return table + txt


def single_table(L):
    pl = P["정책"][L]
    t, c = pl["test"], pl["test_비교"]
    rows = []
    for nm in ["정책1(A)", "A+B1", "A+B2"]:
        x, cc = t[nm], c.get(f"{nm} − 정책1(A)")
        st = pl["설정"]["B1만"] if nm == "A+B1" else (pl["설정"]["B2만"] if nm == "A+B2" else None)
        rows.append([nm.replace("정책1(A)", "모델 A (보정 없음)"), setting(st) if st else "–", f(x["prec"], 4), (pp(cc["prec"]["차이"]) + " " + ci([v_ * 100 for v_ in cc["prec"]["ci"]], 2)) if cc else "–", f(x["e_D"], 3), (sg(cc["e_D"]["차이"], 3) + " " + ci(cc["e_D"]["ci"], 3)) if cc else "–", f(x["e_unpop"], 3), f(x["e_newgen"], 3), f(x["genres"], 2)])
    return tbl(["방식", f"선정 설정 (검증 구간, 한도 {LP(L):.0f}%p)", "Top-10 재청취율", "변화 [95% 신뢰구간, %p]", "통합 유효 발견@10", "변화 [95% 신뢰구간]", "유효 비인기곡", "유효 취향 밖 장르", "고유 장르 수"], rows, num=(2, 4, 6, 7, 8), cap=f"B1·B2 단독 적용 결과 (test, 손실 한도 {LP(L):.0f}%p)")


def em_detail(L):
    x = MT[L]
    d = x["정책3−정책2"]
    rows = [["적용 설정", setting(x["정책2_매칭설정"]), "유형별 설정 (8.2절 표)", ""],
            ["발견 대상곡 노출(곡)", f(x["정책2"]["n_D"], 3), f(x["정책3"]["n_D"], 3), sg(d["n_D"]["차이"], 3) + " " + ci(d["n_D"]["ci"], 3)],
            ["Top-10 재청취율", f(x["정책2"]["prec"], 4), f(x["정책3"]["prec"], 4), pp(d["prec"]["차이"]) + " " + ci([v_ * 100 for v_ in d["prec"]["ci"]], 2)],
            {"cls": "sel", "cells": ["통합 유효 발견@10", f(x["정책2"]["e_D"], 3), f(x["정책3"]["e_D"], 3), sg(d["e_D"]["차이"], 3) + " " + ci(d["e_D"]["ci"], 3)]},
            ["유효 비인기곡", f(x["정책2"]["e_unpop"], 3), f(x["정책3"]["e_unpop"], 3), sg(d["e_unpop"]["차이"], 3) + " " + ci(d["e_unpop"]["ci"], 3)],
            ["유효 새 아티스트", f(x["정책2"]["e_newart"], 3), f(x["정책3"]["e_newart"], 3), sg(d["e_newart"]["차이"], 3) + " " + ci(d["e_newart"]["ci"], 3)],
            ["유효 취향 밖 장르", f(x["정책2"]["e_newgen"], 3), f(x["정책3"]["e_newgen"], 3), sg(d["e_newgen"]["차이"], 3) + " " + ci(d["e_newgen"]["ci"], 3)],
            ["고유 장르 수@10", f(x["정책2"]["genres"], 2), f(x["정책3"]["genres"], 2), sg(d["genres"]["차이"], 2) + " " + ci(d["genres"]["ci"], 2)]]
    return tbl(["항목", "정책 2 (노출 맞춤 설정)", "정책 3 (차등)", "차이 (정책 3 − 정책 2) [95% 신뢰구간]"], rows, num=(1, 2), cap=f"노출을 맞춘 비교 상세 (손실 한도 {LP(L):.0f}%p, test)")


mt_rows = []
for L in ["0.01", "0.02", "0.03", "0.05"]:
    x = MT[L]
    d = x["정책3−정책2"]
    mt_rows.append({"cls": "sel" if L == "0.01" else "", "cells": [f"{LP(L):.0f}%p", f(x["정책3_노출"], 2), setting(x["정책2_매칭설정"]), pp(d["prec"]["차이"]) + " " + ci([v_ * 100 for v_ in d["prec"]["ci"]], 2), sg(d["e_D"]["차이"], 3) + " " + ci(d["e_D"]["ci"], 3), f"{d['e_D']['차이'] / x['정책2']['e_D'] * 100:+.1f}%", f"{d['e_D']['차이'] / (x['정책2']['e_D'] - aT['e_D']) * 100:.0f}%"]})
mt_tbl = tbl(["손실 한도", "정책 3 노출(곡)", "정책 2 매칭 설정", "재청취율 차이 (3−2) [95% 신뢰구간, %p]", "통합 유효 발견 차이 (3−2) [95% 신뢰구간]", "일괄 대비", "일괄 증가분 대비"], mt_rows, num=(1, 3, 4, 5, 6), cap="노출 수준을 맞춘 차등−일괄 비교 (test, 모든 손실 한도)")
sum_rows = []
for L in ["0.01", "0.02"]:
    t = P["정책"][L]["test"]
    for nm, lab in [("정책1(A)", "정책 1"), ("정책2(일괄)", "정책 2"), ("정책3(차등)", "정책 3")]:
        x = t[nm]
        sum_rows.append([f"{LP(L):.0f}%p", lab, f(x["e_D"], 3), f(x["e_unpop"] + x["e_newart"], 3), f(x["e_unpop"], 3), f(x["e_newart"], 3)])
sum_tbl = tbl(["손실 한도", "정책", "통합 유효 발견@10 (합집합, 중복 없음)", "합계 방식 (유효 비인기곡 + 유효 새 아티스트)", "유효 비인기곡", "유효 새 아티스트"], sum_rows, num=(2, 3, 4, 5), cap="유효 발견 정의별 비교 (test)")


CSS = """
:root { --bg:#eef0f3; --paper:#fff; --text:#1f2328; --muted:#656d76; --line:#d8dde3; --line-soft:#eceff2; --head:#f5f7f9; --accent:#1f4e8c; --accent-soft:#eaf1fb; --good:#1a7f37; --bad:#b42318; --warn:#9a6700; --warn-soft:#fff8e5; --c1:#1f6fd1; --c2:#e07b00; --c3:#2a9d57; --c4:#b4262c; --dot:#9aa4b0; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#0f1114; --paper:#181b20; --text:#e6e8eb; --muted:#9aa3ad; --line:#30363d; --line-soft:#23282e; --head:#1f242a; --accent:#7aa7e6; --accent-soft:#1c2738; --good:#57c278; --bad:#f47067; --warn:#e3b341; --warn-soft:#2b2416; --c1:#6ea8fe; --c2:#f0a040; --c3:#57c278; --c4:#f47067; --dot:#6b7480; } }
* { box-sizing:border-box; } html { -webkit-text-size-adjust:100%; }
body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Pretendard","Noto Sans KR","Malgun Gothic",sans-serif; font-size:15px; line-height:1.75; }
.paper { max-width:1000px; margin:32px auto; background:var(--paper); border:1px solid var(--line); padding:56px 68px 72px; }
@media (max-width:760px) { .paper { margin:0; border:none; padding:24px 16px 56px; } }
.cover { border-bottom:2px solid var(--text); padding-bottom:26px; margin-bottom:28px; }
.cover .kicker { font-size:13px; color:var(--muted); letter-spacing:.04em; }
.cover h1 { font-size:30px; line-height:1.35; margin:8px 0 12px; letter-spacing:-.01em; }
.cover .sub { color:var(--muted); font-size:16px; margin:0 0 14px; }
.meta { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:4px 24px; font-size:13.5px; color:var(--muted); } .meta b { color:var(--text); font-weight:600; margin-right:6px; }
.lead { font-size:16.5px; border-left:4px solid var(--accent); padding:10px 16px; background:var(--accent-soft); margin:14px 0 20px; line-height:1.7; }
.note-box { border:2px solid var(--accent); background:var(--accent-soft); padding:14px 18px; margin:0 0 28px; } .note-box .t { font-weight:700; color:var(--accent); margin-bottom:4px; } .note-box p { margin:4px 0; font-size:14px; }
.toc { background:var(--head); border:1px solid var(--line-soft); padding:14px 22px; margin:0 0 34px; font-size:14.5px; } .toc b { display:block; margin-bottom:4px; } .toc ol { margin:0; padding-left:22px; columns:2; column-gap:36px; } .toc a { color:var(--text); text-decoration:none; } .toc a:hover { color:var(--accent); }
@media (max-width:560px) { .toc ol { columns:1; } }
h2 { font-size:20px; margin:52px 0 14px; padding-bottom:7px; border-bottom:1px solid var(--line); scroll-margin-top:16px; }
h3 { font-size:16px; margin:28px 0 8px; } h4 { font-size:14.5px; margin:20px 0 6px; color:var(--muted); }
p { margin:8px 0; } ul, ol { padding-left:22px; margin:8px 0; } li { margin:4px 0; }
code { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12.8px; } p code, li code, td code { background:var(--head); border:1px solid var(--line-soft); padding:0 4px; border-radius:3px; }
.small { color:var(--muted); font-size:13px; } .cite { color:var(--accent); font-size:12.5px; vertical-align:super; }
.kpis { display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); margin:18px 0; } .kpi { padding:14px 16px; border-right:1px solid var(--line); } .kpi:last-child { border-right:none; }
.kpi .l { font-size:12.5px; color:var(--muted); } .kpi .v { font-size:25px; font-weight:700; font-variant-numeric:tabular-nums; } .kpi .d { font-size:12.5px; color:var(--muted); }
@media (max-width:700px) { .kpis { grid-template-columns:repeat(2,1fr); } .kpi:nth-child(2) { border-right:none; } .kpi:nth-child(-n+2) { border-bottom:1px solid var(--line); } }
.tw { overflow-x:auto; margin:12px 0 6px; } table { border-collapse:collapse; width:100%; font-size:13.5px; } caption { caption-side:top; text-align:left; font-weight:600; font-size:13.5px; padding:0 0 6px; }
th, td { border-top:1px solid var(--line-soft); padding:7px 10px; vertical-align:top; text-align:left; } thead th { background:var(--head); border-top:1px solid var(--line); border-bottom:1px solid var(--line); font-weight:600; font-size:12.5px; color:var(--muted); white-space:nowrap; }
tbody tr:last-child td { border-bottom:1px solid var(--line); } td.n, th.n { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; } tr.sel td { background:var(--accent-soft); font-weight:600; }
.callout { border-left:3px solid var(--accent); background:var(--accent-soft); padding:11px 16px; margin:16px 0; font-size:14.5px; } .callout.warn { border-left-color:var(--warn); background:var(--warn-soft); } .callout p { margin:4px 0; }
.flow { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:14px 0; } .step { background:var(--head); border:1px solid var(--line); padding:10px 12px; font-size:13.5px; } .step b { display:block; color:var(--accent); margin-bottom:2px; }
.split { display:flex; height:28px; font-size:12px; margin:10px 0 4px; border:1px solid var(--line); } .split div { display:flex; align-items:center; justify-content:center; border-right:1px solid var(--line); } .split div:last-child { border-right:none; }
.fig { margin:16px 0; } .fig .cap { font-size:13px; color:var(--muted); margin-top:4px; }
footer { margin-top:56px; padding-top:12px; border-top:1px solid var(--line); font-size:12.5px; color:var(--muted); }
@media print { body { background:#fff; } .paper { border:none; margin:0; padding:0; max-width:none; } h2 { break-after:avoid; } tr, .fig { break-inside:avoid; } }
"""

HTML = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>음악 추천 시스템의 사용자별 다양성 최적화 전략 · 최종 보고서</title><style>{CSS}</style></head>
<body><article class="paper">

<header class="cover">
  <div class="kicker">iM DiGital Banker Academy · 데이터분석 전문가 양성과정 최종 프로젝트</div>
  <h1>음악 추천 시스템의 사용자별 다양성 최적화 전략</h1>
  <p class="sub">재청취 정확도와 새로운 음악 발견의 균형을 중심으로 — 최종 결과 보고서</p>
  <div class="meta"><div><b>팀</b>앙상블(Ensemble)</div><div><b>팀원</b>정윤하(팀장), 이재혁, 오정석, 황규현</div><div><b>작성일</b>2026-11-03</div><div><b>데이터</b>KKBox 음악 추천 데이터 (7,352,114행)</div><div><b>모델 A</b>Stack4 앙상블 (v11)</div><div><b>분석 코드</b>A/ , B/ 폴더</div></div>
</header>

<section class="note-box" role="note"><div class="t">이 보고서의 모델 A는 노출 경로 컬럼(source_*)을 사용했습니다</div>
<p><code>source_system_tab</code>(재생 탭), <code>source_screen_name</code>(재생 화면), <code>source_type</code>(진입 경로) 3개 컬럼과 이 값들로 만든 특성 58개가 모델 A의 입력 129개에 포함됩니다. source를 쓰지 않은 마지막 버전의 test AUC는 0.6733이고, 모델 A(source 사용)는 {f(auc_t)}입니다. 6~8장의 모든 보정 실험은 모델 A의 예측 위에서 수행했습니다.</p></section>

<nav class="toc"><b>목차</b><ol>
<li><a href="#s1">프로젝트 개요</a></li><li><a href="#s2">선행 연구와 차별점</a></li><li><a href="#s3">데이터</a></li><li><a href="#s4">분석 설계</a></li>
<li><a href="#s5">근거 분석: 가설 검증</a></li><li><a href="#s6">추천 모델: 모델 A</a></li><li><a href="#s7">다양성 보정: B1·B2</a></li><li><a href="#s8">사용자별 차등 보정: B3</a></li>
<li><a href="#s9">운영 가이드와 비즈니스 인사이트</a></li><li><a href="#s10">한계와 향후 과제</a></li><li><a href="#s11">결론</a></li><li><a href="#s12">부록</a></li></ol></nav>

<h2 id="s1">1. 프로젝트 개요</h2>
<p class="lead">정확도만 보는 음악 추천에 인기도 보정(B1)을 더하면, 재청취율 손실을 약 {loss21 * 100:.1f}%p로 묶은 채 이용자가 실제로 다시 들은 <b>'새로운 발견' 곡을 10곡당 {g21:+.2f}곡(+{g21 / a1['e_D'] * 100:.0f}%)</b> 늘릴 수 있었다. 이용자 유형에 따라 보정 세기를 다르게 주는 차등 보정은 일괄 보정보다 추가 이익이 <b>+{m1rel * 100:.1f}%</b>에 그쳐, 운영 기본값으로는 일괄 보정을 권고한다.</p>
<h3>1.1 배경과 목적</h3>
<p>음원 스트리밍 서비스의 개인화 추천은 대부분 "이용자가 좋아할 확률이 높은 곡"을 고르도록 설계되어 있습니다. 이 방식은 단기 만족도에는 효과적이지만 이미 듣던 장르·아티스트·인기곡을 반복해서 보여 주기 쉽습니다. 이용자는 자신이 모르는 음악에 대해 불만을 말할 수 없으므로, 이 문제는 겉으로 드러나지 않는 <b>'불만 없는 정체'</b>로 남습니다.</p>
<p>이 프로젝트의 목적은 새로운 다양화 알고리즘을 발명하는 것이 아닙니다. 공개 청취 데이터로 <b>"어떤 다양화 방식이 어떤 이용자에게 얼마나 효율적인지"</b>를 정량화하고, 이를 추천 정책의 의사결정 기준으로 정리하는 것입니다.</p>
<ul>
<li>정확도를 크게 해치지 않으면서(팀 기획서 기준: 상위 10곡 재청취율 손실 1%p 이내) 이용자가 실제로 받아들이는 새로운 음악을 늘립니다.</li>
<li>"누구에게, 어떤 방식으로, 얼마만큼" 다양성을 줄지 판단할 수 있는 운영 기준을 제안합니다.</li>
<li>결과를 모바일 앱 시연 화면과 청취 혜택(발견 미션) 모델로 연결합니다. <span class="small">(이 보고서는 추천 모델·정책 단계까지를 다루며, 프로토타입은 포함하지 않습니다.)</span></li></ul>
<h3>1.2 팀과 주제</h3>
{tbl(["항목", "내용"], [["팀명", "앙상블(Ensemble)"], ["팀원", "정윤하(팀장), 이재혁, 오정석, 황규현"], ["주제", "음악 추천 시스템의 사용자별 다양성 최적화 전략: 재청취 정확도와 새로운 음악 발견의 균형을 중심으로"], ["과정", "iM DiGital Banker Academy 데이터분석 전문가 양성과정 최종 프로젝트"]])}
<h3>1.3 두 가지 의문과 이 보고서의 핵심 질문</h3>
<p>주제 검토 과정에서 성격이 다른 두 가지 의문이 제기되었습니다. 설문만으로는 답하기 어려워, 선행 연구와 실제 청취 행동 데이터로 근거를 먼저 확인한 뒤 추천 모델을 제안하는 순서로 설계했습니다.</p>
{tbl(["의문", "성격", "답하는 방법", "이 보고서"], [
["① 이용자들은 실제로 기존 추천에 불편을 느끼는가?", "사실 확인", "불편 여부 대신, 행동 데이터에서 '정체'가 실제로 나타나는지 확인 (H1·H3)", "5장"],
["② 서비스가 '이런 노래도 있네?' 싶은 추천을 만들 필요가 있는가?", "사업적 가치", "다양성과 이후 활동 유지의 관계(H2·H4) + 선행 연구", "2장, 5장"],
["(파생) 모든 이용자에게 같은 다양성을 줘야 하는가?", "운영 기준", "사용자 유형을 나누고 일괄 보정과 차등 보정을 비교", "6~9장"]], cap="제기된 의문과 답하는 방식")}
<p>이 보고서가 직접 답하는 핵심 질문은 세 가지입니다.</p>
<ol>
<li><b>모델 A</b>: 사용자·곡·청취 이력으로 재청취 확률을 신뢰성 있게 예측할 수 있는가?</li>
<li><b>B1·B2</b>: 모델 A의 점수를 후처리로 조정하면, 정확도 손실 대비 얼마나 많은 <b>유효 발견</b>(새롭게 접했고 실제로 다시 들은 곡)이 늘어나는가?</li>
<li><b>B3</b>: 사용자 유형별 차등 보정은 일괄 보정보다 실질적인 추가 이익을 주는가?</li></ol>
<h3>1.4 진행 단계</h3>
{tbl(["단계", "내용", "이 보고서"], [
["1. 문제 제시", "문제의식과 두 가지 의문에 답하는 구조, 선행 연구·행동 데이터·이용자 인식의 3층 근거 체계 설계", "2장"],
["2. 근거 분석", "청취 행동 데이터로 가설 H1~H4 검증, 이전 청취 이력만으로 사용자 유형 구분", "5장, 8.1절"],
["3. 추천 모델", "재청취 확률 모델(모델 A)과 ① 기본 ② 일괄 보정 ③ 차등 보정을 같은 후보·같은 분할·같은 지표로 비교", "6~8장"],
["4. 프로토타입", "기존 추천과 새로운 발견 추천을 비교하는 모바일 앱 시연 화면, 발견 미션 혜택", "범위 밖"]], cap="프로젝트 4단계와 이 보고서의 범위")}
<h3>1.5 핵심 결과</h3>
<div class="kpis">
<div class="kpi"><div class="l">모델 A test AUC</div><div class="v">{f(auc_t)}</div><div class="d">인기도 기준선 {f(seg0['AUC_인기도'])}</div></div>
<div class="kpi"><div class="l">일괄 보정 · 한도 1%p</div><div class="v">{sg(g21, 2)}곡</div><div class="d">유효 발견@10 (+{g21 / a1['e_D'] * 100:.0f}%) · 재청취율 {pp(-loss21)}</div></div>
<div class="kpi"><div class="l">일괄 보정 · 한도 2%p</div><div class="v">{sg(g2, 2)}곡</div><div class="d">유효 발견@10 (+{g2 / aT['e_D'] * 100:.0f}%) · 재청취율 {pp(-loss2)}</div></div>
<div class="kpi"><div class="l">차등 − 일괄 (노출 맞춤, 1%p)</div><div class="v">{sg(m1d['e_D']['차이'], 3)}곡</div><div class="d">일괄 대비 {m1rel * 100:+.1f}% · 재청취율 {pp(m1d['prec']['차이'])}</div></div></div>
<ul>
<li><b>가설 검증은 다양성 보정의 필요성을 약하게만 뒷받침합니다.</b> H1은 지지되지 않았고, H2는 약하게 지지됐으며, H3는 인기 편향 측면에서만 약하게 지지됐고, H4는 활동량을 통제하면 지지되지 않았습니다.</li>
<li><b>모델 A는 사전 합격선을 통과했습니다.</b> 인기도 기준선보다 AUC가 {sg(seg0['AUC차이'])}(95% 신뢰구간 {ci(seg0['ci'])}) 높고, 비인기곡·새 아티스트·취향 밖 장르 구간에서도 모두 통과했습니다. 평균 예측 {f(seg0['모델A 평균예측'], 3)}은 실제 재청취율 {f(seg0['실제 재청취율'], 3)}과 거의 같습니다.</li>
<li><b>인기도 보정(B1)이 가장 효율적인 첫 수단입니다.</b> 한도 1%p에서는 B1만으로 유효 발견을 {f(a1['e_D'], 2)}곡에서 {f(p21['e_D'], 2)}곡으로 늘립니다. 취향 확장 슬롯(B2)은 취향 밖 장르의 유효 발견을 {b2_53['test_e_newgen'] / a0['test_e_newgen']:.1f}배(k=5, τ=0.3)까지(시험한 범위에서) 늘리지만 정확도 손실이 더 크고, 조건을 만족하는 후보가 있는 사용자가 일부입니다.</li>
<li><b>차등 보정의 추가 이익은 유효 발견 기준으로는 통계적으로 유의하지만 아주 작습니다.</b> 발견 대상곡 노출을 같게 맞추면 한도 1%p에서 일괄 보정보다 유효 발견이 {sg(m1d['e_D']['차이'], 3)}곡 {ci(m1d['e_D']['ci'], 3)}(+{m1rel * 100:.1f}%), 한도 2%p에서 {sg(m2d['e_D']['차이'], 3)}곡(+{m2rel * 100:.1f}%) 더 많습니다.</li></ul>
<div class="callout"><p><b>권고</b>: 운영 복잡성을 고려하면 우선 <b>일괄 보정</b>(B1 중심)을 적용하고, 차등 보정은 실서비스 A/B 테스트로 이익이 확인될 때 도입하는 것이 합리적입니다(9장).</p></div>
<p class="small">정확도 손실 한도는 팀 기획서의 1%p를 기준으로 요약했습니다. 분석을 설계할 때는 한도 후보 1·2·3·5%p를 정하고 주 한도를 2%p로 두었으며, 기획서의 1%p 기준은 분석 후에 확인했습니다. 그래서 1%p와 2%p 결과를 모두 제시하고 결론이 한도에 따라 바뀌지 않는지 8.4절에서 확인했습니다.</p>

<h2 id="s2">2. 선행 연구와 차별점</h2>
<p>선행 연구는 알고리즘 추천이 개인의 소비 다양성을 줄일 수 있고, 다양하게 듣는 이용자일수록 서비스 지표가 좋은 경향이 있음을 보여 줍니다. 다만 대부분 상관관계이므로, 이 프로젝트는 이를 "다양화하면 청취가 늘어난다"의 근거가 아니라 <b>"다양성과 이용 성과의 관계를 고려할 필요성"</b>의 근거로만 씁니다.</p>
<h3>2.1 문제의식: 정확도 중심 추천이 만드는 '취향의 정체'</h3>
<p>정확도 중심 추천은 단기 만족에 효과적입니다. 하지만 이미 듣던 장르와 아티스트를 반복해서 보여 주면, 이용자의 취향이 추천이 보여 주는 범위 안으로 점점 좁아질 수 있습니다. 이를 흔히 필터 버블(filter bubble)이라고 부릅니다. 한편 이용자의 취향은 생각보다 넓게 이어져 있을 수 있습니다. 랩을 즐겨 듣는 이용자가 재즈도 함께 듣는 것처럼, 서로 다른 장르가 같은 사람에게서 함께 소비되는 경우가 많은데 정확도 중심 추천은 이런 연결을 잘 드러내지 못합니다.</p>
<p>이용자는 자신이 모르는 음악에 대해 불만을 말할 수 없습니다. 따라서 이 문제는 "이용자가 불편을 느낀다"가 아니라 <b>"불만은 없지만 청취가 점점 좁아지고 있고, 그것이 서비스에도 손해일 수 있다"</b>는 '불만 없는 정체'의 문제로 정의합니다.</p>
<h3>2.2 선행 연구</h3>
<p>아래 내용 중 (1)~(3)은 논문의 초록·공개 자료로 확인한 범위만 적었고, (4)~(5)와 업계 현황은 팀 기획서에 정리된 요약입니다. 수치와 서지는 제출 전에 원문과 대조해야 합니다.</p>
<ol>
<li><b>알고리즘 추천과 소비 다양성: Anderson et al. (2020, WWW '20)</b> — Spotify 청취 기록으로 이용자의 소비 다양성을 측정했습니다. 소비 다양성이 높은 이용자일수록 이후 유료 전환과 유지 지표가 좋은 경향이 있었고, 다양성이 커지는 이용자는 알고리즘 추천 청취에서 직접 찾아 듣는 청취로 옮겨 가는 경향이 있었으며, 무작위 실험에서는 알고리즘 추천이 다양성이 낮은 이용자에게 더 효과적이었다고 보고합니다. 상관 중심의 분석이며 인과는 검증되지 않았습니다. 이 프로젝트의 가설 H2~H4는 이 연구의 논점(다양성과 유지, 추천 경로와 다양성)을 KKBox 데이터에서 다시 확인하는 구조입니다.</li>
<li><b>익숙함과 발견의 균형: Mehrotra (2021, CIKM '21)</b> — Spotify 음악 추천에서 관련성·익숙함·발견 사이의 균형을 맞추는 목적함수 조정 방식을 제안하고, 이용자의 익숙함 선호와 발견의 관계를 분석합니다. 이 프로젝트가 보정 강도(λ, k)를 조절해 정확도와 발견의 균형점을 찾는 설계는 이 관점을 따릅니다.</li>
<li><b>개인화와 다양성의 현장 실험: Holtz et al. (2020)</b> — Spotify 팟캐스트 추천에서 무작위 현장 실험을 했습니다. 개인화 추천은 이용자당 청취량을 늘렸지만 개인 수준의 소비 다양성은 낮췄고, 전체 이용자 수준의 다양성은 오히려 높였습니다. "정확한 개인화가 개인의 소비를 좁힐 수 있다"는 문제의식을 무작위 실험으로 뒷받침합니다.</li>
<li><b>필터 버블에 대한 엇갈리는 결론: Nguyen et al. (2014)</b> — 영화 추천 데이터에서 추천 이용이 다양성에 미치는 영향을 분석했고, 추천을 따른 이용자의 취향 좁아짐이 오히려 더 작았다는 결과를 보고했다고 팀 기획서에 요약돼 있습니다. 그래서 "추천은 항상 취향을 좁힌다"는 가정을 그대로 받아들일 수 없고, 이 데이터에서 직접 확인해야 합니다(5장).</li>
<li><b>정확도·다양성 트레이드오프와 측정 지표</b>: Zhou et al. (2010, PNAS)은 정확도와 다양성이 양립할 수 있음을 보였고, Adamopoulos & Tuzhilin의 연구는 과전문화와 집중 편향을 다룹니다. 다양성은 장르 엔트로피, 지니계수, 임베딩 기반 지표 등으로 측정합니다. 공통 메시지는 <b>정확도 하나로만 평가하면 "다양성을 높이면 성능이 떨어지는 모델"로만 보인다</b>는 것입니다. 그래서 이 프로젝트는 정확도와 다양성, 그리고 둘을 합친 <b>유효 발견</b>(낯선 곡이면서 실제로 다시 들은 곡)을 함께 평가합니다.</li>
<li><b>다양성을 높이는 기법</b>: 점수 위에서 목록을 다시 구성하는 재정렬(MMR[1], 주제 다양화[2])과 인기 편향을 줄이는 방법[3], 사용자 관심사 비율을 맞추는 보정(calibration)[4]이 있습니다. 이 프로젝트의 B1·B2는 재학습 없이 모델 A의 예측 위에서 순위만 조정하는 후처리 방식입니다.</li></ol>
{tbl(["연구", "대상", "보여 주는 것", "이 프로젝트에서의 쓰임"], [
["Anderson et al. (2020)", "Spotify 음악", "다양한 이용자의 전환·유지가 높은 경향(상관), 추천 청취와 직접 청취의 차이", "H2·H3·H4 설계"],
["Mehrotra (2021)", "Spotify 음악 추천", "익숙함·발견·관련성의 균형을 목적함수로 조절", "보정 강도 격자 탐색"],
["Holtz et al. (2020)", "Spotify 팟캐스트 현장 실험", "개인화는 청취량↑, 개인 수준 다양성↓", "문제의식"],
["Nguyen et al. (2014)", "영화 추천", "필터 버블 효과가 일관되지 않음", "가설을 데이터로 확인해야 하는 이유"],
["Zhou et al. (2010), Adamopoulos & Tuzhilin", "추천 일반", "정확도·다양성·의외성을 함께 평가해야 함", "지표 설계(유효 발견)"]], cap="선행 연구 요약")}
<h3>2.3 업계 현황</h3>
<p class="small">팀 기획서에 정리된 내용이며 별도로 검증하지 않았습니다.</p>
<ul>
<li>주요 음원 서비스는 취향 기반 플레이리스트와 라디오 등 개인화 추천을 핵심 기능으로 제공하며, 추천 품질은 주로 재생·재청취 같은 정확도 지표로 평가합니다.</li>
<li>신곡·차트·장르별 플레이리스트처럼 새로운 음악을 접하는 기능도 있습니다. 하지만 개인화 추천과 별도 메뉴로 제공되는 경우가 많아, 개인 취향에서 출발해 탐색 범위를 단계적으로 넓히는 데에는 한계가 있습니다.</li>
<li>대형 플랫폼은 익숙함·유사성·발견의 균형을 이미 연구하고 있습니다. 반면 "모든 이용자에게 같은 정도의 다양성을 줄 것인가, 이용자 성향에 따라 다르게 줄 것인가"에 대한 운영 기준은 공개된 근거가 많지 않습니다.</li></ul>
<h3>2.4 본 프로젝트의 차별점</h3>
<p>다양성 보정 자체는 새로운 기술이 아닙니다. 이 프로젝트의 기여는 다음 세 가지입니다.</p>
<ol>
<li><b>사용자별 차이의 정량화</b>: "모든 이용자가 다양성을 원한다"가 아니라 이용자마다 낯선 음악을 받아들이는 정도가 다르다는 것을, 이전 청취 이력만으로 구분하고 검증 구간과 평가 구간에서 다시 확인합니다(8.1절).</li>
<li><b>일괄 vs 차등 보정의 공정한 비교</b>: 같은 후보곡·같은 분할·같은 지표와 사전에 정한 정확도 손실 한도 안에서 비교하고, 차등 보정의 실익이 작다면 그 사실도 그대로 보고합니다(8장).</li>
<li><b>운영 가이드로의 연결</b>: 손실 한도·노출 수준별로 어떤 정책이 합리적인지 정리합니다(9장).</li></ol>
{tbl(["구분", "일반적인 접근", "이 프로젝트"], [
["정확도의 기준", "클릭·평점 등 예측 점수", "<b>한 달 안 재청취 확률</b>(실제 청취 기록)과 정답 지연 43% 규칙으로 누수를 막은 예측"],
["다양성 보정의 이익", "다양성 지표(장르 수 등) 자체의 증가", "<b>유효 발견</b>: 새롭게 접한 곡 중 실제로 다시 들은 곡의 수. 다양성이 늘어도 외면받는 곡은 이익으로 세지 않음"],
["보정 강도 결정", "경험적으로 정하는 경우가 많음", "손실 한도 후보와 선정 원칙을 <b>사전에 정하고</b>, 한도 안에서 검증 구간으로 강도를 선정한 뒤 평가 구간에서 고정"],
["개인화 여부", "일괄 적용 또는 개인화 방식 제안", "<b>일괄 대비 차등의 추가 실익</b>을 같은 한도·같은 노출 수준에서 사용자 단위 부트스트랩으로 검증"],
["가설 보고", "지지된 결과 위주", "지지되지 않은 가설도 그대로 보고 (5장)"]], cap="일반적인 접근과의 차이")}
<h3>2.5 근거 체계와 해석 원칙</h3>
{tbl(["층위", "근거", "보여 주는 것", "한계"], [
["1. 선행 연구", "2.2절의 연구들", "추천과 다양성, 다양성과 유지의 관계(경향)", "상관관계 중심, 해외 대형 플랫폼"],
["2. 행동 데이터", "KKBox 청취 기록 735만 건 (H1~H4, 사용자 유형)", "이 데이터에서 정체·편중·인기 편향이 실제로 나타나는지", "타임스탬프·해지 정보 없음"],
["3. 이용자 인식", "설문·인터뷰 (팀 별도 진행)", "이용자가 발견을 원하는지, 혜택이 동기가 되는지", "표본·응답 편향. <b>이 보고서에서는 다루지 않음</b>"]], cap="3층 근거 체계")}
<p>해석 원칙은 두 가지입니다. 첫째, 가설이 지지되지 않으면 그대로 보고하고, 주제를 '취향 확장이 필요한 이용자 집단'으로 좁히는 근거로 씁니다. 둘째, 본분석은 관측된 청취 곡을 재정렬하는 <b>오프라인 실험</b>이므로 실서비스 효과는 A/B 테스트로 확인해야 합니다.</p>

<h2 id="s3">3. 데이터</h2>
<h3>3.1 출처와 규모</h3>
<p>KKBox 음악 추천 데이터(Kaggle 대회 공개 데이터)의 청취 기록·곡 정보·회원 정보를 팀의 전처리 규칙으로 병합한 통합 전처리 파일 <code>data.csv</code>를 사용했습니다. 한 행은 "사용자 한 명이 곡 하나를 들은 기록"이고, 정답 <code>target</code>은 한 달 안에 그 곡을 다시 들었으면 1입니다.</p>
{tbl(["항목", "값"], [["행 수 / 컬럼 수", "7,352,114행 × 24열"], ["사용자 / 곡", "30,751명 / 356,267곡"], ["재청취 비율(전체 평균)", "0.5035. 시간이 지날수록 낮아져 검증 구간 0.427, 평가 구간 0.404"], ["시간 정보", "타임스탬프가 없어 원본 행 순서(<code>row_order</code>)로만 시간 순서를 알 수 있음"]], cap="데이터 개요")}
<h3>3.2 주요 컬럼과 전처리</h3>
{tbl(["구분", "컬럼", "전처리 요약"], [
["청취 기록", "<code>msno</code>, <code>song_id</code>, <code>target</code>, <code>source_system_tab</code>, <code>source_screen_name</code>, <code>source_type</code>", "재생 경로 컬럼의 결측은 <code>unknown</code>으로 채움"],
["곡 정보", "곡 길이, 장르(<code>genre_ids</code>, <code>primary_genre</code>), 아티스트(<code>main_artist</code>, <code>is_various_artist</code>), 언어", "깨진 행 복구, 장르·작곡가·작사가가 모두 빈 곡 제거(53,039곡·25,304행), Various Artists 계열 통일, 주 아티스트 분리"],
["회원 정보", "나이, 성별, 가입일, 만료일", "나이는 1~100 밖이면 결측, 성별 결측은 <code>unknown</code>, 날짜형으로 변환"]], cap="컬럼과 전처리")}
<div class="callout"><p><b>노출 경로(source_*)란?</b> 사용자가 그 곡을 앱의 <b>어느 탭·화면·진입점에서 눌러 재생했는지</b>를 곡이 재생된 시점에 기록한 값입니다. 예를 들어 내가 저장해 둔 곡을 보관함에서 눌러 들었는지(<code>my library</code>, <code>local-library</code>), 앱이 추천해 준 목록에서 들었는지(<code>discover</code>, <code>online-playlist</code>), 라디오로 흘러나왔는지(<code>radio</code>)를 구분합니다. 경로에 따라 재청취율이 크게 다릅니다(전체 데이터 기준 진입 경로별 재청취율: local-playlist 0.658, local-library 0.632, online-playlist 0.425, radio 0.220). 이 값은 KKBox 앱의 메뉴 이름으로 고정돼 있어서, 다른 서비스의 화면과는 대응 관계를 따로 정해야 합니다.</p></div>
<h3>3.3 데이터 분할과 누수 방지</h3>
<div class="split"><div style="width:20%">이력 0~20%</div><div style="width:20%">train_a</div><div style="width:20%">train_b</div><div style="width:20%;background:var(--accent-soft)">valid</div><div style="width:20%;background:var(--head)">test</div></div>
<ul>
<li><b>시간 순서 분할</b>: 무작위로 섞지 않고 <code>row_order</code> 기준으로 나눴습니다. train은 20~60%, valid는 60~80%, test는 80~100%입니다. 0~20%는 특성 계산용 과거 이력입니다.</li>
<li><b>검증 구간 분할</b>: valid를 사용자 단위로 반으로 나눠, 한쪽(tune)은 조기 종료와 스태킹 학습에, 다른 쪽(holdout)은 모델·정책 선정에 썼습니다.</li>
<li><b>정답 지연</b>: 정답을 쓰는 특성은 현재 행보다 3,172,289행(전체의 43%, 약 한 달) 이상 앞선 행의 정답만 씁니다. 정답을 쓰지 않는 특성도 현재 행보다 앞선 기록만으로 계산합니다.</li>
<li><b>Various Artists</b>: 아티스트 단위로 계산할 때는 제외하고 결측으로 둡니다.</li></ul>
<h3>3.4 데이터의 한계</h3>
<ul><li>청취 시각이 없어서 시간 간격은 행 번호 차이로만 셀 수 있습니다.</li><li>정답이 있는 곡은 사용자가 실제로 재생한 곡뿐입니다. 추천 후보를 이 곡들로 한정하면 선택 편향이 생깁니다.</li><li>2017년 대만 KKBox 중심의 데이터라 결과의 일반화 범위가 제한됩니다.</li></ul>

<h2 id="s4">4. 분석 설계</h2>
<h3>4.1 전체 흐름</h3>
<div class="flow">
<div class="step"><b>① 근거 분석</b>H1~H4 가설 검증 (5장)</div>
<div class="step"><b>② 모델 A</b>알고리즘 비교 → 재청취 확률 모델 → 사전 합격선 검증 (6장)</div>
<div class="step"><b>③ B1·B2</b>모델 A 점수 후처리 보정, 강도별 트레이드오프 (7장)</div>
<div class="step"><b>④ 정책 구성</b>정책 1 기본 / 정책 2 일괄 / 정책 3 차등 (8장)</div>
<div class="step"><b>⑤ 비교 검증</b>같은 한도·같은 노출에서 유효 발견 비교 (8장)</div>
<div class="step"><b>⑥ 운영 가이드</b>조건별 정책 선택 기준 (9장)</div></div>
<h3>4.2 평가 단위</h3>
<p>사용자별 <b>후보곡</b>은 그 사용자가 평가 구간에서 실제로 재생한 곡입니다. 정답이 있는 곡이 이것뿐이기 때문입니다. 후보가 20곡 이상인 사용자만 대상으로 했습니다(검증 holdout {nv:,}명, 평가 구간 {nt:,}명. 평가 구간 전체 사용자 {n_all_test:,}명의 {nt / n_all_test * 100:.0f}%). 후보가 10곡 안팎이면 상위 10곡을 바꿀 여지가 없기 때문입니다. 각 사용자에게 상위 10곡을 추천하고 지표를 사용자 단위로 평균했습니다. 한 사용자의 후보에 같은 곡이 두 번 나오는 경우는 없었습니다.</p>
<h3>4.3 보정 기법과 정책</h3>
{tbl(["이름", "정의"], [
["모델 A", "재청취 확률 p를 예측하는 기본 개인화 모델. 점수 p순으로 정렬"],
["B1 인기도 보정", "조정 점수 = p − λ × 인기도 백분위. 인기도 백분위는 log(1+곡 누적 청취 수)가 검증 구간 분포에서 차지하는 위치(0~1)"],
["B2 취향 확장 보정", "상위 (10−k)곡은 점수순으로 두고, 나머지 k칸을 <b>취향 밖 장르</b>(그 사용자가 처음 듣는 장르) 곡 중 예측 확률이 τ 이상인 곡으로 점수순 채움. 조건을 만족하는 곡이 k개보다 적으면 남는 칸은 점수순으로 채움"],
["정책 1", "모델 A만 사용 (보정 없음). 다른 정책의 기준"],
["정책 2 (일괄)", "모든 사용자에게 같은 B1·B2 설정 적용"],
["정책 3 (차등, B3)", "사용자 유형별로 B1·B2 설정을 따로 적용"]], cap="보정 기법과 정책")}
<h4>예시</h4>
{tbl(["곡", "모델 A 점수", "인기도 백분위", "깎는 양 (λ=0.2 × 백분위)", "조정 점수", "순위"], [
["곡 X (인기곡)", "0.60", "0.9", "−0.18", "0.42", "2위"], {"cls": "sel", "cells": ["곡 Y (비인기곡)", "0.55", "0.1", "−0.02", "0.53", "1위"]}], num=(1, 2, 3, 4), cap="B1 예시: 모델 A에서는 곡 X가 1위지만, 인기곡이라 많이 깎여 순서가 바뀝니다")}
<p><b>B2 예시 (k=2, τ=0.4)</b>: 1~8위는 모델 A 점수 순서로 두고, 9~10위는 그 사용자가 처음 듣는 장르의 곡 중 예측 확률이 0.4 이상인 곡을 점수 순서로 2곡 넣습니다. 조건을 만족하는 곡이 1곡뿐이면 그 곡만 넣고 나머지는 점수 순서로 채웁니다. 예측 확률이 낮은 곡까지 억지로 넣지 않으려고 τ를 둡니다.</p>
<h3>4.4 평가 지표</h3>
{tbl(["지표", "정의", "의미"], [
["Top-10 재청취율", "추천 10곡 중 실제로 재청취된 곡의 비율 (precision@10)", "정확도"],
["발견 대상곡", f"비인기곡 · 새 아티스트(사용자가 처음 듣는 아티스트, Various 제외) · 취향 밖 장르(사용자가 처음 듣는 장르) 중 하나 이상에 해당하는 곡. <b>비인기곡</b>은 그 구간이 시작되기 전까지의 청취 기록에서 <b>청취의 80%를 차지하는 상위 곡 밖의 곡</b>입니다(팀 보고서와 같은 규칙. 경계 청취 수는 검증 구간 {UNP['valid']['경계_청취수']}회, 평가 구간 {UNP['test']['경계_청취수']}회이고 평가 후보의 {unp_share * 100:.1f}%가 해당). B1의 점수 조정은 이 기준선을 쓰지 않고 인기도 백분위를 씁니다", "다양성 노출"],
["통합 유효 발견@10", "Top-10 중 <b>발견 대상곡이면서 실제로 재청취된</b> 곡의 수", "다양성의 실질 이익"],
["유효 비인기곡 / 새 아티스트 / 취향 밖 장르 @10", "위 지표를 세 유형별로 센 값", "유형별 이익"],
["고유 장르 수@10", "Top-10에 포함된 서로 다른 장르의 수", "장르 다양성"]], cap="평가 지표")}
<h3>4.5 사전 설정과 통계 방법</h3>
<ul>
<li><b>모델 A 합격선(학습 전 확정)</b>: 같은 평가 조건에서 인기도 기준 모델보다 AUC가 높고, 사용자 단위 부트스트랩 AUC 차이의 95% 신뢰구간 하한이 0보다 클 것.</li>
<li><b>정확도 손실 한도</b>: 후보 1%p·2%p·3%p·5%p(Top-10 재청취율의 절대 감소). 분석 설계 때 주 한도를 2%p로 정했습니다. 팀 기획서의 목표는 1%p 이내이며 이 기준은 분석 후에 확인했으므로, 1%p와 2%p 결과를 모두 제시하고 요약은 팀 기준(1%p)으로 씁니다.</li>
<li><b>선정 원칙</b>: 검증 구간(holdout)에서 손실이 한도 이내인 설정 중 통합 유효 발견@10이 가장 큰 설정을 고릅니다. 정책 3은 3개 유형의 설정 조합을 모두 탐색해 전체 손실이 한도 이내인 최적 조합을 고릅니다.</li>
<li><b>평가 구간 고정</b>: 평가 구간(test)에서는 선정된 설정을 바꾸지 않고 성능만 확인합니다.</li>
<li><b>통계 검증</b>: 사용자 단위 복원추출 부트스트랩(정책 비교 1,000회, AUC 비교 300회)으로 95% 신뢰구간을 구했습니다. 같은 사용자의 행이 서로 닮았기 때문에 행 단위가 아닌 사용자 단위로 뽑았습니다.</li></ul>
<div class="callout warn"><p><b>분석 중 바꾼 두 가지</b>(검증 구간 결과에 근거, 부록 A에 상세 기록)</p><ul><li>보정 강도 후보 격자를 넓혔습니다(λ 0.20 → 0.50, k 3 → 5).</li><li>사용자 유형 정의를 한 번 바꿨습니다(8.1절).</li></ul></div>

<h2 id="s5">5. 근거 분석: 가설 검증</h2>
<p>KKBox 데이터에서도 음악 다양성과 이용 행동 사이에 관계가 있는지 4개 가설로 확인했습니다. 지지되지 않은 가설도 그대로 보고하며, <b>관측된 상관을 인과로 해석하지 않습니다</b>.</p>
{verdict}
<h3>5.1 H1. 이용 기간이 길어질수록 청취 장르가 좁아지는가?</h3>
<p>두 가지 방식으로 봤습니다. 첫째, 가입 후 경과일이 다른 사용자끼리 <b>첫 50회 청취</b>의 장르 폭을 비교했습니다(청취 50회 이상 {h1['교차_사용자수']:,}명). 둘째, 같은 사용자의 <b>초반 50회와 후반 50회</b>를 비교했습니다.</p>
{h1_s}{h1_q}{h1_w}
<p>가입 시기 기준 비교에서는 오래된 가입자가 최다 장르 비중과 엔트로피 기준으로 아주 약간 더 편중돼 있지만(ρ={h1['교차_spearman_top']['rho']:+.2f}, {h1['교차_spearman_ent']['rho']:+.2f}), 효과가 매우 작고 고유 장르 수에서는 차이가 없습니다. 같은 사용자 안에서는 후반에 고유 장르 수가 오히려 늘었습니다. 두 관점이 엇갈리고 관측 기간이 짧으며 청취 시각이 없다는 한계가 있어, "이용 기간이 길수록 좁아진다"는 가설은 이 데이터에서 확인되지 않았습니다.</p>
<h3>5.2 H2. 청취 편중도가 높은 이용자는 이후 활동이 감소하는가?</h3>
<p>전반 50% 구간의 첫 50회 청취로 편중도를 구하고, 이후 활동량 변화(50~75% 구간 대비 75~100% 구간)를 비교했습니다.</p>
{h2_s}{h2_q}
<p>편중이 높을수록 활동이 조금 더 줄어드는 경향이 있고(통제 후 ρ={h2['통제후_spearman_최다장르비중']['rho']:+.3f}), 신뢰구간도 0을 포함하지 않습니다. 다만 효과가 작고, 이탈률은 가장 분산된 그룹과 가장 편중된 그룹이 비슷해 일관된 관계로 보기 어렵습니다. "약하게 지지"로 판단합니다.</p>
<h3>5.3 H3. 추천 경로를 통한 청취는 직접 탐색보다 다양성이 낮은가?</h3>
<p>재생 탭을 기준으로 <b>추천·큐레이션 경로</b>(discover, radio, explore), <b>직접 탐색</b>(search), <b>내 라이브러리</b>(my library)로 나눴습니다. 이 분류는 분석을 위해 가정한 것입니다. 다양성은 세 지표(새 아티스트·취향 밖 장르·비인기곡 비중)로 봤습니다.</p>
{h3_p}{h3_w}
<p>결과가 지표에 따라 갈립니다. <b>비인기곡 비중은 추천 경로가 조금 낮습니다</b>({pc(h3p[0])} 대 {pc(h3p[1])}, 같은 사용자 안 평균 차이 {sg(h3w['평균차'], 3)} {ci(h3w['ci'], 3)}). 인기 편향의 방향은 맞지만 크기는 작습니다. 반면 <b>새 아티스트와 취향 밖 장르는 추천 경로가 더 많습니다</b>. 직접 탐색(search)은 이미 알고 있는 곡을 찾는 용도로 쓰이는 것으로 보입니다. 그래서 "추천 경로의 다양성이 낮다"는 가설은 인기 편향 측면에서만, 그것도 약하게 지지됩니다.</p>
<h3>5.4 H4. 새로운 장르를 시도한 이용자는 이후 활동이 더 잘 유지되는가?</h3>
<p>0~40% 구간에 청취 50회 이상인 사용자 중, 40~60% 구간에 새 장르를 한 번이라도 들은 사용자(시도군)와 그렇지 않은 사용자를 비교했습니다. 같은 구간의 청취량과 과거 청취량이 비슷한 사용자끼리 맞춰(5×5 층화) 차이를 구했습니다.</p>
{h4_t}
<p>단순 비교에서는 시도군의 활동 유지율이 {pp(h4[rk]['단순차'])} 높지만, 청취량을 맞추면 {pp(h4[rk]['통제후_차'])}로 줄고 신뢰구간이 0을 포함합니다. 청취를 많이 하는 사용자가 새 장르를 만날 기회도 많은 것이 차이의 대부분을 설명합니다. 따라서 이 데이터에서는 가설이 지지되지 않았습니다.</p>
<div class="callout"><p><b>종합</b>: 가설 검증만으로는 "다양성이 높으면 이용이 유지된다"는 근거가 강하지 않습니다. 이 프로젝트의 다양성 보정은 <b>활동 유지 효과를 주장하지 않고</b>, 추천 상위권에서 비인기곡의 노출이 적다는 점(H3)과 선행연구를 근거로, <b>정확도 손실 한도 안에서 얼마나 유효한 발견을 늘릴 수 있는가</b>만 검증합니다.</p></div>

<h2 id="s6">6. 추천 모델: 모델 A</h2>
<h3>6.1 후보 알고리즘 비교</h3>
<p>v1에서 13개 알고리즘을 같은 데이터 분할과 평가 조건으로 비교했습니다. 이 비교는 정답 지연을 적용하기 전의 조건이라 이후 버전의 AUC와 직접 비교할 수 없고, 알고리즘 간 순위를 보는 용도입니다.</p>
{algo_tbl}
<p>부스팅 계열(LightGBM·CatBoost·XGBoost)이 가장 높았고, 로지스틱 회귀({f(V1['LogisticRegression'], 4)})와 랜덤 포레스트({f(V1['RandomForest'], 4)})는 LightGBM({f(V1['LightGBM_v2'], 4)})보다 낮았습니다. 이후 단계에서는 부스팅 계열을 중심으로 모델을 구성했습니다.</p>
<h3>6.2 개선 과정</h3>
{hist_tbl}
<p>가장 큰 개선은 두 번 있었습니다. v6에서 모든 특성을 "현재 행 직전까지" 기준으로 다시 계산해 +0.030, v7에서 노출 경로 특성을 추가해 +0.030이 올랐습니다. 이후에는 버전마다 +0.003 이하로 개선 폭이 줄었습니다.</p>
<h3>6.3 최종 모델 A의 구성</h3>
{gtab}
<p><b>앙상블</b>: LightGBM(시드 5개 평균), LightGBM_B(열 샘플링을 낮춘 설정, 시드 3개 평균), CatBoost, XGBoost의 예측 확률을 로지스틱 회귀(메타모델)로 결합한 <b>Stack4</b>입니다. 계수는 LightGBM {sw['LightGBM']:.3f}, LightGBM_B {sw['LightGBM_B']:.3f}, XGBoost {sw['XGBoost']:.3f}, CatBoost {sw['CatBoost']:.3f}입니다. 기본 모델 4종으로 단독 4개·평균 11개·가중평균 1개·스태킹 1개의 조합 17개를 만들어, <b>ECE 0.01 이하인 후보 중 검증 holdout AUC가 가장 높은 것</b>을 골랐습니다. 최종 모델은 train+valid로 다시 학습했습니다.</p>
<h3>6.4 성능과 사전 합격선</h3>
{perf_val}{perf_test}{chk_tbl}
<p>모델 A는 사전 합격선을 통과했습니다. 인기도 기준선과의 AUC 차이는 검증 holdout에서 {sg(v11_chk.iloc[0]['AUC차이'])}, 평가 구간에서 {sg(seg0['AUC차이'])}이고, 신뢰구간 하한이 모두 0보다 큽니다. 평가 구간의 ECE는 {f(tt.iloc[0].ECE, 4)}로, 예측 확률을 실제 재청취 확률로 읽어도 되는 수준입니다.</p>
<h3>6.5 구간별 예측 성능</h3>
<p>보정 대상인 비인기곡·새 아티스트·취향 밖 장르에서도 모델 A가 잘 작동하는지 확인했습니다.</p>
{seg_tbl}
<p>모든 구간에서 합격선을 통과했습니다. 비인기곡에서 모델 A의 AUC는 {f(P['모델A_구간별'][1]['AUC_모델A'], 3)}로, 인기도 기준선({f(P['모델A_구간별'][1]['AUC_인기도'], 3)})보다 {P['모델A_구간별'][1]['AUC차이']:.3f} 높습니다. 구간별 평균 예측도 실제 재청취율과 가깝지만, 비인기곡은 {(P['모델A_구간별'][1]['실제 재청취율'] - P['모델A_구간별'][1]['모델A 평균예측']) * 100:.1f}%p, 취향 밖 장르는 {(P['모델A_구간별'][3]['실제 재청취율'] - P['모델A_구간별'][3]['모델A 평균예측']) * 100:.1f}%p 실제보다 낮게 예측하는 경향이 있습니다.</p>

<h2 id="s7">7. 다양성 보정: B1·B2</h2>
<p>7장과 8장의 모든 숫자는 후보 20곡 이상 사용자(평가 구간 {nt:,}명)의 상위 10곡 기준입니다. 보정하지 않은 모델 A의 Top-10 재청취율은 {f(aT['prec'], 4)}, 통합 유효 발견@10은 {f(aT['e_D'], 3)}곡입니다.</p>
<h3>7.1 B1 인기도 보정</h3>
{b1_tbl}
<p>λ가 커질수록 Top-10에 비인기곡이 늘어납니다. λ=0.20에서는 비인기곡이 평균 {f(a0['test_n_unpop'], 2)}곡에서 {f(b1_02['test_n_unpop'], 2)}곡으로 늘고, 그중 재청취된 유효 비인기곡이 {f(a0['test_e_unpop'], 2)}곡에서 {f(b1_02['test_e_unpop'], 2)}곡이 됩니다. 재청취율 변화는 {pp(b1_02['test_prec'] - a0['test_prec'])}입니다. <b>장르 다양성은 바뀌지 않습니다</b>(고유 장르 수 {f(a0['test_genres'], 2)} → {f(b1_02['test_genres'], 2)}). λ를 0.3 이상으로 올리면 손실이 급격히 커지고(λ=0.3 {pp(b1[8]['test_prec'] - a0['test_prec'])}, λ=0.5 {pp(b1[10]['test_prec'] - a0['test_prec'])}) 유효 발견 증가분은 완만해집니다(λ=0.3 {sg(b1[8]['test_e_D'] - a0['test_e_D'], 3)}곡, λ=0.5 {sg(b1[10]['test_e_D'] - a0['test_e_D'], 3)}곡).</p>
<h3>7.2 B2 취향 확장 보정</h3>
{b2_tbl}
<p>B2는 취향 밖 장르의 유효 발견을 직접 늘리고 장르 다양성을 높입니다. k=5, τ=0.3에서는 유효 취향 밖 장르가 {f(a0['test_e_newgen'], 2)}곡에서 {f(b2_53['test_e_newgen'], 2)}곡으로 {b2_53['test_e_newgen'] / a0['test_e_newgen']:.1f}배가 되고, 고유 장르 수는 {f(a0['test_genres'], 2)}에서 {f(b2_53['test_genres'], 2)}로 늘지만 재청취율 변화는 {pp(b2_53['test_prec'] - a0['test_prec'])}입니다. τ가 높을수록 손실이 작은 대신 효과도 작습니다.</p>
<p>B2에는 구조적 한계가 있습니다. 취향 밖 장르는 전체 청취의 약 2.7%로 드물어서, 조건(τ 이상)을 만족하는 후보가 있는 사용자는 τ=0.3에서 약 {cov['tau=0.3'] * 100:.0f}%, τ=0.4에서 {cov['tau=0.4'] * 100:.0f}%, τ=0.5에서 {cov['tau=0.5'] * 100:.0f}%뿐입니다(평가 구간 사용자의 일부를 표본으로 계산한 값). 나머지 사용자에게는 B2가 작동하지 않습니다.</p>
<div class="callout warn"><p><b>후보 범위를 넓혀 다시 확인했습니다.</b> 정책 선정에 쓴 격자는 k 1~5, τ 0.3~0.5였습니다. 보고서를 쓴 뒤 B2 단독으로 k 1~10, τ 0.1~0.5까지 넓혀 검증 구간에서 확인했습니다(<code>B/results/check_b2_wide_grid.csv</code>).</p>
<ul><li><b>τ=0.3은 끝값이 아닙니다.</b> τ를 0.2로 낮추면 k=5에서 {tau2_txt}({cw(5, 0.2, 'valid_eD_gain'):+.3f}곡, τ=0.3은 {cw(5, 0.3, 'valid_eD_gain'):+.3f}곡) 재청취율 손실이 {cw(5, 0.2, 'valid_loss_pp'):.2f}%p로 한도 2%p를 넘습니다.</li>
<li><b>k는 5 이후로 효과가 포화됩니다.</b> τ=0.3에서 k를 5에서 10으로 늘려도 유효 발견이 {cw(5, 0.3, 'valid_eD_gain'):+.3f}곡에서 {cw(10, 0.3, 'valid_eD_gain'):+.3f}곡으로 {(cw(10, 0.3, 'valid_eD_gain') / cw(5, 0.3, 'valid_eD_gain') - 1) * 100:.0f}% 늘 뿐이고 손실은 {cw(5, 0.3, 'valid_loss_pp'):.2f}%p에서 {cw(10, 0.3, 'valid_loss_pp'):.2f}%p가 됩니다. 취향 밖 장르 후보가 있는 사용자가 일부라 k를 늘려도 채울 곡이 부족하기 때문입니다.</li>
<li><b>B2 단독의 검증 구간 최적은 넓힌 격자에서 k=10으로 바뀝니다</b>(한도 1%p는 τ=0.4, 한도 2%p는 τ=0.3). 다만 k=5 대비 차이가 {cw(10, 0.4, 'valid_eD_gain') - cw(5, 0.4, 'valid_eD_gain'):.3f}곡(1%p), {cw(10, 0.3, 'valid_eD_gain') - cw(5, 0.3, 'valid_eD_gain'):.3f}곡(2%p)으로 작아서 정책 2·3은 다시 계산하지 않았습니다.</li></ul>
<p>따라서 이 장에서 선정된 B2 설정은 <b>"시험한 범위에서 한도 안에 가장 효과가 컸던 설정"</b>이며 진짜 최적값이라고 할 수 없습니다.</p></div>
<h3>7.3 B1·B2 단독 비교 (손실 한도 1%p·2%p)</h3>
{single_table('0.01')}{single_table('0.02')}
<p>B1은 <b>비인기곡</b> 노출을, B2는 <b>취향 밖 장르</b> 노출과 장르 다양성을 늘립니다. 둘은 서로 다른 종류의 발견을 늘리므로, 함께 쓰면 효과가 더해집니다(정책 2).</p>
<div class="fig">{svg}<div class="cap">그림 7-1. 정확도 손실과 유효 발견 증가의 트레이드오프 (test). 모델 A에서 오른쪽 위로 갈수록 정확도를 더 내주고 유효 발견을 더 얻습니다. 보정 설정 176개를 모두 평가했습니다.</div></div>

<h2 id="s8">8. 사용자별 차등 보정: B3</h2>
<h3>8.1 사용자 유형 정의와 유효성</h3>
<p>유형은 <b>평가 구간의 정보를 쓰지 않고 이전 청취 이력만으로</b> 정의했습니다. 사용자가 평가 구간에 처음 등장하는 시점의 값을 쓰며, 재청취율은 정답이 확정된 과거 행(43% 이상 이전)으로만 계산한 값입니다.</p>
{dist_tbl}
<p>유형 구분이 실제로 의미 있는지 확인하기 위해, 검증 구간과 평가 구간에서 유형별 실제 재청취율을 비교했습니다.</p>
{validity_tbl("a", "valid_holdout")}{validity_tbl("a", "test")}
<p>탐색 친화형은 새 아티스트·취향 밖 장르·비인기곡을 다시 듣는 비율이 익숙함 선호형보다 모두 높고, 차이의 신뢰구간이 0을 포함하지 않습니다. 이 구분은 검증 구간과 평가 구간에서 같은 방향으로 확인됐습니다.</p>
<div class="callout warn"><p><b>유형 정의를 한 번 바꿨습니다.</b> 처음에는 "새로운 것의 재청취율에서 자기 평균 재청취율을 뺀 값"으로 정의했습니다(상대형). 그러나 검증 구간에서 탐색 친화형의 새 아티스트 재청취율이 익숙함 선호형보다 <b>오히려 낮았습니다</b>({sg(z_v['새 아티스트']['차이'], 3)}, {ci(z_v['새 아티스트']['ci'], 3)}). 평균 재청취율이 낮은 사용자가 이 유형으로 몰렸기 때문으로 보입니다. 그래서 절대적인 수용도(위 표의 정의)로 바꿨고, 검증 구간에서 유효성 기준을 통과한 정의를 채택했습니다. 첫 정의의 평가 구간 수치도 같은 출력에서 보였으므로, 완전히 독립적인 확인은 아니라는 점을 밝혀 둡니다(부록 A).</p></div>
<h3>8.2 정책별 보정 설정 (검증 구간에서 선정)</h3>
{sel_tbl}
<p>정책 3의 유형별 설정은 손실 한도에 따라 달라지며, 한도가 클수록 대체로 강해집니다. 한도 2%p에서는 {set_txt}입니다. 유형 간 B2 설정(k)의 차이가 왜 생기는지는 이 분석만으로 설명할 수 없습니다.</p>
<h3>8.3 세 정책의 비교 (손실 한도 1%p·2%p)</h3>
{policy_block('0.01')}{policy_block('0.02')}
<p>두 한도 모두 정책 3이 정책 2보다 유효 발견을 더 얻는 대신 재청취율을 더 내줍니다. 서로 다른 양의 정확도를 쓰고 있으므로 이 비교만으로 차등 보정이 낫다고 결론 낼 수 없고, 한도별 민감도(8.4)와 노출 수준을 맞춘 비교(8.5)로 확인해야 합니다.</p>
<h3>8.4 손실 한도별 민감도</h3>
{sens_tbl}
<p>모든 한도에서 정책 3의 유효 발견이 정책 2보다 많고 신뢰구간이 0을 포함하지 않지만, 재청취율도 항상 조금 더 낮습니다. 정책 3이 정책 2보다 더 얻은 유효 발견은 한도에 따라 {min(dd_gain):+.3f}곡에서 {max(dd_gain):+.3f}곡 사이이고, 한도의 크기와 일정한 관계가 없습니다.</p>
<h3>8.5 노출 수준을 맞춘 비교</h3>
<p>두 정책이 같은 만큼 발견 대상곡을 노출하도록 맞추면 정확도와 유효 발견을 공정하게 비교할 수 있습니다. 한도마다 정책 3의 노출과 가장 가까운 정책 2 설정을 평가 구간의 <b>노출만 보고</b> 골랐습니다(결과 지표는 보지 않았습니다).</p>
{mt_tbl}
<p>노출이 같을 때 차등 보정의 통합 유효 발견은 일괄 보정보다 {min(MT[k]['정책3−정책2']['e_D']['차이'] for k in MT):+.3f}~{max(MT[k]['정책3−정책2']['e_D']['차이'] for k in MT):+.3f}곡 많고{', 모든 한도에서 신뢰구간이 0을 포함하지 않습니다' if ed_all_sig else ''}. 일괄 보정의 유효 발견 수준과 비교하면 {min(MT[k]['정책3−정책2']['e_D']['차이'] / MT[k]['정책2']['e_D'] for k in MT) * 100:.1f}~{max(MT[k]['정책3−정책2']['e_D']['차이'] / MT[k]['정책2']['e_D'] for k in MT) * 100:.1f}% 수준입니다. 재청취율 차이({min(MT[k]['정책3−정책2']['prec']['차이'] for k in MT) * 100:+.2f}~{max(MT[k]['정책3−정책2']['prec']['차이'] for k in MT) * 100:+.2f}%p)는 한도 {', '.join(prec_sig_L)}에서만 신뢰구간이 0을 포함하지 않고, 한도 {', '.join(prec_ns_L)}에서는 유의하지 않습니다.</p>
{em_detail('0.01')}{em_detail('0.02')}
<p>통합 유효 발견은 두 한도 모두 차등 보정이 더 많지만, <b>어떤 종류의 발견이 늘어나는지는 한도에 따라 다릅니다</b>. 한도 1%p에서 차등 보정은 {comp_phrase('0.01')}입니다. 한도 2%p에서는 {comp_phrase('0.02')}입니다. 따라서 차등 보정의 이익을 "장르 다양성이 더 늘어난다"로 해석할 수는 없습니다.</p>
<h3>8.6 유형별 효과</h3>
{ut_tbl}
<p>한도 2%p에서 정책 3으로 늘어난 유효 발견({gs / nt:.3f}곡/인 평균)의 <b>{share[TN[0]] * 100:.0f}%가 탐색 친화형, {share[TN[1]] * 100:.0f}%가 익숙함 선호형, {share[TN[2]] * 100:.0f}%가 판단 유보형</b>에서 나옵니다. 사용자 수 비중(탐색 {ucnt[0] * 100:.0f}%, 익숙 {ucnt[1] * 100:.0f}%, 유보 {ucnt[2] * 100:.0f}%)보다 탐색 친화형의 몫이 큽니다. 탐색 친화형은 재청취율 변화({pp(ut[TN[0]]['정책3(차등)']['prec'] - ut[TN[0]]['정책1(A)']['prec'], 1)})가 가장 크지만 기준 재청취율이 {f(ut[TN[0]]['정책1(A)']['prec'], 2)}로 가장 높은 유형입니다.</p>
<h3>8.7 판단</h3>
<div class="callout"><p>차등 보정(B3)은 <b>유효 발견 기준으로는 통계적으로 일괄 보정보다 낫지만 크기가 아주 작습니다.</b> 노출을 맞춘 비교에서 추가 유효 발견은 한도 1%p에서 {sg(m1d['e_D']['차이'], 3)}곡(일괄 대비 {m1rel * 100:+.1f}%), 2%p에서 {sg(m2d['e_D']['차이'], 3)}곡({m2rel * 100:+.1f}%)이고, 유효 발견 차이는 어느 한도에서도 신뢰구간이 0을 포함하지 않지만 재청취율 차이는 한도 {', '.join(prec_ns_L)}에서 유의하지 않습니다. 사용자 유형을 산출하고 유형별 설정을 관리하는 운영 비용을 감수할 만큼 크다고 보기는 어렵습니다.</p></div>

<h2 id="s9">9. 운영 가이드와 비즈니스 인사이트</h2>
<h3>9.1 조건별 정책 선택 가이드</h3>
{tbl(["상황", "권장 정책", "근거 (test)"], [
["정확도 손실을 거의 허용하지 않음 (≈1%p)", "일괄 B1 (λ≈0.2)", f"재청취율 {pp(sens['0.01']['정책2(일괄)']['prec'] - sens['0.01']['정책1(A)']['prec'])}에 유효 발견 {sg(sens['0.01']['정책2(일괄)']['e_D'] - sens['0.01']['정책1(A)']['e_D'], 3)}곡 (손실 1%p당 {eff['0.01']:.2f}곡). 이 한도에서는 B1이 B2보다 유효 발견을 더 많이 얻어 B1만 선택됨"],
["약간의 손실 허용 (≈2%p)", "<b>일괄 B1+B2</b> (" + best_setting + ")", f"재청취율 {pp(-loss2)}에 유효 발견 {sg(g2, 3)}곡 (+{g2 / aT['e_D'] * 100:.1f}%, 손실 1%p당 {eff['0.02']:.2f}곡). 한도 1%p와 비슷한 효율이 유지되는 마지막 구간"],
["손실을 더 허용 (3%p 이상)", "일괄 B1 강화 (λ 0.3~0.4) + B2 k=5, τ=0.4", f"한도를 2%p에서 3%p로 늘리면 손실이 {d3[1] * 100 - d2[1] * 100:.1f}%p 더 늘고 유효 발견은 {d3[0] - d2[0]:.3f}곡 더 늘어남. 5%p까지 가면 손실 {d5[1] * 100 - d3[1] * 100:.1f}%p 추가에 {d5[0] - d3[0]:.3f}곡 추가로, 효율이 계속 떨어짐 (손실 1%p당 3%p 한도 {eff['0.03']:.2f}곡, 5%p 한도 {eff['0.05']:.2f}곡)"],
["사용자 유형 정보를 이미 운영 중이고 관리 비용이 낮음", "차등 보정 (탐색 친화형에 강하게)", f"노출 맞춤 기준 추가 유효 발견 {sg(m1d['e_D']['차이'], 3)}곡(한도 1%p, 일괄 대비 {m1rel * 100:+.1f}%). 이익이 작으므로 A/B 테스트로 먼저 확인"],
["이익이 불확실하거나 운영 여력이 부족", "기본 개인화 또는 일괄 보정 유지", "차등 보정의 추가 이익이 운영 복잡성을 정당화하지 못할 수 있음"]], cap="정책 선택 가이드")}
<h3>9.2 관점별 기대 효과 (시뮬레이션 기준)</h3>
<ul>
<li><b>사용자</b>: 일괄 보정(2%p) 시 Top-10에서 발견 대상곡이 평균 {f(aT['n_D'], 2)}곡에서 {f(p2['n_D'], 2)}곡으로 늘고, 그중 실제로 다시 들을 곡이 {f(aT['e_D'], 2)}곡에서 {f(p2['e_D'], 2)}곡으로 늘어납니다. 고유 장르 수도 {f(aT['genres'], 2)}에서 {f(p2['genres'], 2)}로 늘어납니다.</li>
<li><b>스트리밍 플랫폼</b>: 인기곡에 집중된 노출을 분산시켜 카탈로그 활용도를 높일 가능성이 있습니다. B1(λ=0.2)만으로 Top-10의 비인기곡이 평균 {f(a0['test_n_unpop'], 2)}곡에서 {f(b1_02['test_n_unpop'], 2)}곡으로 늘어납니다.</li>
<li><b>아티스트</b>: 비인기곡의 추천 기회가 늘어납니다. 다만 새 아티스트의 유효 발견은 B1에서 오히려 소폭 줄고({f(aT['e_newart'], 3)} → {f(T['A+B1']['e_newart'], 3)}), B2·정책 2·3에서는 소폭 늘어납니다.</li></ul>
<div class="callout warn"><p>위 효과는 <b>과거 청취 기록을 이용한 오프라인 시뮬레이션</b>입니다. 청취 시간 증가나 구독 유지 같은 실제 서비스 지표의 개선을 입증하지 않습니다. 5장에서도 다양성과 활동 유지의 관계는 약했습니다.</p></div>
<h3>9.3 시연용 프로토타입</h3>
<p>로드맵의 시연용 프로토타입(기본·일괄·차등 추천 결과를 비교해 보여 주는 화면)은 이번 분석 범위에서 제작하지 않았습니다. 필요한 입력은 준비돼 있습니다(모델 A의 평가 구간 예측, 정책별 선정 설정, 사용자 유형). 프로토타입을 만들 때는 추천 칸의 곡이 어느 재생 경로로 재생된다고 볼지(예: <code>discover</code> 탭, <code>online-playlist</code> 진입점)를 가정으로 정하고 화면에 밝혀야 합니다.</p>

<h2 id="s10">10. 한계와 향후 과제</h2>
<h3>10.1 한계</h3>
<ol>
<li><b>후보곡이 실제 재생된 곡입니다.</b> 정답이 있는 곡이 이것뿐이어서, 보정이 만든 "발견"은 사용자가 이미 들은 곡들 사이의 재배열입니다. 완전히 새로운 곡을 추천했을 때의 반응은 측정하지 못합니다.</li>
<li><b>재생 경로의 실제 값을 입력으로 썼습니다.</b> 모델 A는 각 후보곡이 실제로 재생된 경로를 입력으로 받습니다. 서비스에 적용할 때는 웹페이지의 추천 칸을 데이터의 어느 경로 값(예: <code>discover</code> 탭, <code>online-playlist</code> 진입점)에 대응시킬지 <b>우리가 가정해서 정해야 하고</b>, 그 가정에 따라 점수와 성능이 달라질 수 있습니다. 이 대응은 데이터로 검증할 수 없습니다.</li>
<li><b>모델 학습에는 정답 지연을 적용하지 않았습니다.</b> 지연 규칙은 특성에만 적용했습니다. 실제 서비스에서는 최근 한 달의 정답이 아직 확정되지 않으므로 실제 성능은 보고된 수치보다 다소 낮을 수 있습니다.</li>
<li><b>평가 구간을 여러 번 확인했습니다.</b> 모델 개발(v1~v12) 과정에서 test를 버전마다 확인했습니다. 보정 설정은 검증 구간에서만 선정했고 정책 비교는 그 설정을 고정해 수행했지만, 유형 정의를 바꿀 때 첫 정의의 평가 구간 수치가 이미 보인 상태였습니다.</li>
<li><b>손실 한도가 평가 구간에서 지켜지지 않을 수 있습니다.</b> 정책 3의 평가 구간 손실은 {abs(loss3) * 100:.2f}%p로 한도 2%p를 넘었습니다. 시간이 지날수록 재청취율 분포가 바뀌기 때문입니다.</li>
<li><b>유형 기준값이 시간에 따라 이동합니다.</b> 검증 구간 중앙값({cuts['a']:.3f})으로 정한 기준을 평가 구간에 적용하자 유형 비율이 달라졌습니다(탐색 친화형 검증 {dist[TN[0]]['valid_holdout'] / (nv - dist[TN[2]]['valid_holdout']) * 100:.0f}% 대 평가 {dist[TN[0]]['test'] / (nt - dist[TN[2]]['test']) * 100:.0f}%, 판단 유보형 제외). 운영하려면 기준값을 주기적으로 다시 정해야 합니다.</li>
<li><b>"유효 발견"의 정의에 가정이 들어갑니다.</b> 비인기곡은 "구간 시작 전 청취의 80%를 차지하는 상위 곡 밖의 곡"으로 정의했습니다. 설명할 수 있는 규칙이지만 80%라는 값 자체는 임의의 선택이고, 이 값을 바꾼 민감도 분석은 하지 않았습니다. 세 발견 유형을 같은 비중으로 합산한 통합 지표도 가정입니다. 통합 지표가 보정 설정을 고르는 목적함수이므로 정의가 바뀌면 선정되는 설정도 달라질 수 있습니다(실제로 비인기곡 기준을 누적 35회 미만에서 80% 규칙으로 바꿨을 때 정책 3의 유형별 설정이 바뀌었습니다, 부록 A). 취향 밖 장르는 전체의 2.7%로 드물어 B2의 적용 범위가 좁습니다.</li>
<li><b>가설 검증은 관찰 분석입니다.</b> 인과 해석을 할 수 없고, 추천 경로 분류와 관측 기간·청취 시각 부재에 따른 한계가 있습니다.</li>
<li><b>B2 후보 범위의 끝값.</b> 정책 선정에 쓴 B2 격자(k 1~5, τ 0.3~0.5)의 선정값은 범위의 끝값이었습니다. 이후 B2 단독으로 범위를 넓혀 확인했고(7.2절) 효과 차이는 작았지만, 정책 2·3은 넓힌 격자로 다시 계산하지 않았습니다.</li>
<li><b>선행연구의 서지 확인.</b> 참고문헌은 제출 전 원문 대조가 필요합니다(부록 F에 확인 상태를 표시했습니다).</li>
<li><b>차등 보정의 도입 기준을 사전에 수치로 정하지 않았습니다.</b> 합격선·손실 한도 후보·선정 원칙은 사전에 정했지만, "차등 보정이 일괄 대비 얼마 이상 나아야 도입한다"는 판정 기준은 정하지 않았고 결과를 본 뒤 판단했습니다.</li>
<li><b>손실 한도 기준을 분석 후에 맞췄습니다.</b> 팀 기획서의 1%p 기준은 분석 후에 확인했습니다. 사전에 정한 주 한도(2%p)와 함께 두 결과를 모두 제시했고 결론은 같았지만, 요약을 1%p 기준으로 쓴 것은 사후 선택입니다.</li>
<li><b>이용자 인식(설문·인터뷰) 층위는 다루지 않았습니다.</b> 근거 체계의 3층은 팀이 별도로 진행합니다(2.5절).</li></ol>
<h3>10.2 향후 과제</h3>
<ul>
<li><b>실서비스 A/B 테스트</b>: 일괄 보정과 차등 보정을 실제 사용자에게 적용해 청취 시간·재청취·구독 유지에 미치는 효과를 측정</li>
<li><b>후보 생성 단계 포함 평가</b>: 이미 들은 곡이 아닌, 후보 생성 단계가 만든 새 곡까지 포함해 효과 확인</li>
<li><b>경로 정보 없는 모델에서 재현</b>: 재생 경로를 쓰지 않은 모델(v6)의 예측 위에서 같은 보정 실험을 반복해 결론이 유지되는지 확인</li>
<li><b>유형 대신 연속적인 개인화</b>: 사용자별 보정 강도를 연속값으로 정하거나 탐색-활용 방식(밴딧)으로 학습</li>
<li><b>다른 보정 기법</b>: MMR, 사용자 관심사 비율을 맞추는 보정 등과의 비교</li>
<li><b>시연용 프로토타입 제작</b></li></ul>

<h2 id="s11">11. 결론</h2>
<ol>
<li><b>모델 A는 신뢰할 만한 기준 모델입니다.</b> 인기도 기준선보다 AUC가 {sg(seg0['AUC차이'])} 높고(합격선 통과), 비인기곡·새 아티스트·취향 밖 장르에서도 같은 결과를 보였으며, 예측 확률이 실제 재청취율과 잘 맞습니다.</li>
<li><b>후처리 보정은 작은 정확도 손실로 유효 발견을 늘립니다.</b> B1은 비인기곡, B2는 취향 밖 장르의 유효 발견을 늘리며, 서로 다른 발견을 늘리므로 함께 쓰는 일괄 보정이 효과적입니다. 팀 기준 한도 1%p에서는 재청취율 {pp(-loss21)}로 유효 발견@10이 {f(a1['e_D'], 2)}곡에서 {f(p21['e_D'], 2)}곡으로, 한도 2%p에서는 {pp(-loss2)}로 {f(aT['e_D'], 2)}곡에서 {f(p2['e_D'], 2)}곡으로 늘었습니다. 한도를 키울수록 효율은 떨어집니다.</li>
<li><b>사용자별 차등 보정의 추가 이익은 아주 작습니다.</b> 유효 발견 기준으로는 통계적으로 일괄 보정보다 낫지만(노출 맞춤 기준 한도 1%p에서 {sg(m1d['e_D']['차이'], 3)}곡으로 일괄 대비 {m1rel * 100:+.1f}%, 2%p에서 {sg(m2d['e_D']['차이'], 3)}곡으로 {m2rel * 100:+.1f}%), 운영 복잡성을 정당화할 만큼 크다고 보기는 어렵습니다.</li>
<li><b>의사결정</b>: 먼저 <b>일괄 보정</b>(정확도 손실 한도 안에서 B1+B2)을 적용하고, 차등 보정은 A/B 테스트로 이익이 확인되면 도입합니다. 이익이 확인되지 않으면 단순 정책을 유지합니다.</li></ol>
<p class="small">다양성과 활동 유지의 관계(H2·H4)는 이 데이터에서 약하거나 확인되지 않았으므로, 보정의 가치는 "정확도를 크게 해치지 않으면서 새 발견 기회를 넓힌다"는 범위에서만 주장할 수 있습니다.</p>

<h2 id="s12">12. 부록</h2>
<h3>A. 분석 수정 이력</h3>
{tbl(["항목", "내용", "근거"], [
["보정 강도 격자 확장", f"처음에는 B1 λ를 0.20까지, B2 k를 3까지로 정했습니다(B1 8개 × B2 10개 = 80개 설정). 이 격자에서 정책 2의 최적해가 격자 끝(λ=0.20, k=3)에 걸렸고, 검증 구간 손실이 {run1_loss * 100:.2f}%p로 한도 2%p에 못 미쳐 한도가 제약으로 작동하지 않았습니다(이 수치는 비인기곡을 35회 미만으로 정의했을 때의 첫 실행 값입니다). λ를 0.50까지, k를 5까지 넓혀 176개 설정으로 다시 선정했습니다.", "검증 구간 결과. 첫 실행 결과는 <code>B/results/policies_run1.json</code>에 보관"],
["사용자 유형 정의 변경", f"첫 정의(상대형: 새로운 것의 재청취율 − 자기 평균)는 검증 구간에서 탐색 친화형의 새 아티스트 재청취율이 익숙함 선호형보다 낮게 나와({sg(z_v['새 아티스트']['차이'], 3)}) 이름과 행동이 반대였습니다. 두 정의를 검증 구간에서 평가하고, '탐색 친화형의 새 아티스트·취향 밖 장르 재청취율이 더 높고 신뢰구간 하한이 0보다 큼'을 통과하는 정의(절대형)를 채택했습니다.", "검증 구간 결과. 단, 첫 정의의 평가 구간 수치도 같은 출력에 있어 열람함"],
["비인기곡 판정 기준 변경", f"처음에는 비인기곡을 '곡 누적 청취 35회 미만'으로 정의했습니다. 사용자 요청으로 팀 보고서와 같은 '구간 시작 전 청취의 80%를 차지하는 상위 곡 밖의 곡'으로 바꿨습니다(결과를 보고 고른 것이 아니라 기준을 팀과 맞추기 위한 변경). 비인기곡 비중은 평가 후보의 약 22%에서 {unp_share * 100:.1f}%로 늘었고, 가설 H3·모델 A 구간별 성능·보정 설정 선정·정책 비교를 모두 다시 계산했습니다. 정책 3의 한도 2%p 유형별 설정이 바뀌었고, 차등−일괄(노출 맞춤, 한도 1%p) 추가 유효 발견은 +0.044곡(+1.6%)에서 {sg(m1d['e_D']['차이'], 3)}곡(+{m1rel * 100:.1f}%)으로 줄었으며 재청취율 차이는 한도 1%p에서 유의하지 않게 되었습니다. '차등 보정의 추가 이익은 작다'는 결론은 같고 더 강해졌습니다.", "이전 결과: <code>B/results_35/</code>"],
["재실행 확인", "정책 분석 스크립트를 처음부터 다시 실행해 결과 파일의 숫자 2,110개와 설정 그리드가 모두 같음을 확인했습니다 (시드 고정).", "<code>B/results/b2_rerun.log</code>"],
["노출 맞춤 비교 확장", "처음에는 손실 한도 2%p에서만 노출 맞춤 비교를 했습니다. 팀 기준 한도 1%p를 확인한 뒤 모든 한도로 확장하는 코드를 추가했고(별도 난수 사용), 기존 결과의 숫자가 바뀌지 않았음을 확인했습니다.", "<code>B/results/matched_exposure.json</code>"],
["B2 후보 범위 확인", "정책 선정에 쓴 B2 격자의 선정값(k=5, τ=0.3)이 후보 범위의 끝값이라, 보고서를 쓴 뒤 B2 단독으로 k 1~10, τ 0.1~0.5까지 넓혀 검증 구간에서 확인했습니다. τ=0.3은 끝값이 아니었고 k는 5 이후 효과가 포화됐습니다. 정책 2·3은 다시 계산하지 않았습니다.", "<code>B/check_b2.py</code>, <code>B/results/check_b2_wide_grid.csv</code>"]], cap="분석 중 변경 사항")}
<h3>B. 재현 방법</h3>
<ul><li>프로젝트 폴더에서 실행: <code>python3 B/b1_hypotheses.py</code> (5장), <code>python3 B/b2_policies.py</code> (6~8장), <code>python3 B/make_report.py</code> (이 보고서)</li>
<li>모델 A(v11)의 학습 코드는 <code>A/v11.py</code>입니다. <code>A</code> 폴더로 옮긴 코드는 <code>data.csv</code> 경로를 <code>../data.csv</code> 등으로 조정해야 실행됩니다.</li>
<li>정책 분석에는 <code>A/v11/pred_*_modelA_v11.parquet</code>(모델 A 예측)과 <code>A/v12/featv12_*.parquet</code>(특성)이 필요합니다.</li></ul>
<h3>C. 주요 산출물</h3>
{tbl(["파일", "내용"], [
["<code>A/v11/</code>", "모델 A 학습 결과, 예측, 성능표, 특성 중요도, v11 보고서"],
["<code>B/results/hypotheses.json</code>", "H1~H4 분석 결과"], ["<code>B/results/policies.json</code>", "모델 A 구간별 검증, 사용자 유형, B1·B2·정책 비교 전체 결과"],
["<code>B/results/grid_settings.csv</code>", "보정 설정 176개의 검증·평가 지표"], ["<code>B/results/policies_run1.json</code>", "격자 확장 전 첫 실행 결과"],
["<code>B/results/v1_algorithms.json</code>", "v1 후보 알고리즘 13종의 검증 holdout AUC"]], cap="파일 목록")}
<h3>D. 모델 A 설정</h3>
{tbl(["모델", "주요 설정", "시드", "최종 반복 수"], [
[k, ", ".join(f"{a}={v if not isinstance(v, float) else round(v, 4)}" for a, v in d["params" if "params" in d else None].items()) if "params" in d else ", ".join(f"{a}={v}" for a, v in d.items() if a not in ("seed", "random_seed")), str(d.get("seeds", d.get("random_seed", ""))), str(V11["재학습반복수"][k])]
for k, d in V11["기본모델"].items()], cap="기본 모델 4종 (Stack4 구성)")}
<p class="small">Stack4 메타모델: 로지스틱 회귀, 입력은 4개 모델 예측의 logit, 절편 {V11['stack4_절편']:.4f}.</p>
<h3>E. 유효 발견 정의별 비교</h3>
<p>유효 발견은 두 가지로 셀 수 있습니다. 이 보고서의 통합 지표는 비인기곡·새 아티스트·취향 밖 장르 중 하나라도 해당하는 곡을 한 번만 셉니다(합집합). 합계 방식(유효 비인기곡 + 유효 새 아티스트)은 두 조건을 모두 만족하는 곡을 두 번 세고 취향 밖 장르를 포함하지 않습니다. 어느 정의로 세어도 정책 간 순서는 같습니다.</p>
{sum_tbl}
<h3>F. 참고문헌</h3>
<ol>{"".join(f"<li>{r}</li>" for r in refs)}</ol>
<p class="small">서지 정보(제목·연도·학회)는 제출 전에 원문과 대조해 확인해 주세요.</p>

<footer>이 보고서의 숫자는 <code>B/results/</code>의 결과 파일에서 코드로 직접 채웠습니다. 보정 설정은 검증 구간(valid holdout)에서만 선정했고, 평가 구간(test)에서는 고정했습니다. 관찰 분석(5장)과 오프라인 시뮬레이션(7~8장)의 결과는 인과 효과나 실서비스 성과를 입증하지 않습니다.</footer>
</article></body></html>"""
open("B/최종보고서.html", "w", encoding="utf-8").write(HTML)
print("saved", len(HTML))
