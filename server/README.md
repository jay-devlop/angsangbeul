# 추천 서버

저장된 v11 모델(`../ML 개발/v11/`)을 실제로 실행해 데모 사용자별 기존·보정 추천 순서(KKBox song_id)를 돌려줍니다.

> 웹 앱에서는 이 서버의 추천을 **가입 직후 처음 취향의 참고용**으로만 씁니다. 실제 추천은 사용자 본인의 기록으로 앱에서 계산하며, 곡을 들을수록 서버 추천의 영향이 줄어듭니다. 서버가 없어도 앱은 동작합니다.

```bash
pip install -r requirements.txt
python3 ../web/tools/prepare_pairs.py            # 쌍 만들기 (data.csv 필요)
python3 ../web/tools/build_serving_features.py   # 특성 129개 (약 4분)
python3 app.py                                   # 포트 8010 (PORT 환경변수로 변경)
python3 validate_scoring.py                      # 점수 재현 검증
```

API: `GET /api/users`, `GET /api/recommend?genres=팝,힙합,재즈` → `{genres, base[], adjusted[]}`.
