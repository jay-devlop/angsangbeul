# 추천 서버

저장된 v11 모델(`../ML 개발/v11/`)을 실제로 실행해 데모 사용자별 기존·보정 추천 순서(KKBox song_id)를 돌려줍니다.

```bash
pip install -r requirements.txt
python3 ../web/tools/prepare_pairs.py            # 쌍 만들기 (data.csv 필요)
python3 ../web/tools/build_serving_features.py   # 특성 129개 (약 4분)
python3 app.py                                   # 포트 8010 (PORT 환경변수로 변경)
python3 validate_scoring.py                      # 점수 재현 검증
```

API: `GET /api/users`, `GET /api/recommend?genres=팝,힙합,재즈` → `{genres, base[], adjusted[]}`.
