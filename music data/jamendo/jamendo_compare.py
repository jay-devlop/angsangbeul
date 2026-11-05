import csv
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


BASE = Path(__file__).resolve().parent

INPUT_FILE = BASE / "song_data.csv"
OUTPUT_DIR = BASE / "jamendo_results"
DB_PATH = OUTPUT_DIR / "jamendo_catalog.sqlite"

RESULT_PATH = OUTPUT_DIR / "kkbox_jamendo_candidates.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"


def normalize(value):
    value = unicodedata.normalize(
        "NFKC", str(value or "")
    ).casefold()

    return re.sub(r"[\W_]+", "", value)


def artist_aliases(value):
    aliases = {normalize(value)}

    for part in str(value).split("|"):
        aliases.add(normalize(part))

        # 괄호 밖 이름
        aliases.add(
            normalize(re.sub(r"\([^()]*\)", "", part))
        )

        # 괄호 안 영문 이름 등
        for alias in re.findall(r"\(([^()]*)\)", part):
            aliases.add(normalize(alias))

    aliases.discard("")
    return aliases


def compare_candidate(song, track):
    artist_equal = bool(
        artist_aliases(song["artist_name"])
        & artist_aliases(track.get("artist_name", ""))
    )

    kkbox_length = pd.to_numeric(
        song.get("song_length", ""),
        errors="coerce",
    )
    jamendo_length = pd.to_numeric(
        track.get("duration"),
        errors="coerce",
    )

    difference = None

    if pd.notna(kkbox_length) and pd.notna(jamendo_length):
        difference = abs(
            float(kkbox_length) - float(jamendo_length) * 1000
        )

    if not artist_equal:
        status = "artist_mismatch"
    elif difference is not None and difference > 5000:
        status = "duration_mismatch"
    else:
        # 동일 녹음인지 확인 전까지 자동 확정하지 않음.
        status = "needs_review"

    return {
        "candidate_status": status,
        "artist_equal": artist_equal,
        "jamendo_id": track.get("id"),
        "jamendo_title": track.get("name"),
        "jamendo_artist": track.get("artist_name"),
        "jamendo_duration_seconds": track.get("duration"),
        "duration_difference_ms": difference,
        "audio_url": track.get("audio"),
        "download_allowed": track.get("audiodownload_allowed"),
        "license_url": track.get("license_ccurl"),
        "track_page": track.get("shareurl"),
    }


def main():
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"통합 CSV를 찾을 수 없습니다: {INPUT_FILE}"
        )

    if not DB_PATH.is_file():
        raise FileNotFoundError(
            f"Jamendo DB를 찾을 수 없습니다: {DB_PATH}"
        )

    required = {"song_id", "name", "artist_name"}
    columns = set(
        pd.read_csv(INPUT_FILE, nrows=0).columns
    )

    if required - columns:
        raise ValueError(
            f"필수 열 누락: {sorted(required - columns)}"
        )

    # 읽기 전용 연결: 수집 DB에 쓰지 않음.
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=30)

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

    temporary_result = RESULT_PATH.with_suffix(".csv.tmp")
    temporary_summary = SUMMARY_PATH.with_suffix(".json.tmp")

    counts = Counter()
    processed = 0
    output_rows = 0

    try:
        # 비교 도중 수집량이 늘어도 동일한 시점의 데이터를 읽음.
        db.execute("BEGIN")

        catalog_count = db.execute(
            "SELECT COUNT(*) FROM catalog"
        ).fetchone()[0]

        started_at = datetime.now(timezone.utc).isoformat()

        print(f"비교 기준 Jamendo 곡 수: {catalog_count:,}곡")
        print("API 호출 없이 KKBox 전체와 비교합니다.")
        print("수집 종료 표시는 확인하지 않습니다.")
        print("완료 후 기존 결과 CSV를 덮어씁니다.\n")

        with temporary_result.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as file:
            writer = csv.DictWriter(
                file,
                fieldnames=fields,
            )
            writer.writeheader()

            with pd.read_csv(
                INPUT_FILE,
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
                                candidate["candidate_status"]
                                == "needs_review"
                                for candidate in candidates
                            ):
                                status = "needs_review"

                            elif any(
                                candidate["artist_equal"]
                                for candidate in candidates
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

                        counts[status] += 1
                        processed += 1

                    file.flush()

                    print(
                        f"비교 완료: {processed:,}곡"
                        f" / 검토 후보 곡: "
                        f"{counts['needs_review']:,}곡",
                        flush=True,
                    )

        summary = {
            "started_at_utc": started_at,
            "finished_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "jamendo_catalog_tracks_at_start": catalog_count,
            "kkbox_processed_songs": processed,
            "output_rows": output_rows,
            "song_status_counts": dict(counts),
            "verified_recording_matches": 0,
            "scope": "비교 시작 시점에 수집된 Jamendo 목록",
            "method": (
                "정규화한 제목 일치 → 아티스트 별칭·길이 비교"
            ),
        }

        temporary_summary.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # 비교가 모두 끝난 뒤 기존 결과를 교체.
        os.replace(temporary_result, RESULT_PATH)
        os.replace(temporary_summary, SUMMARY_PATH)

        print("\n비교 완료")

        for status, count in counts.items():
            print(f"  {status}: {count:,}곡")

        print("\nCSV:", RESULT_PATH)
        print("집계:", SUMMARY_PATH)

    finally:
        # 읽기 트랜잭션 종료.
        db.rollback()
        db.close()


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            "\n비교를 중단했습니다. "
            "기존 결과 CSV는 유지됩니다. "
            "다시 실행하면 비교는 처음부터 진행합니다."
        )

    except (
        OSError,
        ValueError,
        sqlite3.Error,
    ) as error:
        print("\n비교 실패:", error)
        raise SystemExit(1) from None