# 추천 서버

저장해 둔 v11 모델을 실제로 돌려서, 장르별 데모 사용자에게 보여 줄 기존 추천과 보정 추천의 순서(KKBox `song_id`)를 돌려주는 서버입니다. 외부 프레임워크 없이 Python 표준 `http.server`로 만들었습니다.

> 웹 앱은 이 서버의 추천을 가입 직후 처음 취향의 참고용으로만 씁니다. 실제 추천은 앱이 사용자 본인의 기록으로 계산하고, 곡을 들을수록 서버 추천의 영향이 줄어 12곡이면 0이 됩니다. 서버가 없어도 앱은 동작하며, 배포 환경에서는 서버에 연결하지 않습니다(`localhost`에서만 연결).

## 폴더 구성

| 파일 | 내용 |
|---|---|
| `app.py` | 서버 본체. 모델을 불러와 점수를 계산하고 API로 내보냄 |
| `validate_scoring.py` | 서버가 계산한 점수가 v11 학습 때 저장한 예측과 같은지 비교 |
| `requirements.txt` | 필요한 패키지 |
| `data/features.json` | 모델 입력 특성 129개 목록 |
| `data/pop_ref.npy` | 인기도 백분위 기준값 |
| `data/demo_profiles.json` | 장르별 데모 사용자 11명 |
| `data/demo_users.json`, `demo_selection_report.json` | 데모 사용자를 고른 기록. 실제 ID와 가명이 연결돼 있어 서버 안에서만 씀 |

쌍 특성 파일 `data/pairs_features.parquet`은 저장소에 없고, 아래 순서로 직접 만듭니다.

## 준비물

| 항목 | 설명 |
|---|---|
| 모델 폴더 `ML 개발/v11/` | `v11.py`가 만든 모델 파일(`modelA_v11_models.joblib`, `modelA_v11_catboost.cbm`). 용량 때문에 저장소에 없으므로 직접 준비합니다. 다른 위치에 두면 `MODEL_DIR` 환경변수로 알려 줍니다. |
| `data.csv` | 청취 기록 원본(저장소에 없음). 쌍을 만들고 특성을 계산할 때 씁니다. |

모델을 만드는 방법은 [../v11/README.md](../v11/README.md)에 있습니다. 저장소 맨 위의 `v11/`은 코드와 결과이고, 여기서 말하는 `ML 개발/v11/`은 `v11.py`를 돌린 출력 폴더입니다.

## 실행

```bash
pip install -r requirements.txt
python3 ../web/tools/prepare_pairs.py            # 데모 사용자 선정, 사용자×웹곡 쌍 만들기 (data.csv 필요)
python3 ../web/tools/build_serving_features.py   # 쌍의 특성 129개 계산 (약 4분)
python3 app.py                                   # 포트 8010 (PORT 환경변수로 변경)
python3 validate_scoring.py                      # 점수 재현 검증
```

`validate_scoring.py`는 `ML 개발/v12/featv12_test.parquet`에서 20,000행을 뽑아 서버 점수를 계산하고, `ML 개발/v11/pred_test_modelA_v11.parquet`의 예측과 비교합니다. 두 파일이 있어야 돌아갑니다.

## API

| 요청 | 응답 |
|---|---|
| `GET /api/users` | 데모 사용자 목록 |
| `GET /api/recommend?genres=팝,힙합,재즈` | `{genres, base[], adjusted[]}`: 기존 추천(`base`)과 일괄 보정 추천(`adjusted`)의 KKBox song_id 순서 |

- 응답에는 곡 순서만 담습니다. 점수, 보정값, 모델 이름은 내보내지 않습니다.
- 보정은 보고서의 정책 2(일괄 보정, 손실 한도 1%p)입니다. `p - 0.20 × 인기도 백분위`로 순서를 다시 매기고 상위 10곡을 돌려줍니다.
