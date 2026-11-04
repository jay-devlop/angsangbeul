import argparse
import csv
import getpass
import json
import os
import re
import sqlite3
import time
import unicodedata
from pathlib import Path

import pandas as pd
import requests
from datetime import datetime, timezone


# 이 코드를 music data/jamendo_match.py에 저장하세요.
BASE = Path(__file__).resolve().parent
INPUT_FILE = BASE / "song_data.csv"
OUTPUT_DIR = BASE / "jamendo_results"

PAGE_SIZE = 200
REQUEST_INTERVAL = 1.0


def normalize(value):
    value = unicodedata.normalize(
        "NFKC", str(value or "")
    ).casefold()

    return re.sub(r"[\W_]+", "", value)


def artist_aliases(value):
    """원문 이름, 괄호 밖 이름, 괄호 안 별칭을 비교."""
    aliases = {normalize(value)}

    for part in str(value).split("|"):
        aliases.add(normalize(part))

        outside = re.sub(r"\([^()]*\)", "", part)
        aliases.add(normalize(outside))

        for inside in re.findall(r"\(([^()]*)\)", part):
            aliases.add(normalize(inside))

    aliases.discard("")
    return aliases


def connect_database():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(
        OUTPUT_DIR / "jamendo_catalog.sqlite"
    )

    db.execute("PRAGMA journal_mode=WAL")

    db.executescript("""
        CREATE TABLE IF NOT EXISTS catalog (
            track_id TEXT PRIMARY KEY,
            title_key TEXT NOT NULL,
            payload TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS catalog_title_index
        ON catalog(title_key);

        CREATE TABLE IF NOT EXISTS progress (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    return db


def get_progress(db, key, default):
    row = db.execute(
        "SELECT value FROM progress WHERE key=?",
        (key,),
    ).fetchone()

    return row[0] if row else default


def set_progress(db, key, value):
    db.execute(
        "INSERT OR REPLACE INTO progress VALUES (?, ?)",
        (key, str(value)),
    )


class Jamendo:
    def __init__(self):
        self.client_id = (
            os.getenv("JAMENDO_CLIENT_ID")
            or getpass.getpass("Jamendo Client ID: ").strip()
        )

        if not self.client_id:
            raise ValueError("Client ID가 비어 있습니다.")

        self.session = requests.Session()
        self.last_request = 0

    def page(self, offset):
        for attempt in range(4):
            time.sleep(
                max(
                    0,
                    REQUEST_INTERVAL
                    - (time.monotonic() - self.last_request),
                )
            )
            self.last_request = time.monotonic()

            try:
                response = self.session.get(
                    "https://api.jamendo.com/v3.0/tracks/",
                    params={
                        "client_id": self.client_id,
                        "format": "json",
                        "audioformat": "mp32",
                        "limit": PAGE_SIZE,
                        "offset": offset,
                        "order": "id_asc",
                        # 기본값은 앨범 수록곡만 포함하므로
                        # 싱글도 명시적으로 포함.
                        "type": "single albumtrack",
                    },
                    timeout=60,
                )
            except requests.RequestException:
                if attempt == 3:
                    raise RuntimeError(
                        "네트워크 오류. 다시 실행하면 수집을 재개합니다."
                    ) from None

                time.sleep(2 ** attempt)
                continue

            if response.status_code == 429:
                wait = response.headers.get(
                    "Retry-After", "미지정"
                )
                raise RuntimeError(
                    f"호출 제한: Retry-After={wait}. "
                    "나중에 같은 명령으로 재개하세요."
                )

            if response.status_code >= 500 and attempt < 3:
                time.sleep(2 ** attempt)
                continue

            if response.status_code != 200:
                raise RuntimeError(
                    f"Jamendo HTTP 오류: {response.status_code}"
                )

            try:
                data = response.json()
            except ValueError:
                raise RuntimeError(
                    "JSON 응답을 받지 못했습니다."
                ) from None

            headers = data.get("headers", {})

            if headers.get("status") != "success":
                raise RuntimeError(
                    "Jamendo API 오류: "
                    f"code={headers.get('code')}, "
                    f"message={headers.get('error_message')}"
                )

            tracks = data.get("results")

            if not isinstance(tracks, list):
                raise RuntimeError(
                    "예상하지 못한 Jamendo 응답입니다."
                )

            if any(
                not isinstance(track, dict)
                or not track.get("id")
                or "name" not in track
                or "artist_name" not in track
                for track in tracks
            ):
                raise RuntimeError(
                    "곡 데이터 구조가 예상과 다릅니다."
                )

            return tracks

        raise RuntimeError("재시도 횟수를 초과했습니다.")


def collect_catalog(db):
    if get_progress(db, "complete", "0") == "1":
        count = db.execute(
            "SELECT COUNT(*) FROM catalog"
        ).fetchone()[0]

        print(f"저장된 Jamendo 목록 사용: {count:,}곡")
        return

    offset = int(get_progress(db, "offset", "0"))
    api = Jamendo()

    print(f"Jamendo 목록 수집 시작: offset={offset:,}")
    print("음원 파일은 다운로드하지 않습니다.")

    while True:
        tracks = api.page(offset)

        if not tracks:
            set_progress(db, "complete", "1")
            set_progress(db, "completed_at", time.time())
            db.commit()
            break

        before = db.execute(
            "SELECT COUNT(*) FROM catalog"
        ).fetchone()[0]

        for track in tracks:
            # 로컬 비교와 재생 연결에 필요한 정보만 저장.
            item = {
                "id": str(track["id"]),
                "name": track["name"],
                "artist_name": track["artist_name"],
                "duration": track.get("duration"),
                "audio": track.get("audio"),
                "audiodownload_allowed": track.get(
                    "audiodownload_allowed"
                ),
                "license_ccurl": track.get("license_ccurl"),
                "shareurl": track.get("shareurl"),
            }

            db.execute(
                """
                INSERT OR REPLACE INTO catalog
                VALUES (?, ?, ?)
                """,
                (
                    item["id"],
                    normalize(item["name"]),
                    json.dumps(item, ensure_ascii=False),
                ),
            )

        after = db.execute(
            "SELECT COUNT(*) FROM catalog"
        ).fetchone()[0]

        # API가 offset을 무시하거나 같은 페이지를 반복하면 중단.
        if after == before:
            db.rollback()
            raise RuntimeError(
                "새 곡이 없는 페이지가 반복됐습니다. "
                "API 페이지 제한 또는 카탈로그 변경을 확인하세요."
            )

        offset += len(tracks)
        set_progress(db, "offset", offset)

        # 페이지마다 곡 정보와 수집 위치를 함께 저장.
        db.commit()

        print(
            f"Jamendo 저장: {after:,}곡 / offset={offset:,}",
            flush=True,
        )

        # 마지막 페이지 다음에 빈 페이지가 나오는지까지 확인.
        # 중간 오류를 카탈로그 끝으로 잘못 처리하지 않음.

    count = db.execute(
        "SELECT COUNT(*) FROM catalog"
    ).fetchone()[0]

    print(f"Jamendo API 목록 수집 완료: {count:,}곡")


def compare_candidate(song, track):
    artist_equal = bool(
        artist_aliases(song["artist_name"])
        & artist_aliases(track["artist_name"])
    )

    kkbox_ms = pd.to_numeric(
        song.get("song_length", ""),
        errors="coerce",
    )
    jamendo_seconds = pd.to_numeric(
        track.get("duration"),
        errors="coerce",
    )

    difference = None

    if pd.notna(kkbox_ms) and pd.notna(jamendo_seconds):
        difference = abs(
            float(kkbox_ms) - float(jamendo_seconds) * 1000
        )

    if not artist_equal:
        status = "artist_mismatch"
    elif difference is not None and difference > 5000:
        status = "duration_mismatch"
    else:
        # 제목·가수·길이가 비슷해도 동일 녹음 확정은 아님.
        status = "needs_review"

    return {
        "candidate_status": status,
        "artist_equal": artist_equal,
        "jamendo_id": track["id"],
        "jamendo_title": track["name"],
        "jamendo_artist": track["artist_name"],
        "jamendo_duration_seconds": track.get("duration"),
        "duration_difference_ms": difference,
        "audio_url": track.get("audio"),
        "download_allowed": track.get("audiodownload_allowed"),
        "license_url": track.get("license_ccurl"),
        "track_page": track.get("shareurl"),
    }


def match_all(db, input_file):
    required = {"song_id", "name", "artist_name"}

    columns = set(
        pd.read_csv(input_file, nrows=0).columns
    )

    if required - columns:
        raise ValueError(
            f"필수 열 누락: {sorted(required - columns)}"
        )

    final_path = (
        OUTPUT_DIR / "kkbox_jamendo_candidates.csv"
    )
    temporary_path = final_path.with_suffix(".csv.tmp")

    fields = [
        "song_id",
        "kkbox_title",
        "kkbox_artist",
        "kkbox_isrc",
        "status",
        "candidate_count",
        "candidate_status",
        "artist_equal",
        "jamendo_id",
        "jamendo_title",
        "jamendo_artist",
        "jamendo_duration_seconds",
        "duration_difference_ms",
        "audio_url",
        "download_allowed",
        "license_url",
        "track_page",
    ]

    processed = 0
    output_rows = 0
    counts = {}

    print("\nKKBox 전체 로컬 비교 시작")
    print("이 단계에서는 Jamendo API를 호출하지 않습니다.")

    with temporary_path.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        with pd.read_csv(
            input_file,
            dtype=str,
            keep_default_na=False,
            chunksize=10000,
        ) as chunks:
            for chunk in chunks:
                for song in chunk.to_dict("records"):
                    song_id = song["song_id"].strip()
                    title = song["name"].strip()
                    artist = song["artist_name"].strip()

                    if not song_id:
                        raise ValueError(
                            "빈 song_id가 있습니다."
                        )

                    candidates = []

                    if not title or not artist:
                        status = "insufficient_metadata"
                    else:
                        # 공백·대소문자·구두점을 정리한 제목으로
                        # 인덱스 조회. 부분 제목 검색은 하지 않음.
                        records = db.execute(
                            """
                            SELECT payload FROM catalog
                            WHERE title_key=?
                            """,
                            (normalize(title),),
                        )

                        for record in records:
                            track = json.loads(record[0])
                            candidates.append(
                                compare_candidate(song, track)
                            )

                        if not candidates:
                            status = "no_title_match"
                        elif any(
                            c["candidate_status"] == "needs_review"
                            for c in candidates
                        ):
                            status = "needs_review"
                        elif any(
                            c["artist_equal"]
                            for c in candidates
                        ):
                            status = "duration_mismatch"
                        else:
                            status = "artist_mismatch"

                    base = {
                        "song_id": song_id,
                        "kkbox_title": title,
                        "kkbox_artist": artist,
                        "kkbox_isrc": song.get("isrc", ""),
                        "status": status,
                        "candidate_count": len(candidates),
                    }

                    for candidate in candidates or [{}]:
                        writer.writerow({
                            **base,
                            **candidate,
                        })
                        output_rows += 1

                    processed += 1
                    counts[status] = counts.get(status, 0) + 1

                    if processed % 10000 == 0:
                        file.flush()
                        print(
                            f"KKBox 비교 완료: {processed:,}곡",
                            flush=True,
                        )

    # 비교가 끝난 경우에만 기존 10곡 결과를 교체.
    # 중간 오류가 나면 기존 결과 파일은 그대로 유지.
    os.replace(temporary_path, final_path)

    summary = {
        "kkbox_processed_songs": processed,
        "jamendo_catalog_tracks": db.execute(
            "SELECT COUNT(*) FROM catalog"
        ).fetchone()[0],
        "output_rows": output_rows,
        "song_status_counts": counts,
        "verified_recording_matches": 0,
        "method": (
            "normalized exact title + artist aliases + duration review"
        ),
        "finished_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    summary_path = OUTPUT_DIR / "summary.json"
    summary_temp = summary_path.with_suffix(".json.tmp")

    summary_temp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(summary_temp, summary_path)

    print("\n전체 비교 완료")
    print(f"비교한 KKBox 곡: {processed:,}")
    print(f"CSV 행 수: {output_rows:,}")

    for status, count in counts.items():
        print(f"  {status}: {count:,}곡")

    print("\n결과:", final_path)
    print("집계:", summary_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=INPUT_FILE,
    )
    parser.add_argument(
        "--match-only",
        action="store_true",
        help="목록 수집 완료 후 로컬 비교만 다시 실행",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        raise ValueError(
            f"통합 CSV를 찾을 수 없습니다: {args.input}"
        )

    db = connect_database()

    try:
        if args.match_only:
            if get_progress(db, "complete", "0") != "1":
                raise ValueError(
                    "Jamendo 목록 수집이 완료되지 않았습니다. "
                    "--match-only 없이 먼저 실행하세요."
                )
        else:
            collect_catalog(db)

        match_all(db, args.input)

    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(
            "\n중단했습니다. "
            "목록 수집은 다시 실행하면 저장된 페이지부터 재개합니다. "
            "로컬 비교 중 중단했다면 비교 단계는 처음부터 다시 진행합니다."
        )
    except (
        RuntimeError,
        ValueError,
        OSError,
        sqlite3.Error,
        requests.RequestException,
    ) as error:
        print("\n중단:", error)
        raise SystemExit(1) from None