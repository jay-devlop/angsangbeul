# 음악 추천 다양화 분석 — 코드 전달 패키지

KKBox 청취 기록으로 **재청취 확률 모델(모델 A)** 을 만들고, 그 점수를 후처리해 **새로운 발견**을 늘리는 보정(B1·B2)과 사용자 유형별 차등 보정(B3)을 검증한 코드입니다. 입력은 `data.csv` 하나입니다.

## 1. 파일 구조

```
전달용_코드패키지/
├─ README.md
├─ data.csv                     (패키지에 없음, 1.8GB. 팀 전처리본)
├─ A/  모델 A 만들기
│   ├─ v11.py                   ★ data.csv → 특성 129개 → 모델 학습 → 평가
│   └─ v11 results/             v11.py 실행 결과의 참고용 사본 (비교 기준)
└─ B/  모델 A 위의 분석
    ├─ b1_hypotheses.py         가설 H1~H4 검증
    ├─ b2_policies.py           모델 A 구간별 검증, 보정 B1·B2, 정책 1·2·3 비교
    ├─ check_b2.py              B2 후보 범위(k 1~10, τ 0.1~0.5) 확인
    ├─ b3_types.py              사용자 유형 정의 6가지 비교
    └─ results/                 B 코드가 만든 결과
```

## 2. 파일별 의미

### A/

| 파일 | 의미 |
|---|---|
| `v11.py` | 모델 A 전체. ① `data.csv`에서 특성 129개 생성 ② 기본 모델 4종(LightGBM, LightGBM_B, CatBoost, XGBoost) 학습 ③ 조합 17개 중 Stack4 선정 ④ train+valid로 재학습 ⑤ 평가와 사전 합격선 검증 |

`v11 results/` (참고용 사본. 팀원이 `v11.py`를 돌리면 `A/v11/`이 따로 만들어지고, 이 폴더의 숫자와 비교하면 됩니다)

| 파일 | 의미 |
|---|---|
| `modelA_v11_설정과결과.json` | 선정된 조합(Stack4), 기본 모델 반복 수, 메타모델 계수, 특성 그룹과 목록, 그룹별 중요도 |
| `result_test.csv` | 평가 구간(test) 성능: AUC, logloss, ECE, 평균 예측, 실제 평균 |
| `result_valid_holdout.csv` | 검증 holdout 구간 성능 (모델 선택에 쓴 구간) |
| `result_조합후보_valid_holdout.csv` | 비교한 조합 17개의 검증 성능 |
| `result_합격선검증.csv` | 인기도·사용자 재청취율 기준선 대비 AUC 차이와 95% 신뢰구간 (사전 합격선) |
| `result_특성중요도.csv` | 특성별 gain 비중 |
| `run.log` | 실행 로그 (단계별 소요 시간 포함) |

> `result_test.csv`, `result_valid_holdout.csv`에는 이전 버전(v10) 비교 행이 같이 있습니다. `v11.py` 단독 실행에서는 v10 예측 파일이 없어 이 행이 빠지고 나머지 숫자는 같습니다.

`v11.py` 실행 시 `A/v11/`에 추가로 생기는 파일 (용량이 커서 패키지에는 없음)

| 파일 | 의미 |
|---|---|
| `featv11_{train_a,train_b,valid,test}.parquet` | 모델 입력 특성 129개 + 키 4개(`row_order`, `msno`, `song_id`, `target`). 약 1.9GB. B가 읽음 |
| `pred_{valid,test}_modelA_v11.parquet` | 모델 A의 예측 확률. B가 읽음 |
| `modelA_v11_models.joblib`, `modelA_v11_catboost.cbm` | 학습된 모델 |
| `recommend_top10_test_modelA_v11.csv` | 사용자별 상위 10곡 |

### B/

