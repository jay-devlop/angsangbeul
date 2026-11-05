# Music Data

KKBox 음악 데이터와 Jamendo 카탈로그를 비교하고, 연결된 곡의 재생·이미지 정보를 수집하는 폴더입니다. 기존 추천 모델의 KKBox `song_id`를 유지하면서 Jamendo 곡 ID와 연결합니다.

## 폴더 구조

```text
music data/
├── songs.csv
├── song_extra_info.csv
├── song_data.csv
├── jamendo_match.py
├── jamendo_compare.py
├── jamendo_fetch.py
├── jamendo_final_candidates.csv
└── jamendo_results/
    ├── jamendo_catalog.sqlite
    ├── jamendo_catalog.sqlite-wal
    ├── jamendo_catalog.sqlite-shm
    ├── kkbox_jamendo_candidates.csv
    ├── jamendo_song_audit.csv
    ├── summary.json
    ├── jamendo_audio_samples.json
    ├── audio_test.html
    └── jamendo_381_full/
        ├── jamendo_381_full.csv
        └── jamendo_381_api_raw.json
```

## KKBox 데이터

| 파일 | 설명 |
|---|---|
| `songs.csv` | KKBox 원본 곡 정보. `song_id`, 아티스트, 곡 길이, 장르 코드, 작곡가, 작사가, 언어 코드 등을 포함합니다. |
| `song_extra_info.csv` | KKBox 추가 곡 정보. `song_id`, 곡명(`name`), ISRC를 포함합니다. |
| `song_data.csv` | 두 원본을 `song_id`로 합친 통합 데이터. 2,296,320곡이며, 연결되지 않은 정보는 결측값으로 남습니다. |

`genre_ids`는 장르 이름이 아닌 KKBox 장르 코드입니다. ISRC는 음원 식별 코드입니다.

## 실행 코드

| 파일 | 역할 |
|---|---|
| `jamendo_match.py` | 처음 Jamendo 전체 카탈로그를 수집하고 KKBox 데이터와 비교할 때 사용한 코드입니다. |
| `jamendo_compare.py` | 이미 저장된 Jamendo 카탈로그와 KKBox 데이터를 비교하는 코드입니다. |
| `jamendo_fetch.py` | 381곡 목록의 Jamendo ID를 사용해 재생 주소·이미지·앨범·장르 등 API의 반환 정보를 추가 조회하는 코드입니다. |

위 역할은 작업 과정에서 사용한 용도 기준입니다. Python 파일은 이름을 바꾸거나 내용을 수정했을 수 있으므로, 실제 실행 옵션과 저장 경로는 해당 코드가 기준입니다.

## Jamendo 전체 수집 데이터

| 파일 | 설명 |
|---|---|
| `jamendo_results/jamendo_catalog.sqlite` | Jamendo API로 처음 수집한 전체 카탈로그 데이터베이스. 수집 완료 기록 기준 895,845곡입니다. KKBox와 비교할 때 사용한 원본입니다. |
| `jamendo_results/jamendo_catalog.sqlite-wal` | 아직 본 데이터베이스 파일에 반영되지 않은 변경 내용이 들어갈 수 있는 SQLite 보조 파일입니다. |
| `jamendo_results/jamendo_catalog.sqlite-shm` | SQLite가 WAL 접근을 관리할 때 사용하는 공유 메모리 보조 파일입니다. |

### 데이터베이스 내용

- `catalog`: Jamendo 곡 ID(`track_id`), 제목 비교 키(`title_key`), 수집 정보(`payload`).
- `progress`: 수집 진행 상태.

처음 수집한 `payload`에는 다음 정보가 저장되어 있습니다.

| 필드 | 의미 |
|---|---|
| `id` | Jamendo 곡 ID |
| `name` | 곡명 |
| `artist_name` | 아티스트 |
| `duration` | API가 제공한 곡 길이(초) |
| `audio` | 수집 당시의 재생 URL |
| `audiodownload_allowed` | 다운로드 허용 여부 |
| `license_ccurl` | 라이선스 URL. 값이 비어 있을 수 있습니다. |
| `shareurl` | Jamendo 곡 페이지 URL |

