"""Jamendo 수집 CSV → 앱용 data/catalog.json 변환 (원본 CSV는 수정하지 않음, API 호출 없음)

사용: python3 web/tools/build_catalog.py [CSV 경로]
- fetch.status == success 인 행만 사용
- 곡 목록은 mapping.jamendo_id 기준 중복 제거, song_id → jamendo_id 매핑은 success 행 전부 유지
- 파일이 없거나 필수 열이 없으면 임의 데이터로 대체하지 않고 오류로 멈춤
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]            # 음악 추천/
OUT = Path(__file__).resolve().parents[1] / "data" / "catalog.json"
CANDIDATES = [
    ROOT / "music data/jamendo_results/jamendo_381_full/jamendo_381_full.csv",   # 요청서에 적힌 경로
    ROOT / "music data/jamendo/jamendo_full/jamendo_full.csv",                   # 현재 프로젝트의 실제 경로
]
REQUIRED = [
    "mapping.song_id", "mapping.jamendo_id", "fetch.status", "name", "artist_name", "album_name",
    "duration", "audio", "image", "album_image", "musicinfo.tags.genres", "lyrics",
    "license_ccurl", "shareurl",
]


def find_csv():
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    for p in CANDIDATES:
        if p.is_file():
            return p
    raise SystemExit("입력 CSV를 찾지 못했습니다. 확인한 경로:\n" + "\n".join(f"  {p}" for p in CANDIDATES))


def parse_genres(text):
    text = (text or "").strip()
    if not text:
        return []
    try:
        value = json.loads(text)
    except ValueError:
        return []
    return [str(g).strip() for g in value if str(g).strip()] if isinstance(value, list) else []


def to_int(text):
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return 0


def main():
    src = find_csv()
    csv.field_size_limit(10**9)
    with src.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)                      # 가사의 쉼표·따옴표·줄바꿈은 CSV 파서가 처리
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"필수 열이 없습니다: {missing}")
        rows = list(reader)

    ok = [r for r in rows if r["fetch.status"] == "success"]
    tracks, seen, mapping = [], set(), []
    for r in ok:
        jid = r["mapping.jamendo_id"].strip()
        mapping.append([r["mapping.song_id"].strip(), int(jid)])
        if jid in seen:
            continue
        seen.add(jid)
        tracks.append({
            "id": int(jid),
            "name": r["name"].strip(),
            "artist": r["artist_name"].strip(),
            "album": r["album_name"].strip(),
            "duration": to_int(r["duration"]),
            "audio": r["audio"].strip(),
            "image": r["image"].strip(),
            "albumImage": r["album_image"].strip(),
            "genres": parse_genres(r["musicinfo.tags.genres"]),
            "lyrics": r["lyrics"].strip(),
            "license": r["license_ccurl"].strip(),
            "share": r["shareurl"].strip(),
            "listens": to_int(r.get("stats.rate_listened_total")),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"tracks": tracks, "songMap": mapping}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"입력: {src}")
    print(f"전체 {len(rows)}행 / success {len(ok)}행 / 고유 곡 {len(tracks)}곡 / 매핑 {len(mapping)}행")
    print(f"저장: {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