| 파일 | 입력 | 출력 | 의미 |
|---|---|---|---|
| `b1_hypotheses.py` | `data.csv` | `results/hypotheses.json` | H1~H4: 이용 기간과 장르 폭, 편중도와 활동, 추천 경로와 다양성, 새 장르 시도와 활동 유지 |
| `b2_policies.py` | `data.csv`, `A/v11/featv11_*`, `A/v11/pred_*` | `results/policies.json`, `matched_exposure.json`, `grid_settings.csv` | 모델 A 구간별 성능, B1(인기도 보정)·B2(취향 확장 보정) 강도별 결과, 정책 1(기본)·2(일괄)·3(차등) 비교, 노출 수준을 맞춘 비교 |
| `check_b2.py` | 위와 같음 | `results/check_b2_wide_grid.csv` | B2 후보 범위를 넓혀 선정값이 끝값이 아닌지 확인 |
| `b3_types.py` | 위와 같음 + `results/policies.json` | `results/type_schemes.json` | 사용자 유형 정의 6가지 비교 (현행 3유형, 점수 10분위, 기준 개선, 2유형, 군집, 활동량) |

`B/results/` 파일

| 파일 | 의미 |
|---|---|
| `hypotheses.json` | 가설 H1~H4 검증 결과 |
| `policies.json` | 구간별 모델 성능, 사용자 유형 분포와 유효성, B1·B2 결과, 정책 1~3의 손실 한도별 비교 |
| `grid_settings.csv` | 보정 설정 176개의 검증·평가 지표 |
| `matched_exposure.json` | 차등 − 일괄을 발견 대상곡 노출을 맞춰 비교한 결과 |
| `check_b2_wide_grid.csv` | B2 후보 범위 확인 결과 |
| `type_schemes.json` | 유형 정의 6가지 비교 결과 |
| `v1_algorithms.json` | 개발 초기에 비교한 알고리즘 13종의 검증 AUC (이 패키지에 만드는 코드는 없음) |

## 3. 핵심 용어

| 용어 | 뜻 |
|---|---|
| 모델 A | 사용자가 곡을 한 달 안에 다시 들을 확률을 예측하는 기본 모델 (v11, Stack4 앙상블) |
| 노출 경로(`source_*`) | 곡을 재생한 탭·화면·진입 경로. 모델 A 입력 129개에 포함됨 |
| B1 | 점수 − λ × 인기도 백분위로 순위를 다시 매겨 비인기곡 노출을 늘림 |
| B2 | 상위 10곡 중 k칸을 사용자가 처음 듣는 장르 곡(예측 확률 τ 이상)으로 채움 |
| 유효 발견@10 | 상위 10곡 중 발견 대상곡(비인기곡·새 아티스트·취향 밖 장르)이면서 실제로 재청취된 곡 수 |
| 정책 1 / 2 / 3 | 기본 / 모든 사용자에게 같은 보정 / 사용자 유형별 보정 |

## 4. 실행 방법

환경: Python 3.9 (`pip install pandas==2.2.3 lightgbm==4.6.0 xgboost==2.1.4 catboost==1.2.10 numpy scipy scikit-learn pyarrow joblib`)

**① 모델 A** — `A` 안에서 실행합니다(경로가 `data.csv`, `v11` 상대 경로). 약 80분 (이 컴퓨터 기준 76분).

```bash
cd A
ln -s ../data.csv data.csv
python3 v11.py
```

**② B 분석** — 패키지 루트에서 실행합니다. ①이 끝나 `A/v11/`에 특성·예측 파일이 있어야 합니다.

```bash
python3 B/b1_hypotheses.py     # 가설. ①과 무관하게 실행 가능
python3 B/b2_policies.py       # 약 5분. 먼저 실행해야 아래가 results/policies.json을 읽을 수 있음
python3 B/check_b2.py
python3 B/b3_types.py
```

## 5. 알아둘 점

- 분석은 시드(`SEED = 42`)가 고정돼 있어, 보정·정책 분석을 다시 실행하면 결과 숫자가 같습니다.
- 모델 A는 노출 경로(`source_*`)를 입력으로 사용했습니다.
- 평가 구간(test)은 모델 개발 중 여러 번 확인했고, 보정 설정은 검증 구간에서만 골랐습니다.
- 용량 때문에 `data.csv`와 `v11.py`가 만드는 parquet·모델 파일은 패키지에 넣지 않았습니다.