전체 API 컬럼을 저장한 파일은 아닙니다. 이미지·앨범·장르·가사·통계 등은 후속 API 조회로 보완합니다.

**`-wal`, `-shm` 파일을 임의로 삭제하지 마세요.** 실행 중인 데이터베이스의 `.sqlite` 파일만 따로 복사하면 최신 기록이 빠질 수 있으므로, 백업 시에는 SQLite 백업 기능을 사용하거나 정상 종료·반영 여부를 확인해야 합니다.

## 비교 결과와 곡 목록

| 파일 | 설명 |
|---|---|
| `jamendo_results/kkbox_jamendo_candidates.csv` | KKBox와 Jamendo 저장 데이터를 비교한 원본 결과. 곡명·아티스트·길이 비교 결과와 Jamendo 연결 정보를 포함합니다. 하나의 KKBox 곡에 여러 비교 행이 있을 수 있습니다. |
| `jamendo_results/jamendo_song_audit.csv` | 최초 381곡 목록. `song_id`, 곡명, 아티스트, `candidate_ids`, 검토 정보 등을 포함하며 추가 API 조회의 입력 파일입니다. |
| `jamendo_final_candidates.csv` | 381곡과 길이 차이 그룹 134곡을 재검토해 선별한 358행의 결과입니다. 고유 Jamendo 곡 ID는 351개입니다. |
| `jamendo_results/summary.json` | 수집·비교 작업의 요약 파일. 구체적인 항목은 실제 파일 내용을 확인해야 합니다. |

### 최초 비교 결과

KKBox 2,296,320곡과 Jamendo 저장 데이터를 비교한 결과입니다.

| 분류 | KKBox 곡 수 |
|---|---:|
| 제목 일치 없음 (`no_title_match`) | 1,676,952 |
| 아티스트 불일치 (`artist_mismatch`) | 617,955 |
| 길이 차이 (`duration_mismatch`) | 134 |
| 정보 부족 (`insufficient_metadata`) | 898 |
| 곡명·아티스트·길이 기준 통과 (`needs_review`) | 381 |
| 합계 | 2,296,320 |

최초 381곡은 KKBox `song_id` 기준입니다. 연결된 Jamendo ID는 중복을 제외하면 385개이며, KKBox–Jamendo 연결은 393쌍입니다. 한 곡에 Jamendo ID가 여러 개 연결될 수 있습니다.

후속 재검토에서는 기존 381곡 중 355곡과 길이 차이 그룹의 3곡을 합쳐 358행을 선별했습니다. **381곡 목록과 358행 목록은 서로 다른 단계의 파일입니다.** 선별 결과가 원본 음원 간 동일 녹음이나 현재 재생 가능 여부까지 확정하는 것은 아닙니다.

### 추가 조회에 사용하는 컬럼

- `candidate_ids`: Jamendo API에 요청할 곡 ID. 여러 ID가 있으면 각각 조회합니다.
- `song_id`: 기존 추천 모델의 KKBox 곡 ID. API 응답을 추천 결과에 연결할 때 유지합니다.
- 그 외 검토 컬럼은 API 조회에 필수는 아니며 참고 정보입니다. `train_event_rows`, `present_in_train`은 과거 참고용 집계로, 현재 모델의 사용 데이터 범위를 뜻하지 않습니다.

## 381곡 추가 API 조회 결과

| 파일 | 설명 |
|---|---|
| `jamendo_results/jamendo_381_full/jamendo_381_full.csv` | 381곡에 연결된 Jamendo ID의 추가 API 조회 결과. API가 반환한 모든 필드를 저장합니다. 연결이 여러 개인 곡은 행을 나누므로 381행보다 많을 수 있습니다. |
| `jamendo_results/jamendo_381_full/jamendo_381_api_raw.json` | API 원본 응답과 진행 기록. 재실행 시 성공한 ID를 건너뛰고, 요청별 응답과 오류를 확인하는 데 사용합니다. |

