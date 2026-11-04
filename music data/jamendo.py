import requests

client_id = input("Jamendo Client ID를 입력하세요: ").strip()

response = requests.get(
    "https://api.jamendo.com/v3.0/tracks/",
    params={
        "client_id": client_id,
        "format": "json",
        "limit": 1,
        "fullcount": "true",
        "type": "single albumtrack",
    },
    timeout=60,
) 
response.raise_for_status()

data = response.json()
headers = data.get("headers", {})

if headers.get("status") != "success":
    print("조회 실패:", headers.get("error_message"))
else:
    total = headers.get("results_fullcount")

    if total is None:
        print("응답에 전체 개수가 없습니다.")
        print(headers)
    else:
        total = int(total)
        print(f"전체 곡 수: {total:,}곡")
        print(f"200곡씩 수집할 때 페이지 수: {(total + 199) // 200:,}개")
