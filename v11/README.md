# v11: 모델 A와 다양성 보정 분석 (최종본)

KKBox 청취 기록으로 재청취 확률 모델(모델 A)을 만들고, 그 점수를 다시 정렬해 새로운 곡의 노출을 늘리는 보정(B1·B2)과 사용자 유형별 보정(B3)을 검증한 코드와 결과입니다. 입력은 `data.csv` 하나입니다. 분석 내용과 해석은 [최종보고서.md](최종보고서.md)에 있습니다.

## 폴더 구조

```
v11/
├─ README.md
├─ 최종보고서.md
├─ ML Model/                 모델 A 만들기
│   ├─ v11.py                data.csv → 특성 129개 → 모델 학습 → 평가
│   └─ v11 results/          v11.py를 돌려 얻은 결과 (비교용)
└─ Tuning/                   모델 A 위에서 하는 보정 분석
    ├─ b1_hypotheses.py      가설 H1~H4 검증
    ├─ b2_policies.py        구간별 성능, 보정 B1·B2, 정책 1·2·3 비교
    ├─ check_b2.py           B2 후보 범위(k 1~10, τ 0.1~0.5) 확인
    ├─ b3_types.py           사용자 유형 정의 6가지 비교
    └─ results/              위 코드가 만든 결과
```

`data.csv`(약 1.8GB, 팀 전처리본)는 저장소에 없습니다. CSV, parquet, 모델 파일도 `.gitignore`에 걸려 있어서, 아래 표에 적힌 파일 중 일부는 직접 실행해야 생깁니다.

## ML Model/

### v11.py

한 파일에서 모델 A를 끝까지 만듭니다.

1. `data.csv`에서 기본 특성 71개를 만들고, 노출 경로·라이브러리·경로 프로필 특성 58개를 더해 129개로 만듭니다.
2. 기본 모델 4개(LightGBM, LightGBM_B, CatBoost, XGBoost)를 학습합니다.
3. 단독, 평균, 가중평균, 스태킹 조합 17개를 비교해 Stack4를 고릅니다.
4. train과 valid를 합쳐 다시 학습한 뒤 test로 평가하고, 사전에 정한 합격선을 검증합니다.

### v11 results/

`v11.py` 결과를 저장해 둔 것입니다. 직접 돌린 결과와 숫자를 맞춰 볼 때 씁니다.

| 파일 | 내용 |
|---|---|
| `modelA_v11_설정과결과.json` | 선정된 조합(Stack4), 모델별 반복 수, 메타모델 계수, 특성 그룹과 목록, 그룹별 중요도 |
| `result_test.csv` | test 성능: AUC, logloss, ECE, 평균 예측, 실제 평균 |
| `result_valid_holdout.csv` | 모델 선택에 쓴 검증 holdout 성능 |
| `result_조합후보_valid_holdout.csv` | 비교한 조합 17개의 검증 성능 |
| `result_합격선검증.csv` | 인기도·사용자 재청취율 기준선과의 AUC 차이와 95% 신뢰구간 |
| `result_특성중요도.csv` | 특성별 gain 비중 |
| `run.log` | 실행 로그와 단계별 소요 시간 |

`result_test.csv`와 `result_valid_holdout.csv`에는 이전 버전(v10) 비교 행이 들어 있습니다. `v11.py`만 돌리면 v10 예측 파일이 없어 이 행만 빠지고 나머지 숫자는 같습니다.

### v11.py가 만드는 파일

`OUT = "v11"` 폴더에 저장됩니다. 용량이 커서 저장소에는 없습니다.

| 파일 | 내용 |
|---|---|
| `featv11_{train_a,train_b,valid,test}.parquet` | 모델 입력 특성 129개와 키 4개(`row_order`, `msno`, `song_id`, `target`). 약 1.9GB. Tuning이 읽음 |
| `pred_{valid,test}_modelA_v11.parquet` | 모델 A의 예측 확률. Tuning이 읽음 |
| `modelA_v11_models.joblib`, `modelA_v11_catboost.cbm` | 학습된 모델. 추천 서버(`server/`)가 읽음 |
| `recommend_top10_test_modelA_v11.csv` | 사용자별 상위 10곡 |

## Tuning/