기본 저장 위치는 입력 CSV 옆의 `jamendo_381_full` 폴더입니다. `--output-dir`을 지정하면 달라집니다. 이어서 실행하려면 같은 입력과 출력 폴더를 사용해야 합니다.

### 앱에서 사용하는 주요 API 필드

| 필드 | 의미 |
|---|---|
| `id` | Jamendo 곡 ID |
| `name` | 곡명 |
| `artist_name` | 아티스트 |
| `album_name` | 앨범명 |
| `duration` | 곡 길이(초) |
| `audio` | 재생 URL |
| `image` | 곡 커버 이미지 URL |
| `album_image` | 앨범 이미지 URL. 싱글은 비어 있을 수 있습니다. |
| `license_ccurl` | 라이선스 URL |
| `audiodownload_allowed` | 다운로드 허용 여부 |
| `lyrics` | 가사 |
| `musicinfo.tags.genres` | 장르 이름 목록 |
| `licenses.*` | 라이선스 관련 추가 정보 |
| `stats.*` | 청취·다운로드·즐겨찾기 등 통계 |

API 필드명은 유지합니다. 중첩 객체는 CSV에서 점(`.`)으로 펼치고, 배열은 JSON 문자열로 보존합니다. 원본 JSON은 중첩 구조를 유지합니다. API의 곡별 응답에 따라 필드와 값이 없을 수 있습니다.

`mapping.song_id`, `mapping.jamendo_id` 등은 연결용 정보이며, `fetch.*`는 조회 상태를 나타내는 코드에서 추가한 컬럼입니다. API 자체의 필드는 아닙니다.

### 조회 상태

| 상태 | 의미 |
|---|---|
| `success` | 추가 필드를 요청한 조회에서 해당 ID의 곡 정보를 받았습니다. 모든 필드에 값이 있다는 뜻은 아닙니다. |
| `partial` | 기본 곡 정보는 받았지만 추가 필드를 포함한 조회는 성공하지 못했습니다. 받아온 정보는 저장합니다. |
| `empty_response` | 수정 코드의 모든 조회 조건에서 정상 응답을 받았지만 결과가 빈 목록이었습니다. |
| `unresolved` | 오류 또는 요청한 ID와 다른 응답 등으로 조회를 해결하지 못했습니다. |
| `access_error` | 인증·접근·요청 제한 등으로 조회를 중단한 상태입니다. 자세한 이유는 원본 응답을 확인합니다. |
| `pending` | 아직 처리하지 않았습니다. |
| `not_found` | 이전 코드에서 사용한 상태. 해당 ID의 정보가 반환되지 않았다는 뜻입니다. 수정 코드에서는 재조회 대상입니다. |

`empty_response`와 `not_found`는 **재생 실패를 확인했다는 뜻이 아닙니다.** 처음 전체 수집한 SQLite에 해당 ID의 기존 정보와 재생 URL이 남아 있을 수 있습니다. 현재 추가 조회 코드는 SQLite를 자동으로 읽거나 병합하지 않으므로, 새 조회가 실패했다고 기존 정보가 사라진 것은 아닙니다.

재생 URL과 이미지 URL을 저장하는 작업이며 음원·이미지 파일 자체를 내려받는 작업은 아닙니다. URL이 있다는 사실과 실제 플레이어에서 재생되는지는 별도로 확인해야 합니다.

## 초기 재생 테스트 파일

| 파일 | 설명 |
|---|---|
| `jamendo_results/jamendo_audio_samples.json` | 초기 재생 테스트에 사용한 샘플 곡과 오디오 정보입니다. |
| `jamendo_results/audio_test.html` | 브라우저에서 샘플 음원의 재생 버튼을 눌러 확인하는 테스트 페이지입니다. |

이 두 파일은 초기 샘플 테스트용이며, 381곡 전체의 조회 결과나 재생 검증 결과는 아닙니다.

## 작업 흐름

