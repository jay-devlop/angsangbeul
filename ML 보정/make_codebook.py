# v11 모델 입력 데이터(구간별 특성 파일)의 코드북(데이터 명세서)을 만든다. 값 범위·결측은 실제 파일에서 계산한다.
import json
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = "B/데이터명세서_v11.xlsx"
cfg = json.load(open("A/v11/modelA_v11_설정과결과.json", encoding="utf-8"))
GROUPS = cfg["특성그룹"]
BLOCKS = ["train_a", "train_b", "valid", "test"]
KEYS = ["row_order", "msno", "song_id", "target"]
FEATS = [c for g in GROUPS.values() for c in g]
assert len(FEATS) == 129

# ---------- 실제 파일에서 통계 ----------
df = pd.concat([pd.read_parquet(f"A/v12/featv12_{b}.parquet", columns=KEYS + FEATS) for b in BLOCKS], ignore_index=True)
N = len(df)
print("행 수", N)
raw = pd.read_csv("data.csv", engine="pyarrow", usecols=["row_order", "source_system_tab", "source_screen_name", "source_type", "primary_genre"])
x = df[["row_order", "src_tab", "src_screen", "src_type", "primary_genre_code"]].merge(raw, on="row_order")
MAP = {
    "src_tab": x.groupby("src_tab")["source_system_tab"].first().to_dict(),
    "src_screen": x.groupby("src_screen")["source_screen_name"].first().to_dict(),
    "src_type": x.groupby("src_type")["source_type"].first().to_dict(),
    "primary_genre_code": x.groupby("primary_genre_code")["primary_genre"].first().to_dict(),
}
TAB = [MAP["src_tab"][k] for k in sorted(MAP["src_tab"])]            # 코드 1~9 -> 탭 이름 (경로 프로필의 k는 코드-1)
del x, raw

