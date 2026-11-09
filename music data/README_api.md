# music data

KKBox 곡과 Jamendo 카탈로그를 비교해 같은 곡을 찾고, 찾은 곡의 재생 주소와 이미지 같은 정보를 모으는 폴더입니다. 추천 모델이 쓰는 KKBox `song_id`는 그대로 두고, Jamendo 곡 ID를 옆에 연결합니다.

## 폴더 구조

작업할 때의 전체 구조입니다. CSV, SQLite 같은 큰 데이터 파일은 GitHub에 올리지 않았습니다. 아래에서 `[저장소]`로 표시한 파일만 내려받은 폴더에 있고, 나머지는 코드를 돌리거나 따로 받아야 생깁니다.

```text
music data/
├── README_api.md                       [저장소]
├── songs.csv, song_extra_info.csv, song_data.csv     (KKBox 원본·통합 데이터)
├── jamendo_final_candidates.csv        (재검토로 고른 358행)
├── jamendo/
│   ├── jamendo_match.py                [저장소]
│   ├── jamendo_compare.py              [저장소]
│   ├── jamendo_fetch.py                [저장소]
│   ├── jamendo_count.py                [저장소]
│   ├── jamendo_info.py                 [저장소]
│   ├── jamendo_full/
│   │   └── jamendo_api_raw.json        [저장소] 381곡 추가 조회의 API 원본 응답 (Jamendo ID 385개)
│   └── jamendo_results/
│       ├── jamendo_catalog.sqlite (+ -wal, -shm)
│       ├── kkbox_jamendo_candidates.csv
│       ├── jamendo_song_audit.csv
│       ├── summary.json                [저장소]
│       ├── jamendo_audio_samples.json  [저장소]
│       ├── audio_test.html             [저장소]
│       └── jamendo_381_full/
│           ├── jamendo_381_full.csv
│           └── jamendo_381_api_raw.json
└── youtube/
    ├── youtube_match.py                [저장소]
    └── youtube_results/                (검토 기록. 아래 YouTube 항목 참고)
```

앱이 쓰는 곡 목록은 이 폴더가 아니라 `web/data/catalog.json`입니다. 이 파일은 `web/tools/build_catalog.py`가 `jamendo_381_full.csv`에서 만듭니다.

## KKBox 데이터

| 파일 | 내용 |
|---|---|
| `songs.csv` | KKBox 원본 곡 정보. `song_id`, 아티스트, 곡 길이, 장르 코드, 작곡가, 작사가, 언어 코드 등 |
| `song_extra_info.csv` | 곡명(`name`)과 ISRC(음원 식별 코드) |
| `song_data.csv` | 위 두 파일을 `song_id`로 합친 것. 2,296,320곡이고, 짝이 없는 값은 비어 있음 |

`genre_ids`는 장르 이름이 아니라 KKBox의 장르 코드입니다.

## 코드

| 파일 | 하는 일 |
|---|---|
| `jamendo/jamendo_match.py` | Jamendo 전체 카탈로그를 처음 수집하고 KKBox와 비교할 때 쓴 코드 |
| `jamendo/jamendo_compare.py` | 이미 저장한 Jamendo 카탈로그와 KKBox 데이터를 다시 비교 |
| `jamendo/jamendo_fetch.py` | 381곡의 Jamendo ID로 재생 주소, 이미지, 앨범, 장르 같은 정보를 API에서 추가로 조회 |
| `jamendo/jamendo_count.py` | API로 조회할 수 있는 전체 곡 수 확인. 실행할 때 Client ID를 입력 |
| `jamendo/jamendo_info.py` | API 응답의 필드 이름, 자료형, 예시 값을 중첩 구조까지 출력. 실행할 때 Client ID를 입력 |
| `youtube/youtube_match.py` | YouTube 검색으로 영상 후보를 찾는 검토용 코드 (아래 YouTube 항목) |

Client ID 같은 인증 값은 코드에 적지 않고 실행할 때 입력합니다. 위 설명은 작업하면서 쓴 용도이고, 파일을 고쳤을 수 있으니 실제 옵션과 저장 경로는 코드를 확인하세요.

## Jamendo 전체 수집 데이터

