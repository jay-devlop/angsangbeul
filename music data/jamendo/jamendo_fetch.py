import argparse
import csv
import getpass
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


API_URL = "https://api.jamendo.com/v3.0/tracks/"


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def parse_ids(value):
    """단일 ID, 구분자로 연결된 ID, JSON 배열을 처리합니다."""
    text = (value or "").strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        parsed = None

    if isinstance(parsed, list):
        values = parsed
    elif isinstance(parsed, (int, float)):
        values = [parsed]
    else:
        values = re.findall(r"\d+(?:\.0)?", text)

    result = []
    for value in values:
        track_id = str(value).strip()
        if track_id.endswith(".0"):
            track_id = track_id[:-2]
        if not track_id.isdigit():
            raise ValueError(f"잘못된 Jamendo ID: {value}")
        if track_id not in result:
            result.append(track_id)

    return result


def flatten(value, prefix="", output=None):
    """중첩 필드를 펼치고 배열은 JSON 문자열로 보존합니다."""
    if output is None:
        output = {}

    if isinstance(value, dict):
        if not value and prefix:
            output[prefix] = "{}"

        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else key
            flatten(item, name, output)

    elif isinstance(value, list):
        output[prefix] = json.dumps(value, ensure_ascii=False)

    else:
        output[prefix] = value

    return output


def fetch_track(session, client_id, track_id):
    # 요청 조건을 기록할 때 Client ID는 제외합니다.
    variants = [
        ("full_both", {"type": "single albumtrack", "include": "licenses musicinfo stats lyrics"}),
        ("full_default", {"include": "licenses musicinfo stats lyrics"}),
        ("full_single", {"type": "single", "include": "licenses musicinfo stats lyrics"}),
        ("basic_both", {"type": "single albumtrack"}),
        ("basic_default", {}),
    ]
    attempts = []
    basic_track = None
    for label, options in variants:
        params = {
            "format": "json", "id": track_id, "limit": 1,
            "audioformat": "mp32", "imagesize": 600, **options,
        }
        for retry in range(3):
            item = {"variant": label, "params": params.copy(),
                    "checked_at_utc": datetime.now(timezone.utc).isoformat()}
            try:
                response = session.get(
                    API_URL, params={**params, "client_id": client_id},
                    timeout=(15, 60),
                )
                item["http_status"] = response.status_code
                try:
                    data = response.json()
                except ValueError:
                    data = None
                if isinstance(data, dict):
                    item["response"] = data
                attempts.append(item)
                if response.status_code in (401, 403):
                    return {"status": "access_error", "stop": True,
                            "checked_at_utc": item["checked_at_utc"], "attempts": attempts}
                if response.status_code == 429 or response.status_code >= 500:
                    time.sleep(2 ** (retry + 1))
                    continue
                if response.status_code != 200 or not isinstance(data, dict):
                    break
                headers = data.get("headers", {})
                if headers.get("status") != "success":
                    # 요청 자체를 진행할 수 없는 오류는 저장 후 중단합니다.
                    if str(headers.get("code")) in {"4", "5", "6", "11", "12", "13", "101"}:
                        return {"status": "access_error", "stop": True,
                                "checked_at_utc": item["checked_at_utc"], "attempts": attempts}
                    break
                results = data.get("results", [])
                if not isinstance(results, list):
                    break
                track = next((x for x in results
                              if isinstance(x, dict) and str(x.get("id")) == track_id), None)
                if track is not None:
                    if "include" in options:
                        return {"status": "success", "track": track,
                                "checked_at_utc": item["checked_at_utc"],
                                "request_variant": label, "attempts": attempts}
                    basic_track = track
                break
            except requests.RequestException as error:
                item["error_type"] = type(error).__name__
                attempts.append(item)
                time.sleep(2 ** (retry + 1))
        time.sleep(0.3)
    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "attempts": attempts,
    }
    if basic_track is not None:
        return {**result, "status": "partial", "track": basic_track}
    # 모든 요청이 정상적인 빈 목록일 때만 empty_response로 기록.
    all_empty = bool(attempts) and all(
        x.get("http_status") == 200
        and isinstance(x.get("response"), dict)
        and x["response"].get("headers", {}).get("status") == "success"
        and x["response"].get("results") == []
        for x in attempts
    )
    return {**result, "status": "empty_response" if all_empty else "unresolved"}