# ---------- 변수 설명 ----------
# (설명, 척도, 결측 사유, 비고)
NAN_DEF = "NaN 그대로 모델에 입력(대체하지 않음)"
D = {
    # 정적
    "song_length_min": ("곡 길이(분)", "비율", "0 이하·songs에 없는 곡은 결측", "원본 song_length(밀리초)를 분으로 변환"),
    "is_short": ("1분 미만 곡 여부", "명목(이진)", "songs에 없는 곡은 결측", "1 = 1분 미만"),
    "is_long": ("10분 초과 곡 여부", "명목(이진)", "songs에 없는 곡은 결측", "1 = 10분 초과"),
    "n_genres": ("장르 개수", "비율", "songs에 없는 곡은 결측", "unknown 장르는 0"),
    "n_artists": ("참여 아티스트 수", "비율", "songs에 없는 곡은 결측", ""),
    "language": ("곡 언어 코드", "명목", "미상은 -1, songs에 없는 곡은 결측", "원본 값 그대로(정수 코드). 모델에는 숫자로 입력"),
    "is_various_artist": ("Various Artists(여러 가수 모음집) 여부", "명목(이진)", "songs에 없는 곡은 결측", "1이면 아티스트 단위 특성을 결측으로 둠"),
    "bd_clean": ("나이", "비율", "1~100 밖의 값은 결측", "원본 bd 정제"),
    "age_group": ("연령대 코드", "순서", "나이 결측은 0(미상)", "1 10대 이하, 2 20대, 3 30대, 4 40대, 5 50대 이상"),
    "primary_genre_code": ("첫 번째 장르 코드(범주 번호)", "명목", "unknown 장르는 0", "원본 primary_genre를 코드로 변환. 모델에 범주형으로 지정. 코드 번호는 '범주코드표' 시트 참고"),
    "gender_code": ("성별 코드", "명목", "결측은 0(미상)", "원본 gender(male/female/unknown)를 코드로 변환. 모델에는 숫자로 입력"),
    "membership_days": ("멤버십 기간(만료일 − 가입일, 일)", "비율", "만료일이 가입일보다 앞선 회원은 결측", "회원 정보에서 계산"),
    "reg_year": ("가입 연도", "구간", "", "가입일에서 추출"),
    # 누적
    "u_cnt_now": ("현재 행 직전까지 사용자의 누적 청취 수", "비율", "", "사용자별 cumcount. 현재 행 제외"),
    "s_cnt_now": ("현재 행 직전까지 곡의 누적 청취 수(전체 사용자)", "비율", "", "곡 인기도"),
    "a_cnt_now": ("아티스트의 누적 청취 수", "비율", "Various Artists는 결측", ""),
    "ua_cnt_now": ("사용자가 이 아티스트를 들은 누적 횟수", "비율", "Various Artists는 결측", ""),
    "ug_cnt_now": ("사용자가 이 장르를 들은 누적 횟수", "비율", "장르 unknown은 결측", ""),
    "ul_cnt_now": ("사용자가 이 언어의 곡을 들은 누적 횟수", "비율", "언어 미상은 결측", ""),
    "ua_share_now": ("사용자 전체 청취 중 이 아티스트의 비율", "비율", "Various Artists는 결측", "ua_cnt_now ÷ max(u_cnt_now,1)"),
    "ug_share_now": ("사용자 전체 청취 중 이 장르의 비율", "비율", "장르 unknown은 결측", "ug_cnt_now ÷ max(u_cnt_now,1)"),
    "ul_share_now": ("사용자 전체 청취 중 이 언어의 비율", "비율", "언어 미상은 결측", "ul_cnt_now ÷ max(u_cnt_now,1)"),
    "s_share_in_artist": ("아티스트 전체 청취 중 이 곡의 비율(대표곡 여부)", "비율", "Various Artists는 결측", "s_cnt_now ÷ max(a_cnt_now,1)"),
    "is_new_artist": ("사용자가 처음 듣는 아티스트인지", "명목(이진)", "", "1 = ua_cnt_now가 0. 새 아티스트 정의의 기준(Various 제외)"),
    "is_new_genre": ("사용자가 처음 듣는 장르인지", "명목(이진)", "", "1 = ug_cnt_now가 0. 취향 밖 장르 정의의 기준(unknown 제외)"),
    "u_nuniq_artist_now": ("사용자가 직전까지 들은 서로 다른 아티스트 수", "비율", "", "첫 등장 이벤트의 누적 합"),
    "u_nuniq_genre_now": ("사용자가 직전까지 들은 서로 다른 장르 수", "비율", "", "첫 등장 이벤트의 누적 합"),
    "u_newartist_ratio_now": ("사용자 청취 중 처음 듣는 아티스트였던 비율(탐색 성향)", "비율", "", "서로 다른 아티스트 수 ÷ 유효 아티스트 청취 수"),
    "u_avg_pop_now": ("사용자가 직전까지 들은 곡들의 평균 인기도", "비율", "", "log(1+곡 누적 청취 수)의 평균"),
    "pop_vs_user": ("이 곡의 인기도 − 사용자가 듣는 곡의 평균 인기도", "구간", "", "log(1+s_cnt_now) − u_avg_pop_now"),
    # 최근성
    "gap_u": ("사용자가 직전 곡을 들은 뒤 지난 행 수(로그)", "비율", "사용자의 첫 청취는 결측", "log(1+행 번호 차이). 청취 시각이 없어 행 번호로 간격을 셈"),
    "gap_s": ("이 곡이 (누구에게든) 마지막으로 재생된 뒤 지난 행 수(로그)", "비율", "곡의 첫 재생은 결측", "log(1+행 번호 차이)"),
    "gap_a": ("이 아티스트가 마지막으로 재생된 뒤 지난 행 수(로그)", "비율", "첫 재생·Various Artists는 결측", "log(1+행 번호 차이)"),
    "gap_ua": ("사용자가 이 아티스트를 마지막으로 들은 뒤 지난 행 수(로그)", "비율", "첫 청취·Various Artists는 결측", "log(1+행 번호 차이)"),
    "gap_ug": ("사용자가 이 장르를 마지막으로 들은 뒤 지난 행 수(로그)", "비율", "첫 청취·장르 unknown은 결측", "log(1+행 번호 차이)"),
    "u_w_short": ("최근 2만 행 동안 사용자의 청취 수", "비율", "", "현재 행 이전 2만 행 이내"),
    "u_w_long": ("최근 30만 행 동안 사용자의 청취 수", "비율", "", "현재 행 이전 30만 행 이내"),
    "s_w_short": ("최근 2만 행 동안 곡의 청취 수", "비율", "", ""),
    "s_w_long": ("최근 30만 행 동안 곡의 청취 수", "비율", "", ""),
    "a_w_short": ("최근 2만 행 동안 아티스트의 청취 수", "비율", "Various Artists는 결측", ""),
    "a_w_long": ("최근 30만 행 동안 아티스트의 청취 수", "비율", "Various Artists는 결측", ""),
    "ua_w_long": ("최근 30만 행 동안 사용자의 이 아티스트 청취 수", "비율", "Various Artists는 결측", ""),
    "ug_w_long": ("최근 30만 행 동안 사용자의 이 장르 청취 수", "비율", "장르 unknown은 결측", ""),
    "ua_share_recent": ("최근 30만 행 동안 사용자 청취 중 이 아티스트의 비율", "비율", "Various Artists는 결측", "ua_w_long ÷ max(u_w_long,1)"),
    "ug_share_recent": ("최근 30만 행 동안 사용자 청취 중 이 장르의 비율", "비율", "장르 unknown은 결측", "ug_w_long ÷ max(u_w_long,1)"),
    "s_velocity": ("곡 급상승 정도", "비율", "", "최근 30만 행 청취 ÷ (누적 청취 + 1)"),
    "a_velocity": ("아티스트 급상승 정도", "비율", "Various Artists는 결측", "최근 30만 행 청취 ÷ (누적 청취 + 1)"),
    "u_velocity": ("사용자 활동 증가 정도", "비율", "", "최근 30만 행 청취 ÷ (누적 청취 + 1)"),
    "prev_same_artist": ("사용자의 바로 앞 곡과 아티스트가 같은지", "명목(이진)", "사용자의 첫 청취는 결측", "1 = 같음"),
    "prev_same_genre": ("사용자의 바로 앞 곡과 장르가 같은지", "명목(이진)", "사용자의 첫 청취는 결측", "1 = 같음"),
    # 지연 정답
    "user_rate_lag": ("사용자 전체 재청취율(정답 지연 적용)", "비율", "행 위치가 앞쪽(전체의 43% 이전)이면 정답이 확정된 이력이 없어 결측", "(재청취 수 + 전체 평균×5) ÷ (청취 수 + 5). 현재 행보다 3,172,289행(43%) 이상 앞선 행의 정답만 사용"),
    "user_lag_n": ("사용자의 정답 확정 청취 수", "비율", "", "재청취율의 신뢰도"),
    "song_rate_lag": ("곡 재청취율", "비율", "위와 같음", "정답 지연 적용"),
    "song_lag_n": ("곡의 정답 확정 청취 수", "비율", "", ""),
    "artist_rate_lag": ("아티스트 재청취율", "비율", "위와 같음. Various Artists는 평균값", "정답 지연 적용"),
    "artist_lag_n": ("아티스트의 정답 확정 청취 수", "비율", "", ""),
    "genre_rate_lag": ("장르 재청취율", "비율", "위와 같음", "정답 지연 적용"),
    "user_artist_rate_lag": ("사용자 × 아티스트 재청취율", "비율", "위와 같음", "정답 지연 적용"),
    "user_genre_rate_lag": ("사용자 × 장르 재청취율", "비율", "위와 같음", "정답 지연 적용"),
    "user_lang_rate_lag": ("사용자 × 언어 재청취율", "비율", "위와 같음", "정답 지연 적용"),
    "user_pop_rate_lag": ("사용자가 인기곡을 들었을 때의 재청취율", "비율", "위와 같음", "인기곡 구간: 곡 누적 청취 수가 시기별 기준(12·21·28·35회) 이상"),
    "user_unpop_rate_lag": ("사용자가 비인기곡을 들었을 때의 재청취율", "비율", "위와 같음", "비인기곡 구간(위 기준 미만). 평가 지표의 비인기곡 정의와는 다름"),
    "user_newartist_rate_lag": ("사용자가 처음 듣는 아티스트였을 때의 재청취율", "비율", "위와 같음", "정답 지연 적용"),
    "user_ootgenre_rate_lag": ("사용자가 처음 듣는 장르였을 때의 재청취율", "비율", "위와 같음", "정답 지연 적용"),
    "user_popseg_rate_lag": ("현재 곡이 속한 인기 구간(인기/비인기)에서의 사용자 재청취율", "비율", "위와 같음", "인기곡이면 user_pop_rate_lag, 아니면 user_unpop_rate_lag"),
    "user_newseg_rate_lag": ("처음 듣는 아티스트면 신규 아티스트 재청취율, 아니면 사용자 × 아티스트 재청취율", "비율", "위와 같음", ""),
    "rate_gap_user_song": ("곡 재청취율 − 사용자 재청취율", "구간", "위와 같음", "song_rate_lag − user_rate_lag"),
    # SVD
    "svd_song_dot": ("사용자와 곡의 잠재 취향 내적", "구간", "결측은 없음. 곡이 SVD 학습 구간에 없으면 곡 벡터가 0이라 내적이 0", "사용자×곡 청취 행렬(log 변환)을 24차원 TruncatedSVD. 구간 시작 전 기록만 사용"),
    "svd_song_cos": ("사용자와 곡의 코사인 유사도", "구간", "", "−1 ~ 1"),
    "svd_artist_dot": ("사용자와 아티스트의 잠재 취향 내적", "구간", "Various Artists는 결측", "사용자×아티스트 행렬 24차원 SVD"),
    "svd_artist_cos": ("사용자와 아티스트의 코사인 유사도", "구간", "Various Artists는 결측", "−1 ~ 1"),
    # 노출 경로
    "src_tab": ("재생 탭 코드(source_system_tab)", "명목", "원본 결측은 unknown", "원본 source_system_tab을 코드로 변환. 모델에 범주형으로 지정. 코드 번호는 '범주코드표' 시트 참고"),
    "src_screen": ("재생 화면 코드(source_screen_name)", "명목", "원본 결측은 unknown", "원본 source_screen_name을 코드로 변환. 모델에 범주형으로 지정"),
    "src_type": ("재생 진입 경로 코드(source_type)", "명목", "원본 결측은 unknown", "원본 source_type을 코드로 변환. 모델에 범주형으로 지정"),
    "srctype_rate_lag": ("진입 경로별 재청취율", "비율", "정답 지연 적용(43% 앞쪽은 결측)", "정답 지연 적용"),
    "srcscreen_rate_lag": ("화면별 재청취율", "비율", "위와 같음", ""),
    "srctab_rate_lag": ("탭별 재청취율", "비율", "위와 같음", ""),
    "srctype_screen_rate_lag": ("진입 경로 × 화면 조합의 재청취율", "비율", "위와 같음", ""),
    "user_srctype_rate_lag": ("사용자 × 진입 경로 재청취율", "비율", "위와 같음", ""),
    "user_srcscreen_rate_lag": ("사용자 × 화면 재청취율", "비율", "위와 같음", ""),
    "user_srctab_rate_lag": ("사용자 × 탭 재청취율", "비율", "위와 같음", ""),
    "song_srctype_rate_lag": ("곡 × 진입 경로 재청취율", "비율", "위와 같음", ""),
    "artist_srctype_rate_lag": ("아티스트 × 진입 경로 재청취율", "비율", "위와 같음. Various Artists는 결측", ""),
    "ut_cnt_now": ("사용자가 이 진입 경로로 들은 누적 횟수", "비율", "", ""),
    "ut_share_now": ("사용자 전체 청취 중 이 진입 경로의 비율", "비율", "", "ut_cnt_now ÷ max(u_cnt_now,1)"),
    "ur_share_now": ("사용자 전체 청취 중 이 탭의 비율", "비율", "", ""),
    "uc_share_now": ("사용자 전체 청취 중 이 화면의 비율", "비율", "", ""),
    "st_share_now": ("곡 전체 재생 중 이 진입 경로의 비율", "비율", "", "곡×진입 경로 누적 ÷ max(s_cnt_now,1)"),
    "ut_share_recent": ("최근 30만 행 동안 사용자 청취 중 이 진입 경로의 비율", "비율", "", ""),
    "prev_same_srctype": ("사용자의 바로 앞 곡과 진입 경로가 같은지", "명목(이진)", "사용자의 첫 청취는 결측", "1 = 같음"),
    "prev_same_srcscreen": ("사용자의 바로 앞 곡과 재생 화면이 같은지", "명목(이진)", "사용자의 첫 청취는 결측", "1 = 같음"),
    # 라이브러리·라디오
    "s_local_share_now": ("곡 전체 재생 중 라이브러리 재생 비율", "비율", "", "라이브러리 재생 = source_type이 local-library 또는 local-playlist"),
    "s_local_n_now": ("이 곡이 라이브러리로 재생된 누적 횟수", "비율", "", ""),
    "s_radio_share_now": ("곡 전체 재생 중 라디오 재생 비율", "비율", "", "라디오 재생 = source_type이 radio"),
    "a_local_share_now": ("아티스트 전체 재생 중 라이브러리 재생 비율", "비율", "Various Artists는 결측", ""),
    "u_local_share_now": ("사용자 전체 청취 중 라이브러리 재생 비율", "비율", "", ""),
    "u_radio_share_now": ("사용자 전체 청취 중 라디오 재생 비율", "비율", "", ""),
    "ua_local_cnt_now": ("사용자가 이 아티스트를 라이브러리로 들은 누적 횟수", "비율", "Various Artists는 결측", ""),
    "ua_local_share_now": ("사용자가 이 아티스트를 들은 기록 중 라이브러리 재생 비율", "비율", "Various Artists는 결측", ""),
    "u_local_share_recent": ("최근 30만 행 동안 사용자 청취 중 라이브러리 재생 비율", "비율", "", ""),
    "u_w_tiny": ("최근 2천 행 동안 사용자의 청취 수(지금 연속으로 듣는 중인지)", "비율", "", ""),
    "ut_w_tiny": ("최근 2천 행 동안 사용자가 이 진입 경로로 들은 수", "비율", "", ""),
}
for k in range(9):
    D[f"s_tab{k}_share"] = (f"곡 전체 재생 중 '{TAB[k]}' 탭에서 재생된 비율", "비율", "", f"탭 코드 {k + 1} = {TAB[k]}. 곡 누적 재생(s_cnt_now) 대비")
    D[f"u_tab{k}_share"] = (f"사용자 전체 청취 중 '{TAB[k]}' 탭에서 들은 비율", "비율", "", f"탭 코드 {k + 1} = {TAB[k]}")
    D[f"a_tab{k}_share"] = (f"아티스트 전체 재생 중 '{TAB[k]}' 탭에서 재생된 비율", "비율", "Various Artists는 결측", f"탭 코드 {k + 1} = {TAB[k]}")