| 파일 | 내용 |
|---|---|
| `jamendo/jamendo_results/jamendo_catalog.sqlite` | Jamendo API로 처음 모은 전체 카탈로그. 수집 완료 기록으로 895,845곡. KKBox와 비교할 때 쓴 원본 |
| `…sqlite-wal` | 아직 본 파일에 반영되지 않은 변경이 들어 있을 수 있는 SQLite 보조 파일 |
| `…sqlite-shm` | WAL 접근을 관리하는 SQLite 공유 메모리 파일 |

테이블은 두 개입니다.
- `catalog`: Jamendo 곡 ID(`track_id`), 제목 비교용 키(`title_key`), 수집 정보(`payload`)
- `progress`: 수집 진행 상태

`payload`에 들어 있는 정보는 아래와 같습니다.

| 필드 | 뜻 |
|---|---|
| `id` | Jamendo 곡 ID |
| `name` | 곡명 |
| `artist_name` | 아티스트 |
| `duration` | 곡 길이(초) |
| `audio` | 수집할 때의 재생 URL |
| `audiodownload_allowed` | 다운로드 허용 여부 |
| `license_ccurl` | 라이선스 URL. 비어 있을 수 있음 |
| `shareurl` | Jamendo 곡 페이지 URL |

API의 전체 컬럼을 저장한 것은 아닙니다. 이미지, 앨범, 장르, 가사, 통계는 뒤에 따로 조회해서 채웠습니다.

`-wal`, `-shm` 파일은 지우지 마세요. 실행 중인 데이터베이스는 `.sqlite` 파일만 복사하면 최신 기록이 빠질 수 있습니다. 백업할 때는 SQLite의 백업 기능을 쓰거나, 정상 종료해서 변경이 반영됐는지 확인한 뒤 복사하세요.

## 비교 결과와 곡 목록

| 파일 | 내용 |
|---|---|
| `jamendo/jamendo_results/kkbox_jamendo_candidates.csv` | KKBox와 Jamendo를 비교한 원본 결과. 곡명·아티스트·길이 비교 결과와 Jamendo 연결 정보. KKBox 곡 하나에 행이 여러 개일 수 있음 |
| `jamendo/jamendo_results/jamendo_song_audit.csv` | 처음 고른 381곡 목록. `song_id`, 곡명, 아티스트, `candidate_ids`, 검토 정보. 추가 API 조회의 입력 파일 |
| `jamendo_final_candidates.csv` | 381곡과 길이 차이 그룹 134곡을 다시 검토해 고른 358행. 고유 Jamendo 곡 ID는 351개 |
| `jamendo/jamendo_results/summary.json` | 수집·비교 작업 요약 |

### 처음 비교한 결과

KKBox 2,296,320곡을 Jamendo 저장 데이터와 비교한 결과입니다.

| 분류 | KKBox 곡 수 |
|---|---:|
| 제목이 같은 곡 없음 (`no_title_match`) | 1,676,952 |
| 아티스트가 다름 (`artist_mismatch`) | 617,955 |
| 길이 차이 (`duration_mismatch`) | 134 |
| 정보 부족 (`insufficient_metadata`) | 898 |
| 곡명·아티스트·길이 모두 통과 (`needs_review`) | 381 |
| 합계 | 2,296,320 |

처음 고른 381곡은 KKBox `song_id` 기준입니다. 여기에 연결된 Jamendo ID는 중복을 빼면 385개이고, KKBox–Jamendo 연결은 393쌍입니다. 한 곡에 Jamendo ID가 여러 개 붙을 수 있습니다.

다시 검토할 때는 381곡 중 355곡과 길이 차이 그룹의 3곡을 합쳐 358행을 골랐습니다. 381곡 목록과 358행 목록은 단계가 다른 별개의 파일입니다. 358행을 골랐다고 해서 같은 녹음이라고 확정한 것도, 지금 재생된다고 확인한 것도 아닙니다.

### 추가 조회에 쓰는 컬럼

