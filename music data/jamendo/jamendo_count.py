import sqlite3
from pathlib import Path

import requests


BASE = Path(__file__).resolve().parent
DB_PATH = BASE / "jamendo_results" / "jamendo_catalog.sqlite"

client_id = input("Jamendo Client ID를 입력하세요: ").strip()

if not client_id:
    raise SystemExit("Client ID가 비어 있습니다.")

try:
    response = requests.get(
        "https://api.jamendo.com/v3.0/tracks/",
        params={
            "client_id": client_id,
            "format": "json",
            "limit": 1,
            "offset": 0,
            "fullcount": "true",
            "type": "single albumtrack",
            "order": "id_asc",
        },
        timeout=60,
    )

    if response.status_code != 200:
        raise SystemExit(
            f"HTTP 오류: {response.status_code}"
        )

    data = response.json()
    headers = data.get("headers", {})

    if headers.get("status") != "success":
        raise SystemExit(
            f"API 오류: {headers.get('error_message')}"
        )

    total_value = headers.get("results_fullcount")
    total = None

    print("\n[API 응답]")

    if total_value is None:
        print("전체 개수가 응답에 없습니다.")
    else:
        total = int(total_value)
        pages = (total + 199) // 200

        print(f"API가 보고한 전체 곡 수: {total:,}곡")
        print(f"200곡 기준 예상 페이지: {pages:,}개")

    if headers.get("warnings"):
        print("API 경고:", headers["warnings"])

    print("\n[현재 저장된 데이터]")

    if not DB_PATH.is_file():
        print("저장 DB를 찾지 못했습니다.")
        print("확인 경로:", DB_PATH)

    else:
        # 읽기 전용 연결: 진행 중인 수집 데이터를 변경하지 않음.
        uri = DB_PATH.resolve().as_uri() + "?mode=ro"

        with sqlite3.connect(
            uri, uri=True, timeout=10
        ) as db:
            saved = db.execute(
                "SELECT COUNT(*) FROM catalog"
            ).fetchone()[0]

            progress = dict(
                db.execute(
                    "SELECT key, value FROM progress"
                )
            )

        print(f"저장된 고유 곡 수: {saved:,}곡")
        print(f"저장된 offset: {progress.get('offset', '없음')}")
        print(
            "수집 종료 표시:",
            "완료" if progress.get("complete") == "1"
            else "미완료",
        )

        if total is not None:
            if saved > total:
                print(
                    f"\n저장 건수가 API 총수보다 "
                    f"{saved - total:,}곡 많습니다."
                )
                print(
                    "API 총수와 수집 건수가 불일치하므로 "
                    "이 총수로 남은 시간이나 완료율을 "
                    "계산할 수 없습니다."
                )
            else:
                print(
                    f"\nAPI 총수 기준 차이: "
                    f"{total - saved:,}곡"
                )
                print(
                    "이 차이는 참고값이며, "
                    "실제 수집 종료를 보장하지 않습니다."
                )

except requests.RequestException:
    raise SystemExit(
        "네트워크 요청에 실패했습니다. "
        "잠시 후 다시 실행하세요."
    ) from None

except sqlite3.Error as error:
    raise SystemExit(
        f"DB 확인 실패: {error}"
    ) from None

except (ValueError, TypeError):
    raise SystemExit(
        "API 응답 형식 또는 전체 개수를 확인할 수 없습니다."
    ) from None