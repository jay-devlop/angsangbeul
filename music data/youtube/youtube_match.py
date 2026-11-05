import argparse
import csv
import getpass
import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


# API 데이터는 장기간 그대로 두지 않고 다시 조회하도록 설정.
CACHE_DAYS = 29


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def duration_ms(value):
    """YouTube의 PT3M25S 형식을 밀리초로 변환."""
    match = re.fullmatch(
        r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?",
        value or "",
    )

    if not match:
        return None

    hours, minutes, seconds = (
        float(part or 0) for part in match.groups()
    )
    return round((hours * 3600 + minutes * 60 + seconds) * 1000)


class YouTube:
    def __init__(self):
        self.key = (
            os.getenv("YOUTUBE_API_KEY")
            or getpass.getpass("YouTube API 키 (숨김 입력): ").strip()
        )

        if not self.key:
            raise ValueError("API 키가 비어 있습니다.")

        self.session = requests.Session()
        self.last_request = 0

    def get(self, resource, params):
        # 키는 URL 대신 요청 헤더에 전달.
        headers = {"X-Goog-Api-Key": self.key}

        for attempt in range(3):
            time.sleep(
                max(0, 1 - (time.monotonic() - self.last_request))
            )
            self.last_request = time.monotonic()

            try:
                response = self.session.get(
                    f"https://www.googleapis.com/youtube/v3/{resource}",
                    headers=headers,
                    params=params,
                    timeout=30,
                )
            except requests.RequestException:
                if attempt == 2:
                    raise RuntimeError(
                        "네트워크 오류. 저장된 결과는 유지됩니다."
                    ) from None

                time.sleep(2 ** attempt)
                continue

            try:
                data = response.json()
            except ValueError:
                raise RuntimeError(
                    f"JSON 응답을 받지 못했습니다: HTTP {response.status_code}"
                ) from None

            if response.status_code >= 500 and attempt < 2:
                time.sleep(2 ** attempt)
                continue

            if response.status_code != 200:
                error = data.get("error", {})
                reasons = [
                    item.get("reason", "")
                    for item in error.get("errors", [])
                ]
                reason = ", ".join(reasons) or error.get(
                    "status", "unknown"
                )

                if any(
                    value in reasons
                    for value in (
                        "quotaExceeded",
                        "dailyLimitExceeded",
                        "rateLimitExceeded",
                        "userRateLimitExceeded",
                    )
                ) or response.status_code == 429:
                    raise RuntimeError(
                        f"할당량 또는 호출 제한: {reason}. "
                        "Google Cloud 할당량을 확인하고 나중에 재개하세요."
                    )

                raise RuntimeError(
                    f"YouTube 접근 실패: HTTP {response.status_code}, "
                    f"사유={reason}. "
                    "API 활성화·키 제한·프로젝트 설정을 확인하세요."
                )

            if not isinstance(data.get("items"), list):
                raise RuntimeError("예상하지 못한 YouTube 응답입니다.")

            return data["items"]

        raise RuntimeError("API 재시도 횟수를 초과했습니다.")

    def search(self, query, region):
        # 임베드 가능한 영상 후보를 검색.
        return self.get(
            "search",
            {
                "part": "snippet",
                "q": query,
                "type": "video",
                "maxResults": 5,
                "regionCode": region,
                "videoEmbeddable": "true",
                "videoSyndicated": "true",
            },
        )

    def video_details(self, ids):
        if not ids:
            return []

        return self.get(
            "videos",
            {
                "part": "snippet,contentDetails,status",
                "id": ",".join(ids),
            },
        )


def open_database(folder):
    folder.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(folder / "youtube_matches.sqlite")
    database.execute("PRAGMA journal_mode=WAL")

    database.executescript("""
        CREATE TABLE IF NOT EXISTS search_cache (
            region TEXT,
            query TEXT,
            payload TEXT,
            checked_at REAL,
            PRIMARY KEY (region, query)
        );

        CREATE TABLE IF NOT EXISTS results (
            song_id TEXT,
            region TEXT,
            status TEXT,
            payload TEXT,
            checked_at REAL,
            PRIMARY KEY (song_id, region)
        );
    """)

    # 오래된 메타데이터는 삭제하고 다음 검색 때 새로 조회.
    cutoff = time.time() - CACHE_DAYS * 86400
    database.execute(
        "DELETE FROM search_cache WHERE checked_at < ?",
        (cutoff,),
    )
    database.execute(
        "DELETE FROM results WHERE checked_at < ?",
        (cutoff,),
    )
    database.commit()

    return database