1. `songs.csv`와 `song_extra_info.csv`를 합쳐 `song_data.csv`를 만듭니다.
2. Jamendo API에서 전체 카탈로그를 수집해 `jamendo_catalog.sqlite`에 저장합니다.
3. KKBox 통합 데이터와 Jamendo 저장 데이터를 비교해 `kkbox_jamendo_candidates.csv`를 만듭니다.
4. 최초 381곡과 연결 ID를 `jamendo_song_audit.csv`에 정리합니다.
5. 해당 ID로 Jamendo API의 기본·추가 정보를 조회해 `jamendo_381_full` 폴더에 CSV와 원본 JSON을 저장합니다.
6. 앱에서는 모델의 KKBox `song_id`를 Jamendo ID와 연결하고, 확보한 `audio`와 `image`를 사용합니다.

현재 381곡 추가 조회는 후속 선별 파일인 `jamendo_final_candidates.csv`를 입력으로 사용하지 않습니다. 기존 추천 모델도 변경하지 않습니다.


## YouTube API 검토 — 실제 서비스 계획에 미적용

Jamendo 사용 전, YouTube Data API v3로 KKBox 곡명과 아티스트를 검색해 연결 가능한 영상을 찾는 작업을 진행했습니다. 검색 결과에서 여러 영상 후보를 저장하고 곡별 연결 가능성을 검토했습니다.

**YouTube에서 확인한 것은 독립적인 음원 재생 URL이 아니라 YouTube 영상입니다. 재생도 YouTube 영상 플레이어를 사용하는 방식이므로, 음원 중심으로 재생하는 이번 음악 앱의 실제 계획에는 적용하지 않았습니다.** 아래 파일은 검토·실험 기록으로 보관하며, 현재 Jamendo 기반 재생 데이터 흐름에는 사용하지 않습니다.

### 폴더 구조

```text
youtube/
├── youtube_match.py
└── youtube_results/
    ├── youtube_candidates_KR.csv
    ├── youtube_matches.sqlite
    ├── youtube_matches.sqlite-shm
    └── youtube_matches.sqlite-wal
```

### 파일 설명

| 파일 | 설명 |
|---|---|
| `youtube_match.py` | KKBox 곡명·아티스트로 YouTube API를 검색하고 영상 후보를 수집·비교하는 코드입니다. |
| `youtube_results/youtube_candidates_KR.csv` | YouTube 검색으로 찾은 영상 후보와 비교 결과를 저장한 CSV입니다. `KR`은 파일명에 붙은 구분이며, 실제 지역 설정과 컬럼은 코드·파일 내용이 기준입니다. |
| `youtube_results/youtube_matches.sqlite` | YouTube 검색·비교 결과를 저장하는 SQLite 데이터베이스입니다. 세부 테이블과 진행 기록의 저장 방식은 해당 코드가 기준입니다. |
| `youtube_results/youtube_matches.sqlite-shm` | SQLite의 WAL 접근을 관리하는 공유 메모리 보조 파일입니다. |
| `youtube_results/youtube_matches.sqlite-wal` | 본 데이터베이스에 아직 반영되지 않은 변경 내용이 들어갈 수 있는 보조 파일입니다. |

위 파일 설명은 당시 작업 용도와 화면의 파일 목록을 기준으로 정리했습니다. 파일별 실제 컬럼과 데이터베이스 구조를 직접 점검한 명세는 아닙니다. SQLite 보조 파일은 임의로 삭제하지 마세요.

### 검토 결과의 의미

- 영상 후보가 검색됐다는 것은 해당 검색어와 관련된 영상을 찾았다는 뜻입니다. 동일 곡·동일 녹음이 확인됐다는 뜻은 아닙니다.
- YouTube 영상 주소·영상 ID는 Jamendo의 `audio` 같은 직접 음원 재생 주소가 아닙니다.
- 이번 앱에서는 YouTube 검색 결과를 재생용 음원 데이터로 사용하지 않고, Jamendo 기반 데이터 수집과 연결 작업을 진행합니다.
