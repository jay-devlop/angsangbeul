"""[1~3단계 앞부분] 데모 사용자 선정 + 사용자 x 웹곡(344) 쌍의 '원시 행' 생성.
출력(server/data/): pairs_raw.parquet (v11.py 가 읽는 data.csv 열 형식), demo_users.json (서버 전용: 가명 ↔ 실제 ID)
쌍 행의 정답(target)은 모른다 -> 0. 재생 경로는 discover 탭 고정. 곡 정보는 song_data.csv, 사용자 정보는 data.csv 의 그 사용자 행.
사용: python3 web/tools/prepare_pairs.py"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "server" / "data"
N_ORIG = 7377418
MIN_PLAYS = 400
SRC = {"source_system_tab": "discover", "source_screen_name": "Online playlist more", "source_type": "online-playlist"}

cat = json.load(open(ROOT / "web/data/catalog.json"))
kk = sorted({a for a, b in cat["songMap"]})
songs = pd.read_csv(ROOT / "music data/song_data.csv").set_index("song_id").loc[kk].reset_index()
d = pd.read_csv(ROOT / "data.csv")

# 곡 열: data.csv 와 같은 규칙으로 계산 (길이=ms/60000, 짧음<1분, 김>10분, 장르=코드 목록의 첫 값)
sp = songs.copy()
sp["song_length_min"] = (sp["song_length"] / 60000).round(3)
sp["is_short"] = (sp["song_length_min"] < 1).astype(float)
sp["is_long"] = (sp["song_length_min"] > 10).astype(float)
g = sp["genre_ids"].fillna("").astype(str)
sp["primary_genre"] = g.str.split("|").str[0].replace("", "unknown").replace("nan", "unknown")
sp["n_genres"] = g.apply(lambda x: float(len([t for t in x.split("|") if t])))
parts = sp["artist_name"].fillna("").apply(lambda a: [t.strip() for p in a.split("|") for t in p.split(" feat. ") if t.strip()])
sp["main_artist"] = parts.apply(lambda p: p[0] if p else "unknown")
sp["n_artists"] = parts.apply(lambda p: float(max(len(p), 1)))
sp["is_various_artist"] = (sp["main_artist"] == "Various Artists").astype(float)
# 데이터에 이미 있는 곡은 data.csv 값을 우선 사용
have = d[d.song_id.isin(kk)].drop_duplicates("song_id").set_index("song_id")
for c in ["song_length_min", "is_short", "is_long", "primary_genre", "n_genres", "main_artist", "n_artists", "is_various_artist", "language"]:
    if c in have.columns:
        m = sp["song_id"].map(have[c])
        sp[c] = m.where(m.notna(), sp[c])
sp = sp[["song_id", "song_length_min", "is_short", "is_long", "primary_genre", "n_genres", "main_artist", "n_artists", "is_various_artist", "language"]]
print("곡", len(sp), "| data.csv 에 이미 있는 곡", len(have))

# 사용자 선정: 웹 곡 장르(genres.json 11개)마다 '그 장르를 가장 많이 듣는' 실제 사용자 1명 (겹침 없음)
tracks = {t["id"]: t for t in cat["tracks"]}
gdef = json.load(open(ROOT / "web/data/genres.json", encoding="utf-8"))["genres"]
GENRES = [g["name"] for g in gdef]
tag2name = {tg: g["name"] for g in gdef for tg in g["tags"]}
song_genre = {}
for k, j in cat["songMap"]:
    song_genre.setdefault(k, next((tag2name[t] for t in tracks[j]["genres"] if t in tag2name), None))
sp["web_genre"] = sp["song_id"].map(song_genre)
code_w = {}   # 장르 -> {KKBox 장르 코드: 가중치}  (그 장르 웹 곡이 가진 코드 비율, 상위 3개)
for gname in GENRES:
    c = sp[(sp.web_genre == gname) & (sp.primary_genre != "unknown")].primary_genre.value_counts()
    c = c.head(3)
    code_w[gname] = (c / c.sum()).to_dict() if len(c) else {}
print("장르별 웹 곡 수/대표 코드:", {g: (int((sp.web_genre == g).sum()), code_w[g]) for g in GENRES})

cnt = d.groupby("msno").size()
cand = cnt[cnt >= MIN_PLAYS].index
dc = d[d.msno.isin(cand)]
share = dc.groupby(["msno", "primary_genre"]).size().unstack(fill_value=0)
share = share.div(share.sum(axis=1), axis=0)
ORDER = ["팝", "록·메탈", "일렉트로닉", "영상 음악", "힙합", "월드", "lofi", "포크", "재즈", "R&B", "기타"]   # 구분이 쉬운 장르부터
assert set(ORDER) == set(GENRES)
pick, used, report = {}, set(), []
for gname in ORDER:
    sc = sum(w * share[c] for c, w in code_w[gname].items() if c in share.columns)
    sc = sc[~sc.index.isin(used)].sort_values(ascending=False)
    u = sc.index[0]
    pick[gname] = u; used.add(u)
    report.append({"장르": gname, "웹곡수": int((sp.web_genre == gname).sum()), "대표코드": list(code_w[gname]), "재생수": int(cnt[u]), "대표코드_비중": round(float(sc.iloc[0]), 3)})
print(pd.DataFrame(report).to_string(index=False))

mem_cols = ["bd_clean", "age_group", "gender", "registration_init_time", "expiration_date"]
mem = d.drop_duplicates("msno").set_index("msno").loc[list(pick.values()), mem_cols]
rows, i = [], 0
for u in pick.values():
    for _, s in sp.iterrows():
        r = {"row_order": N_ORIG + i, "msno": u, "song_id": s.song_id, **SRC, "target": 0}
        r.update({c: s[c] for c in sp.columns if c != "song_id"})
        r.update(mem.loc[u].to_dict())
        rows.append(r); i += 1
pr = pd.DataFrame(rows)
for c in d.columns:
    if c not in pr.columns:
        pr[c] = np.nan   # artist_name, artist_set, genre_ids 등 특성에 안 쓰는 열
pr = pr[d.columns]
OUT.mkdir(parents=True, exist_ok=True)
json.dump(report, open(OUT / "demo_selection_report.json", "w"), ensure_ascii=False, indent=1)
pr.to_parquet(OUT / "pairs_raw.parquet", index=False)
json.dump(pick, open(OUT / "demo_users.json", "w"), ensure_ascii=False, indent=1)
print("쌍", len(pr), "저장 완료")
# 서버가 화면에 내보내는 사용자 정보: 장르 이름 + 자주 듣는 아티스트 3명 (실제 ID는 내보내지 않음)
prof = []
for gname, u in pick.items():
    top3 = d[(d.msno == u) & (d.is_various_artist != 1)].main_artist.value_counts().head(3)
    prof.append({"id": gname, "label": gname + " 리스너", "topArtists": list(top3.index)})
json.dump(prof, open(OUT / "demo_profiles.json", "w"), ensure_ascii=False, indent=1)