missing_desc = [c for c in FEATS if c not in D]
assert not missing_desc, missing_desc

BINARY = {c for c, v in D.items() if v[1] == "명목(이진)"}
CODE_RANGE = {
    "src_tab": "9개: " + ", ".join(f"{k} {v}" for k, v in MAP["src_tab"].items()),
    "src_screen": f"{len(MAP['src_screen'])}개 (코드표 시트 참고)",
    "src_type": "13개: " + ", ".join(f"{k} {v}" for k, v in MAP["src_type"].items()),
    "primary_genre_code": f"{df['primary_genre_code'].nunique()}개 (0 = unknown, 나머지는 코드표 시트 참고)",
    "language": "3 중국어, 52 영어, 31 한국어, 17 일본어, 10 대만어, 24 광둥어, 38·45(태국어)·59 등, -1 미상",
    "gender_code": "0 미상, 1 male, 2 female",
    "age_group": "0 미상, 1 10대 이하, 2 20대, 3 30대, 4 40대, 5 50대 이상",
}


def fmt(v):
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    return f"{v:.3g}"


def stat_text(c):
    s = df[c]
    nn = s.dropna()
    base = ""
    if c in CODE_RANGE:
        base = CODE_RANGE[c]
        if c in ("gender_code", "age_group"):
            vc = nn.value_counts(normalize=True).sort_index()
            base += " / 비중: " + ", ".join(f"{int(i)} {p * 100:.1f}%" for i, p in vc.items())
        return base
    if c in BINARY:
        p = (nn == 1).mean() * 100
        return f"1 = 해당({p:.2f}%), 0 = 아님"
    return f"{fmt(nn.min())} ~ {fmt(nn.max())}, 평균 {fmt(nn.mean())}, 중앙값 {fmt(nn.median())}"