| 파일 | 입력 | 출력 | 내용 |
|---|---|---|---|
| `b1_hypotheses.py` | `data.csv` | `hypotheses.json` | H1~H4: 이용 기간과 장르 폭, 편중도와 활동, 추천 경로와 다양성, 새 장르 시도와 활동 유지 |
| `b2_policies.py` | `data.csv`, 특성·예측 parquet | `policies.json`, `matched_exposure.json`, `grid_settings.csv` | 구간별 성능, B1(인기도 보정)·B2(취향 확장 보정) 강도별 결과, 정책 1(기본)·2(일괄)·3(차등) 비교, 노출을 맞춘 비교 |
| `check_b2.py` | 위와 같음 | `check_b2_wide_grid.csv` | B2 후보 범위를 넓혀 고른 값이 범위 끝이 아닌지 확인 |
| `b3_types.py` | 위와 같음 + `policies.json` | `type_schemes.json` | 사용자 유형 정의 6가지 비교(현행 3유형, 점수 10분위, 기준 개선, 2유형, 군집, 활동량) |

`results/`에는 위 출력과 함께 `v1_algorithms.json`(개발 초기에 비교한 알고리즘 13종의 검증 AUC)이 있습니다. 이 파일을 만드는 코드는 이 폴더에 없습니다.

## 용어

| 용어 | 뜻 |
|---|---|
| 모델 A | 사용자가 곡을 한 달 안에 다시 들을 확률을 예측하는 기본 모델 (Stack4 앙상블) |
| 노출 경로(`source_*`) | 곡을 재생한 탭, 화면, 진입 경로. 모델 입력 129개에 들어 있음 |
| B1 | 점수 − λ × 인기도 백분위로 순위를 다시 매겨 비인기곡 노출을 늘림 |
| B2 | 상위 10곡 중 k칸을 사용자가 처음 듣는 장르의 곡(예측 확률 τ 이상)으로 채움 |
| 유효 발견@10 | 상위 10곡 중 발견 대상곡(비인기곡, 새 아티스트, 취향 밖 장르)이면서 실제로 다시 들은 곡 수 |
| 정책 1 / 2 / 3 | 기본 / 모든 사용자에게 같은 보정 / 사용자 유형별 보정 |

## 실행

환경: Python 3.9
(`pip install pandas==2.2.3 lightgbm==4.6.0 xgboost==2.1.4 catboost==1.2.10 numpy scipy scikit-learn pyarrow joblib`)

코드의 경로는 `data.csv`, `A/v11/`, `B/results/`처럼 전달 당시 폴더 이름을 기준으로 적혀 있습니다. 작업 폴더를 아래처럼 만들어 두면 코드를 고치지 않고 실행됩니다.

```
작업폴더/
├─ data.csv
├─ A/v11.py            ← ML Model/v11.py를 복사
└─ B/                  ← Tuning/을 통째로 복사 (결과는 B/results에 저장)
```

**1. 모델 A**: `A` 안에서 실행합니다. 약 80분 걸립니다(이 컴퓨터 기준 76분).

```bash
cd A
ln -s ../data.csv data.csv
python3 v11.py
```

**2. 보정 분석**: 작업 폴더 맨 위에서 실행합니다. 1이 끝나서 `A/v11/`에 특성과 예측 파일이 있어야 합니다.

```bash
python3 B/b1_hypotheses.py     # 가설 검증. 1과 별개로 실행 가능
python3 B/b2_policies.py       # 약 5분. 아래 둘이 policies.json을 읽으므로 먼저 실행
python3 B/check_b2.py
python3 B/b3_types.py
```

## 알아둘 점

- 시드(`SEED = 42`)를 고정해서 보정·정책 분석을 다시 돌려도 숫자가 같습니다.
- 모델 A는 노출 경로(`source_*`)를 입력으로 씁니다. 이 때문에 "해당 경로로 재생된 곡이 다시 들릴지"를 맞히는 모델이고, 같은 조건에서 source를 뺀 모델보다 AUC가 높습니다. 자세한 수치는 최종보고서 앞부분에 있습니다.
- test 구간은 모델을 개발하는 동안 여러 번 확인했습니다. 보정 설정은 검증 구간에서만 골랐습니다.
- 추천 서버는 `v11.py`가 만든 모델 파일을 `ML 개발/v11/`에서 읽습니다. 다른 곳에 두었다면 `MODEL_DIR` 환경변수로 알려 주세요.
- `최종보고서.md` 안에서 분석 코드를 "A/, B/ 폴더"라고 부르는 곳은 이 폴더의 `ML Model/`, `Tuning/`에 해당합니다.