def search_candidates(database, api, query, region):
    cached = database.execute(
        """
        SELECT payload FROM search_cache
        WHERE region=? AND query=?
        """,
        (region, query),
    ).fetchone()

    if cached:
        return json.loads(cached[0])

    search_items = api.search(query, region)

    ids = []
    for item in search_items:
        video_id = item.get("id", {}).get("videoId")
        if video_id and video_id not in ids:
            ids.append(video_id)

    if search_items and not ids:
        raise RuntimeError("검색 응답에 유효한 videoId가 없습니다.")

    details = {
        item["id"]: item
        for item in api.video_details(ids)
    }

    candidates = []

    for rank, video_id in enumerate(ids, start=1):
        video = details.get(video_id)

        # 검색 후 삭제되거나 상세 조회가 불가능한 영상은 연결하지 않음.
        if video is None:
            continue

        snippet = video.get("snippet", {})
        content = video.get("contentDetails", {})
        status = video.get("status", {})
        restriction = content.get("regionRestriction", {})

        blocked = region in restriction.get("blocked", [])
        allowed = restriction.get("allowed")

        if allowed is not None and region not in allowed:
            blocked = True

        thumbnails = snippet.get("thumbnails", {})
        thumbnail = (
            thumbnails.get("high")
            or thumbnails.get("medium")
            or thumbnails.get("default")
            or {}
        ).get("url")

        candidates.append({
            "search_rank": rank,
            "video_id": video_id,
            "video_title": snippet.get("title"),
            "channel_id": snippet.get("channelId"),
            "channel_title": snippet.get("channelTitle"),
            "video_duration_ms": duration_ms(
                content.get("duration")
            ),
            "live_broadcast_content": snippet.get(
                "liveBroadcastContent"
            ),
            "embeddable": status.get("embeddable"),
            "region_blocked": blocked,
            "age_restricted": (
                content.get("contentRating", {}).get("ytRating")
                == "ytAgeRestricted"
            ),
            "thumbnail_url": thumbnail,
            "youtube_url": (
                f"https://www.youtube.com/watch?v={video_id}"
            ),
        })

    database.execute(
        """
        INSERT OR REPLACE INTO search_cache
        VALUES (?, ?, ?, ?)
        """,
        (
            region,
            query,
            json.dumps(candidates, ensure_ascii=False),
            time.time(),
        ),
    )
    database.commit()

    return candidates