def dtype_text(c):
    t = str(df[c].dtype)
    if c in ("msno", "song_id"):
        return "문자열"
    return "정수" if t.startswith(("int", "uint")) and not df[c].isna().any() else "실수"


def miss_text(c, reason):
    n = int(df[c].isna().sum())
    if n == 0:
        return "결측 없음"
    p = n / N * 100
    base = f"결측 {n:,}행({p:.1f}%)"
    return base + (" ← " + reason if reason else "")


rows = []
rows.append(["row_order", "원본 train.csv의 행 번호(시간 순서). 청취 시각이 없어 이 순서를 시간으로 사용", "정수", "순서", f"{int(df['row_order'].min()):,} ~ {int(df['row_order'].max()):,} (전체의 20~100% 구간)", "결측 없음", "구간 분할의 기준. 0~20% 구간은 특성 계산용 과거 이력으로만 사용해 이 표에 없음", "키"])
rows.append(["msno", "사용자 ID(암호화 문자열)", "문자열", "명목", f"고유 {df['msno'].nunique():,}명", "결측 없음", "원본 그대로. 모델 입력에서는 제외하고 사용자 단위 평가·분할에만 사용", "키"])
rows.append(["song_id", "곡 ID(암호화 문자열)", "문자열", "명목", f"고유 {df['song_id'].nunique():,}곡", "결측 없음", "원본 그대로. 모델 입력에서는 제외", "키"])
rows.append(["target", "정답 라벨: 한 달 안에 같은 곡을 다시 들었는지", "정수", "명목(이진)", f"1 = 재청취({df['target'].mean() * 100:.2f}%), 0 = 아님 (모델용 20~100% 구간 기준)", "결측 없음", "정답 누출 주의: target을 쓰는 특성은 현재 행보다 3,172,289행(43%) 이상 앞선 행의 정답만 사용", "정답"])
for g, cols in GROUPS.items():
    gname = {"노출경로": "노출 경로(source_*)", "라이브러리성향(v9)": "라이브러리·라디오 성향(source_*)", "경로프로필(v10)": "경로 프로필(source_*)", "정적": "곡·회원 속성", "누적": "누적 행동", "최근성": "최근성·연속성", "지연정답": "지연 정답 재청취율", "취향SVD": "취향 유사도(SVD)"}[g]
    for c in cols:
        desc, scale, reason, note = D[c]
        rows.append([c, desc, dtype_text(c), scale, stat_text(c), miss_text(c, reason), (note + (" | " if note else "") + NAN_DEF) if df[c].isna().any() else note, gname])

