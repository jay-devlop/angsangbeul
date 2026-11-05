import getpass
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import requests


# Jamendo 곡 목록(API)을 전부 가져와 jamendo_results/jamendo_catalog.sqlite 에 저장합니다.
# 중간에 멈춰도 다시 실행하면 저장된 위치부터 이어서 수집합니다.
BASE = Path(__file__).resolve().parent
OUTPUT_DIR = BASE / "jamendo_results"

PAGE_SIZE = 200
REQUEST_INTERVAL = 1.0


def normalize(value):
    value = unicodedata.normalize(
        "NFKC", str(value or "")
    ).casefold()

    return re.sub(r"[\W_]+", "", value)


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


LOG_FILE = BASE / "jamendo_run.log"


def check_client_id(client_id):
    """입력한 키가 맞는지 요청 1건으로 확인. 문제가 없으면 None, 있으면 이유를 돌려줌."""
    try:
        response = requests.get(
            "https://api.jamendo.com/v3.0/tracks/",
            params={"client_id": client_id, "format": "json", "limit": 1},
            timeout=30,
        )
        headers = response.json().get("headers", {})
    except (requests.RequestException, ValueError):
        return "네트워크 또는 응답 오류로 키를 확인하지 못했습니다."

    if headers.get("status") != "success":
        return headers.get("error_message") or "키가 올바르지 않습니다."

    return None


def launch_in_background():
    """키를 먼저 물어보고, 맞으면 수집을 터미널과 분리해 백그라운드로 실행."""
    client_id = os.getenv("JAMENDO_CLIENT_ID", "").strip()

    for attempt in range(3):
        if not client_id:
            client_id = getpass.getpass(
                "Jamendo Client ID (입력은 화면에 보이지 않습니다): "
            ).strip()

        problem = check_client_id(client_id) if client_id else "키가 비어 있습니다."

        if problem is None:
            break

        print("키 확인 실패:", problem)
        client_id = ""
    else:
        raise ValueError("키를 3번 틀렸습니다. 다시 실행하세요.")

    command = [sys.executable, "-u", str(Path(__file__).resolve()), "--worker"]

    # 맥이 잠자기로 들어가 수집이 멈추지 않도록 caffeinate가 있으면 함께 사용.
    if shutil.which("caffeinate"):
        command = ["caffeinate", "-dimsu"] + command

    log = LOG_FILE.open("a", encoding="utf-8")

    subprocess.Popen(
        command,
        cwd=BASE,
        env={**os.environ, "JAMENDO_CLIENT_ID": client_id},
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # 터미널 창을 닫아도 계속 실행
    )

    print("\n수집을 백그라운드에서 시작했습니다. 터미널을 닫아도 계속됩니다.")
    print(f"진행 확인: tail -f {LOG_FILE.name}")
    print("멈추기:    pkill -f jamendo_match.py")
    print("끝나면 로그 마지막 줄에 '완료'가 나옵니다.")


def main():
    db = connect_database()

    try:
        collect_catalog(db)
        print("완료")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        if "--worker" in sys.argv:
            main()
        else:
            launch_in_background()
    except KeyboardInterrupt:
        print(
            "\n중단했습니다. "
            "다시 실행하면 저장된 페이지부터 재개합니다."
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