- `candidate_ids`: API에 요청할 Jamendo 곡 ID. 여러 개면 하나씩 조회합니다.
- `song_id`: 추천 모델의 KKBox 곡 ID. API 응답을 추천 결과에 이을 때 씁니다.
- 나머지 검토 컬럼은 조회에 꼭 필요하지 않습니다. `train_event_rows`, `present_in_train`은 예전에 참고하려고 센 값이라, 지금 모델이 쓰는 데이터 범위와는 관계없습니다.

## 381곡 추가 조회 결과

| 파일 | 내용 |
|---|---|
| `jamendo/jamendo_results/jamendo_381_full/jamendo_381_full.csv` | 381곡에 연결된 Jamendo ID의 추가 조회 결과. API가 준 필드를 모두 저장. 연결이 여러 개인 곡은 행을 나눠서 381행보다 많을 수 있음 |
| `jamendo/jamendo_results/jamendo_381_full/jamendo_381_api_raw.json` | API 원본 응답과 진행 기록. 다시 실행하면 성공한 ID는 건너뛰고, 요청별 응답과 오류도 여기서 확인 |

저장 위치는 기본적으로 입력 CSV 옆의 `jamendo_381_full` 폴더이고, `--output-dir`로 바꿀 수 있습니다. 이어서 실행하려면 입력과 출력 폴더를 이전과 같게 해야 합니다.

### 앱이 쓰는 API 필드

| 필드 | 뜻 |
|---|---|
| `id` | Jamendo 곡 ID |
| `name` | 곡명 |
| `artist_name` | 아티스트 |
| `album_name` | 앨범명 |
| `duration` | 곡 길이(초) |
| `audio` | 재생 URL |
| `image` | 곡 커버 이미지 URL |
| `album_image` | 앨범 이미지 URL. 싱글은 비어 있을 수 있음 |
| `license_ccurl` | 라이선스 URL |
| `audiodownload_allowed` | 다운로드 허용 여부 |
| `lyrics` | 가사 |
| `musicinfo.tags.genres` | 장르 이름 목록 |
| `licenses.*` | 라이선스 관련 추가 정보 |
| `stats.*` | 청취, 다운로드, 즐겨찾기 등 통계 |

필드 이름은 API 그대로입니다. CSV에서는 중첩 객체를 점(`.`)으로 펼치고 배열은 JSON 문자열로 넣었고, 원본 JSON은 중첩 구조를 그대로 둡니다. 곡에 따라 비어 있는 필드도 있습니다.

`mapping.song_id`, `mapping.jamendo_id` 같은 컬럼은 곡을 연결하려고 넣은 것이고, `fetch.*`는 조회 상태를 적으려고 코드에서 추가한 컬럼입니다. 둘 다 API 필드는 아닙니다.

### 조회 상태

| 상태 | 뜻 |
|---|---|
| `success` | 추가 필드까지 요청해서 해당 ID의 곡 정보를 받음. 모든 필드에 값이 있다는 뜻은 아님 |
| `partial` | 기본 곡 정보만 받고, 추가 필드를 포함한 조회는 실패. 받은 정보는 저장 |
| `empty_response` | 모든 조건으로 조회해서 정상 응답을 받았지만 결과가 빈 목록 |
| `unresolved` | 오류가 났거나 요청과 다른 ID가 응답돼서 해결하지 못함 |
| `access_error` | 인증, 접근 권한, 요청 제한 때문에 조회를 멈춤. 이유는 원본 응답에서 확인 |
| `pending` | 아직 처리하지 않음 |
| `not_found` | 이전 코드가 쓰던 상태로, 해당 ID의 정보가 오지 않았다는 뜻. 지금 코드에서는 다시 조회함 |

`empty_response`와 `not_found`는 재생이 안 되는 것을 확인했다는 뜻이 아닙니다. 처음 수집한 SQLite에는 그 ID의 정보와 재생 URL이 남아 있을 수 있습니다. 추가 조회 코드는 SQLite를 읽거나 합치지 않기 때문에, 새로 조회해서 실패해도 기존 정보가 사라지는 것은 아닙니다.

이 작업이 저장하는 것은 재생 URL과 이미지 URL이고, 음원이나 이미지 파일을 내려받지는 않습니다. URL이 있는 것과 플레이어에서 실제로 재생되는 것은 별개라서, 재생은 따로 확인해야 합니다.