def run(database, args):
    required = {"song_id", "name", "artist_name"}

    columns = set(
        pd.read_csv(args.input, nrows=0).columns
    )

    if required - columns:
        raise ValueError(
            f"필수 열이 없습니다: {sorted(required - columns)}"
        )

    # 지정하면 추천 결과에 포함된 곡만 검색.
    selected_ids = None

    if args.only:
        selected = pd.read_csv(
            args.only,
            dtype=str,
            keep_default_na=False,
        )

        if "song_id" not in selected:
            raise ValueError("--only 파일에 song_id 열이 필요합니다.")

        selected_ids = set(selected["song_id"].str.strip())

    api = None
    processed = 0

    with pd.read_csv(
        args.input,
        dtype=str,
        keep_default_na=False,
        chunksize=10000,
    ) as chunks:
        for chunk in chunks:
            for row in chunk.to_dict("records"):
                if not args.all and processed >= args.limit:
                    return

                song_id = row["song_id"].strip()

                if not song_id:
                    raise ValueError("빈 song_id가 있습니다.")

                if (
                    selected_ids is not None
                    and song_id not in selected_ids
                ):
                    continue

                completed = database.execute(
                    """
                    SELECT 1 FROM results
                    WHERE song_id=? AND region=?
                    """,
                    (song_id, args.region),
                ).fetchone()

                if completed:
                    continue

                title = row["name"].strip()
                artist = row["artist_name"].strip()

                length = pd.to_numeric(
                    row.get("song_length", ""),
                    errors="coerce",
                )
                kkbox_length = (
                    None if pd.isna(length) else float(length)
                )

                query = ""
                candidates = []

                if not title or not artist:
                    status = "insufficient_metadata"
                else:
                    # 공식 채널 여부를 보장하지 않으므로
                    # 'official'이라는 단어만으로 확정하지 않습니다.
                    query = " ".join(
                        f"{artist} {title}".split()
                    )

                    if api is None:
                        api = YouTube()

                    candidates = search_candidates(
                        database,
                        api,
                        query,
                        args.region,
                    )

                    for candidate in candidates:
                        length_ms = candidate["video_duration_ms"]
                        candidate["duration_difference_ms"] = (
                            abs(kkbox_length - length_ms)
                            if kkbox_length is not None
                            and length_ms is not None
                            else None
                        )

                        # 검색 순위·제목·길이만으로 동일 곡 확정 금지.
                        candidate["candidate_status"] = "needs_review"

                    status = (
                        "needs_review"
                        if candidates
                        else "no_usable_candidates"
                    )

                payload = {
                    "kkbox_title": title,
                    "kkbox_artist": artist,
                    "kkbox_isrc": row.get("isrc", "").strip(),
                    "query": query,
                    "candidates": candidates,
                }

                database.execute(
                    """
                    INSERT INTO results
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        song_id,
                        args.region,
                        status,
                        json.dumps(payload, ensure_ascii=False),
                        time.time(),
                    ),
                )

                # 곡마다 저장. 오류 난 곡은 완료 처리하지 않습니다.
                database.commit()
                processed += 1

                print(
                    f"{processed:,}: {title} / {artist}"
                    f" → {status}, 후보 {len(candidates)}개",
                    flush=True,
                )


def export_csv(database, folder, region):
    path = folder / f"youtube_candidates_{region}.csv"

    fields = [
        "song_id",
        "region",
        "status",
        "checked_at_utc",
        "kkbox_title",
        "kkbox_artist",
        "kkbox_isrc",
        "query",
        "search_rank",
        "video_id",
        "video_title",
        "channel_id",
        "channel_title",
        "video_duration_ms",
        "duration_difference_ms",
        "live_broadcast_content",
        "embeddable",
        "region_blocked",
        "age_restricted",
        "thumbnail_url",
        "youtube_url",
        "candidate_status",
    ]

    with path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        rows = database.execute(
            """
            SELECT song_id, region, status, payload, checked_at
            FROM results WHERE region=?
            """,
            (region,),
        )

        for song_id, country, status, payload, checked in rows:
            data = json.loads(payload)

            base = {
                "song_id": song_id,
                "region": country,
                "status": status,
                "checked_at_utc": datetime.fromtimestamp(
                    checked, timezone.utc
                ).isoformat(),
                "kkbox_title": data["kkbox_title"],
                "kkbox_artist": data["kkbox_artist"],
                "kkbox_isrc": data["kkbox_isrc"],
                "query": data["query"],
            }

            for candidate in data["candidates"] or [{}]:
                writer.writerow({**base, **candidate})

    print("CSV 저장:", path.resolve())


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "command",
        choices=["run", "review", "export"],
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("song_data.csv"),
    )
    parser.add_argument(
        "--folder",
        type=Path,
        default=Path("youtube_results"),
    )
    parser.add_argument(
        "--region",
        choices=["KR", "TW", "US"],
        default="KR",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
    )
    parser.add_argument(
        "--all",
        action="store_true",
    )
    parser.add_argument(
        "--only",
        type=Path,
        help="이 CSV의 song_id에 포함된 곡만 검색",
    )

    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit는 1 이상이어야 합니다.")

    database = open_database(args.folder)
    exit_code = 0

    try:
        if args.command == "run":
            run(database, args)

        if args.command in ("run", "export"):
            export_csv(database, args.folder, args.region)

        counts = dict(
            database.execute(
                """
                SELECT status, COUNT(*)
                FROM results
                WHERE region=?
                GROUP BY status
                """,
                (args.region,),
            )
        )

        print(f"\n[{args.region}] 곡 단위 처리 현황")
        for status, count in counts.items():
            print(f"  {status}: {count:,}")

    except KeyboardInterrupt:
        print("\n중단했습니다. 완료한 곡은 저장되어 있습니다.")
        export_csv(database, args.folder, args.region)

    except (
        RuntimeError,
        ValueError,
        OSError,
        sqlite3.Error,
        requests.RequestException,
    ) as error:
        print("\n중단:", error)
        export_csv(database, args.folder, args.region)
        exit_code = 1

    finally:
        database.close()

    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()