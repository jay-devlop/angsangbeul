import getpass
import json
import requests


def show_fields(value, path=""):
    """중첩된 필드까지 이름, 자료형, 예시를 출력합니다."""
    if isinstance(value, dict):
        if not value:
            print(f"{path} | dict | {{}}")

        for key, item in value.items():
            next_path = f"{path}.{key}" if path else key
            show_fields(item, next_path)

    elif isinstance(value, list):
        preview = json.dumps(value, ensure_ascii=False)
        print(f"{path} | list | {preview[:200]}")

        for index, item in enumerate(value):
            if isinstance(item, dict):
                show_fields(item, f"{path}[{index}]")

    else:
        preview = str(value).replace("\n", " ")
        print(f"{path} | {type(value).__name__} | {preview[:200]}")


def main():
    client_id = getpass.getpass(
        "Jamendo Client ID 입력 (화면에 표시되지 않음): "
    ).strip()

    if not client_id:
        print("Client ID를 입력해주세요.")
        return

    try:
        response = requests.get(
            "https://api.jamendo.com/v3.0/tracks/",
            params={
                "client_id": client_id,
                "format": "json",
                "type": "single albumtrack",
                "limit": 1,
                "include": "licenses musicinfo stats lyrics",
                "audioformat": "mp32",
                "imagesize": 600,
            },
            timeout=60,
        )
        response.raise_for_status()

    except requests.HTTPError:
        print(f"HTTP 오류: {response.status_code}")
        return

    except requests.RequestException as error:
        # 오류 전문에는 Client ID가 포함된 URL이 나올 수 있어 생략
        print(f"요청 실패: {type(error).__name__}")
        return

    try:
        data = response.json()
    except ValueError:
        print("응답을 JSON으로 읽지 못했습니다.")
        return

    headers = data.get("headers", {})

    if headers.get("status") != "success":
        print("API 조회 실패")
        print("오류 코드:", headers.get("code"))
        print("오류 내용:", headers.get("error_message"))
        return

    if headers.get("warnings"):
        print("API 알림:", headers["warnings"])

    tracks = data.get("results", [])

    if not tracks:
        print("조회 결과가 없습니다.")
        print("응답 헤더:", json.dumps(headers, ensure_ascii=False))
        return

    track = tracks[0]

    print("\n[조회한 샘플 곡]")
    print("곡 ID:", track.get("id"))
    print("곡명:", track.get("name"))
    print("아티스트:", track.get("artist_name"))

    print(f"\n[최상위 필드: {len(track)}개]")
    for index, field in enumerate(track, start=1):
        print(f"{index}. {field}")

    print("\n[전체 필드 경로 | 자료형 | 예시]")
    show_fields(track)

    print("\n[재생·이미지 주소]")
    print("재생 주소 — audio:", track.get("audio") or "(없음)")
    print("곡 이미지 — image:", track.get("image") or "(없음)")
    print("앨범 이미지 — album_image:", track.get("album_image") or "(없음)")

    print("\n[곡 정보 원본 JSON]")
    print(json.dumps(track, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()