## 초기 재생 테스트

| 파일 | 내용 |
|---|---|
| `jamendo/jamendo_results/jamendo_audio_samples.json` | 처음 재생을 시험할 때 쓴 샘플 곡과 오디오 정보 |
| `jamendo/jamendo_results/audio_test.html` | 브라우저에서 샘플 음원의 재생 버튼을 눌러 보는 테스트 페이지 |

초기 샘플 테스트용이어서 381곡 전체를 조회하거나 재생해 본 결과는 아닙니다.

## 작업 순서

1. `songs.csv`와 `song_extra_info.csv`를 합쳐 `song_data.csv`를 만듭니다.
2. Jamendo API로 전체 카탈로그를 모아 `jamendo_catalog.sqlite`에 저장합니다.
3. KKBox 통합 데이터와 Jamendo 데이터를 비교해 `kkbox_jamendo_candidates.csv`를 만듭니다.
4. 처음 고른 381곡과 연결 ID를 `jamendo_song_audit.csv`에 정리합니다.
5. 그 ID로 Jamendo API에서 기본·추가 정보를 조회해 `jamendo_381_full` 폴더에 CSV와 원본 JSON을 저장합니다.
6. 앱은 모델의 KKBox `song_id`를 Jamendo ID와 이어서 쓰고, 받아 둔 `audio`와 `image`를 사용합니다.

지금 돌리는 381곡 추가 조회는 나중에 고른 `jamendo_final_candidates.csv`를 입력으로 쓰지 않습니다. 추천 모델도 이 작업으로 바뀌지 않습니다.

## YouTube API 검토 (서비스에는 적용하지 않음)

Jamendo를 쓰기 전에 YouTube Data API v3로 KKBox 곡명과 아티스트를 검색해, 이어 붙일 만한 영상이 있는지 살펴봤습니다. 검색 결과에서 영상 후보를 모으고 곡마다 연결 가능성을 검토했습니다.

YouTube에서 얻는 것은 음원 재생 주소가 아니라 영상입니다. 재생도 YouTube 영상 플레이어로 해야 해서, 음원 위주로 재생하는 이 앱에는 쓰지 않기로 했습니다. 아래 파일은 검토 기록으로만 남겼고, 지금의 Jamendo 기반 데이터에는 쓰지 않습니다.

### 폴더 구조

저장소에는 `youtube_match.py`만 올라가 있고 `youtube_results/`의 결과 파일은 없습니다.

```text
youtube/
├── youtube_match.py                    [저장소]
└── youtube_results/
    ├── youtube_candidates_KR.csv
    ├── youtube_matches.sqlite
    ├── youtube_matches.sqlite-shm
    └── youtube_matches.sqlite-wal
```

| 파일 | 내용 |
|---|---|
| `youtube_match.py` | KKBox 곡명·아티스트로 YouTube API를 검색해 영상 후보를 모으고 비교하는 코드 |
| `youtube_results/youtube_candidates_KR.csv` | 검색으로 찾은 영상 후보와 비교 결과. `KR`은 파일 이름의 구분일 뿐이고, 실제 지역 설정은 코드를 확인 |
| `youtube_results/youtube_matches.sqlite` | 검색·비교 결과를 저장한 데이터베이스. 테이블 구조는 코드를 확인 |
| `youtube_results/youtube_matches.sqlite-shm`, `-wal` | SQLite 보조 파일. 지우지 마세요 |

위 설명은 작업할 때의 용도와 파일 목록을 보고 정리한 것이고, 컬럼과 DB 구조를 하나씩 열어 확인한 명세는 아닙니다.

### 검토 결과의 의미

- 영상 후보가 검색됐다는 것은 검색어와 관련된 영상이 있다는 뜻입니다. 같은 곡, 같은 녹음이라는 보장은 없습니다.
- YouTube 영상 주소나 영상 ID는 Jamendo의 `audio`처럼 음원을 바로 재생하는 주소가 아닙니다.
- 이 앱은 YouTube 검색 결과를 재생용 음원 데이터로 쓰지 않고, Jamendo 기반 수집과 연결로 진행합니다.