# ---------- 시트 만들기 ----------
wb = Workbook()
thin = Side(style="thin", color="BBBBBB")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
head_fill = PatternFill("solid", fgColor="1F4E8C")
grp_fill = {"키": "F2F2F2", "정답": "FDECEA", "곡·회원 속성": "FFFFFF", "누적 행동": "FFFFFF", "최근성·연속성": "FFFFFF"}


def write_table(ws, header, data, widths, start=4):
    for j, h in enumerate(header, 1):
        c = ws.cell(row=start, column=j, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    for i, r in enumerate(data, start + 1):
        for j, v in enumerate(r, 1):
            c = ws.cell(row=i, column=j, value=v)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = border
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = ws.cell(row=start + 1, column=2)


ws = wb.active
ws.title = "코드북"
ws["A1"] = "코드북(Codebook) — v11 모델 입력 데이터 명세서"
ws["A1"].font = Font(bold=True, size=14)
ws["A2"] = f"대상: 구간별 특성 파일(원본 통합 전처리 데이터에서 파생변수를 만든 결과). 키 3개 + 정답 1개 + 모델 입력 특성 129개. 행 {N:,}개(전체의 20~100% 구간). 척도: 명목/순서/구간/비율."
ws["A2"].alignment = Alignment(wrap_text=True)
ws.merge_cells("A2:H2")
ws.row_dimensions[2].height = 32
write_table(ws, ["변수명", "변수 설명(라벨)", "데이터타입", "척도(명목/순서/구간/비율)", "값 범위 / 값 라벨", "결측값 처리방식", "비고", "그룹"], rows, [26, 46, 10, 14, 50, 44, 60, 22])

# ---------- 데이터 구성 ----------
ws2 = wb.create_sheet("데이터 구성·규칙")
ws2["A1"] = "데이터 구성과 누수 방지 규칙"
ws2["A1"].font = Font(bold=True, size=14)
cnt = {b: len(pd.read_parquet(f"A/v12/featv12_{b}.parquet", columns=["row_order"])) for b in BLOCKS}
cfg_rows = [
    ["원본 데이터", "통합 전처리 데이터 data.csv (7,352,114행 × 24열)에서 파생변수를 계산"],
    ["모델용 데이터", f"{N:,}행. 원본 행 순서(row_order)의 20~100% 구간. 0~20%는 특성 계산용 과거 이력으로만 사용"],
    ["train", f"20~60% 구간 {cnt['train_a'] + cnt['train_b']:,}행 (train_a {cnt['train_a']:,} + train_b {cnt['train_b']:,}). 모델 학습"],
    ["valid", f"60~80% 구간 {cnt['valid']:,}행. 사용자 단위로 절반(tune)은 조기 종료·스태킹 학습, 나머지 절반(holdout)은 모델 선택"],
    ["test", f"80~100% 구간 {cnt['test']:,}행. 최종 모델 하나만 평가. 최종 모델은 train+valid로 다시 학습"],
    ["시간 순서", "무작위로 섞지 않고 row_order 순서로 분할. 청취 시각이 없어 시간 간격도 행 번호 차이로 계산"],
    ["특성 계산 시점", "정답을 쓰지 않는 특성은 현재 행 직전까지의 기록만으로 계산(현재 행·미래 행 제외). 취향 SVD는 각 구간 시작 전 기록만 사용"],
    ["정답 지연", "target을 쓰는 특성(*_rate_lag 등)은 현재 행보다 3,172,289행(전체의 43%, 약 한 달) 이상 앞선 행의 정답만 사용. 평활: (재청취 수 + 전체 평균×5) ÷ (청취 수 + 5)"],
    ["Various Artists", "아티스트 단위 특성은 Various Artists 행을 결측으로 둠"],
    ["결측 처리", "대체하지 않고 NaN 그대로 모델에 입력(LightGBM·XGBoost·CatBoost의 결측 처리 사용). 정답 지연 특성은 행 위치가 전체의 43% 앞쪽이면 결측"],
    ["범주형 지정", "모델에서 범주형으로 지정한 변수: primary_genre_code, src_tab, src_screen, src_type. 나머지는 숫자로 입력"],
    ["모델 입력 특성 수", "129개 = 곡·회원 속성 13 + 누적 행동 17 + 최근성·연속성 20 + 지연 정답 17 + 취향 SVD 4 + 노출 경로 20 + 라이브러리·라디오 성향 11 + 경로 프로필 27"],
]
write_table(ws2, ["항목", "내용"], cfg_rows, [26, 140])
ws2.freeze_panes = None

# ---------- 범주코드표 ----------
ws3 = wb.create_sheet("범주코드표")
ws3["A1"] = "범주형 변수의 코드 번호와 원본 값"
ws3["A1"].font = Font(bold=True, size=14)
code_rows = []
for col, mp in [("src_tab", MAP["src_tab"]), ("src_screen", MAP["src_screen"]), ("src_type", MAP["src_type"])]:
    for k, v in mp.items():
        code_rows.append([col, int(k), v])
for k, v in MAP["primary_genre_code"].items():
    code_rows.append(["primary_genre_code", int(k), v])
write_table(ws3, ["변수명", "코드", "원본 값"], code_rows, [24, 10, 50])

# ---------- 원본 컬럼 처리 ----------
ws4 = wb.create_sheet("원본 컬럼 처리")
ws4["A1"] = "원본 통합 데이터의 컬럼이 모델 입력에서 어떻게 쓰였는가"
ws4["A1"].font = Font(bold=True, size=14)
raw_rows = [
    ["row_order, msno, song_id, target", "키·정답으로 그대로 보존"],
    ["source_system_tab / source_screen_name / source_type", "범주 코드(src_tab, src_screen, src_type)로 변환해 모델 입력에 포함. 이 값으로 재청취율·비율 특성도 만듦"],
    ["song_length_min, is_short, is_long, n_genres, n_artists, language, is_various_artist", "그대로 입력"],
    ["primary_genre", "범주 코드(primary_genre_code)로 변환. 장르 관련 특성(ug_*, ug_share 등)과 '취향 밖 장르' 판정의 기준"],
    ["genre_ids", "모델 입력에서 제외(첫 장르 primary_genre만 사용)"],
    ["main_artist", "모델 입력에서 제외. 아티스트 단위 특성과 '새 아티스트' 판정의 기준으로 사용"],
    ["artist_name, artist_set", "모델 입력에서 제외"],
    ["bd_clean, age_group", "그대로 입력"],
    ["gender", "코드(gender_code: 0 미상, 1 male, 2 female)로 변환"],
    ["registration_init_time, expiration_date", "membership_days(만료일−가입일), reg_year(가입 연도)로 변환해 입력. 날짜 원본은 제외"],
]
write_table(ws4, ["원본 컬럼", "처리"], raw_rows, [70, 100])
ws4.freeze_panes = None
wb.save(OUT)
print("saved", OUT, "| 코드북 행", len(rows))