def write_csv(path, mappings, cache):
    records = []
    api_fields = set()

    for mapping in mappings:
        track_id = mapping["jamendo_id"]
        entry = cache.get(track_id, {})
        api_data = flatten(entry.get("track", {}))
        api_fields.update(api_data)

        record = {
            "mapping.song_id": mapping["song_id"],
            "mapping.jamendo_id": track_id,
            "mapping.title": mapping["title"],
            "mapping.artist": mapping["artist"],
            "fetch.status": entry.get("status", "pending"),
            "fetch.checked_at_utc": entry.get("checked_at_utc", ""),
        }
        record.update(api_data)
        records.append(record)

    mapping_fields = [
        "mapping.song_id",
        "mapping.jamendo_id",
        "mapping.title",
        "mapping.artist",
        "fetch.status",
        "fetch.checked_at_utc",
    ]

    preferred = [
        "id",
        "name",
        "duration",
        "artist_id",
        "artist_name",
        "artist_idstr",
        "album_name",
        "album_id",
        "releasedate",
        "audio",
        "image",
        "album_image",
        "audiodownload",
        "audiodownload_allowed",
        "license_ccurl",
        "shareurl",
    ]

    fields = [name for name in preferred if name in api_fields]
    fields.extend(sorted(api_fields - set(fields)))

    temporary = path.with_suffix(path.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=mapping_fields + fields,
        )
        writer.writeheader()
        writer.writerows(records)

    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--retry-not-found", action="store_true",
                        help="이전 명령 호환용. 실패 결과는 기본으로 재조회합니다.")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        raise SystemExit(f"입력 파일이 없습니다: {input_path}")

    with input_path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)
        required = {"song_id", "candidate_ids"}

        if not required.issubset(reader.fieldnames or []):
            raise SystemExit(
                "입력 CSV에 song_id, candidate_ids 컬럼이 필요합니다."
            )

        source_rows = list(reader)

    if not source_rows:
        raise SystemExit("입력 CSV가 비어 있습니다.")

    mappings = []
    seen_pairs = set()

    for line_number, row in enumerate(source_rows, start=2):
        song_id = row["song_id"].strip()

        if not song_id:
            raise SystemExit(
                f"{line_number}번째 줄의 song_id가 비어 있습니다."
            )

        try:
            ids = parse_ids(row["candidate_ids"])
        except ValueError as error:
            raise SystemExit(f"{line_number}번째 줄: {error}")

        if not ids:
            raise SystemExit(
                f"{line_number}번째 줄의 candidate_ids가 비어 있습니다."
            )

        for track_id in ids:
            pair = (song_id, track_id)
            if pair in seen_pairs:
                continue

            seen_pairs.add(pair)
            mappings.append({
                "song_id": song_id,
                "jamendo_id": track_id,
                "title": row.get("title", ""),
                "artist": row.get("artist", ""),
            })

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else input_path.parent / "jamendo_381_full"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    csv_path = output_dir / "jamendo_381_full.csv"
    cache_path = output_dir / "jamendo_381_api_raw.json"

    cache = {}
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise SystemExit(
                "기존 저장 파일을 읽지 못했습니다. "
                "덮어쓰지 않고 종료합니다."
            )

        if not isinstance(cache, dict):
            raise SystemExit("기존 저장 파일 형식이 올바르지 않습니다.")

    track_ids = list(dict.fromkeys(
        item["jamendo_id"] for item in mappings
    ))

    pending = []
    for track_id in track_ids:
        status = cache.get(track_id, {}).get("status")

        if status == "success":
            continue


        pending.append(track_id)

    print(f"KKBox 고유 곡 수: {len({x['song_id'] for x in mappings}):,}")
    print(f"KKBox–Jamendo 연결 수: {len(mappings):,}")
    print(f"고유 Jamendo ID: {len(track_ids):,}")
    print(f"이번 조회 ID: {len(pending):,}")
    print(f"저장 폴더: {output_dir}")

    client_id = ""
    if pending:
        client_id = getpass.getpass(
            "Jamendo Client ID 입력 (화면에 표시되지 않음): "
        ).strip()

        if not client_id:
            raise SystemExit("Client ID를 입력해주세요.")

    interrupted = False

    try:
        with requests.Session() as session:
            for number, track_id in enumerate(pending, start=1):
                result = fetch_track(session, client_id, track_id)
                previous = cache.get(track_id, {})
                if "track" not in result and previous.get("track"):
                    result["track"] = previous["track"]
                    result["retained_previous_track"] = True
                cache[track_id] = result

                # ID 하나를 처리할 때마다 저장합니다.
                atomic_json(cache_path, cache)
                write_csv(csv_path, mappings, cache)

                print(
                    f"{number}/{len(pending)} "
                    f"ID={track_id} → {result['status']}",
                    flush=True,
                )
                if result.get("stop"):
                    print("요청 제한·인증 오류: 저장 후 중단합니다. 원본 응답을 확인하세요.")
                    break
                time.sleep(0.3)

    except KeyboardInterrupt:
        interrupted = True
        print("\n중단 요청을 받았습니다. 완료된 결과를 저장합니다.")

    finally:
        atomic_json(cache_path, cache)
        write_csv(csv_path, mappings, cache)

    counts = {}
    for track_id in track_ids:
        status = cache.get(track_id, {}).get("status", "pending")
        counts[status] = counts.get(status, 0) + 1

    print("\n[고유 Jamendo ID 기준 결과]")
    for status, count in sorted(counts.items()):
        print(f"{status}: {count:,}")

    print("\nCSV:", csv_path)
    print("원본 API 응답:", cache_path)

    if interrupted:
        print("같은 명령으로 다시 실행하면 이어서 진행합니다.")

    print(
        "partial: 기본 정보만 조회됨 / empty_response: 모든 조건에서 빈 응답 / "
        "unresolved: 오류 또는 예상과 다른 응답. 재생 여부를 뜻하지 않습니다."
    )


if __name__ == "__main__":
    main()
