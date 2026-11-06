# 앙상블 (음악 추천 웹 서비스)

취향에 맞는 음악을 추천해 주는 뮤직 스트리밍 데모입니다. 장르와 청취 기록을 바탕으로 사용자마다 다른 추천을 보여 주고, 곡은 [Jamendo](https://www.jamendo.com) 음원으로 실제 재생됩니다.

KKBox 청취 기록으로 만든 추천 모델(v11)과 다양성 보정 연구를 웹 서비스로 연결한 프로젝트입니다.

## 주요 기능

| 기능 | 설명 |
|---|---|
| 회원가입·로그인 | 이메일/비밀번호, Google. 로그인해야만 앱을 사용할 수 있습니다. 비밀번호 찾기는 재설정 메일을 보냅니다. |
| 취향 선택 | 가입할 때 좋아하는 장르를 최대 3개 고릅니다(Google 첫 로그인은 팝업으로 선택). |
| 개인 추천 | 서로 다른 3곡을 들으면 추천이 나타나고, 이후 3곡 더 들을 때마다 새로 구성됩니다. 같은 사용자는 새로고침해도 같은 추천을 봅니다. |
| 재생 | LP 모양 재생 화면, 다음 곡·추천곡 목록(접기/펴기), 하단 재생바(볼륨 조절 팝업). |
| 검색 | 곡·아티스트·장르 검색, 최근 검색어. |
| 내 라이브러리 | 좋아요한 곡, 내 플레이리스트(곡 추가, 우클릭·꾹 누르기로 삭제). |
| 내 현황 | 지금까지 들은 곡, 자주 듣는 장르, 추천 초기화. |

## 추천 방식

1. **서로 다른 3곡을 듣기 전:** 추천을 보여 주지 않습니다(첫 사용자는 1~2곡을 들어도 추천 없음). 이때 재생 화면 하단에는 전체 곡이 나옵니다.
2. **3곡부터:** 이 사용자의 기록만으로 점수를 계산합니다.
   - 장르 취향(들은 곡, 좋아요, 가입 때 고른 장르), 아티스트 취향, 인기도(작게)
   - 처음에는 장르별 대리 사용자의 모델 추천(서버)을 참고하고, 곡을 들을수록 영향이 줄어 12곡이면 0이 됩니다.
   - 이미 들은 곡은 제외하고, 한 장르가 몰리지 않게 장르당 6곡까지, 마지막 2곡은 아직 안 들어 본 장르(새로운 발견)입니다.
3. **추천은 10곡**입니다(보고서의 Top-10 기준).
4. 추천 목록은 스냅샷으로 저장·동기화되어 같은 사용자는 항상 같은 결과를 봅니다.

추천 서버(`server/`)는 선택 사항입니다. 서버가 없어도 개인 추천은 동작합니다.

## 사용자 데이터와 보안

- **인증:** Firebase Authentication(이메일/비밀번호, Google). 익명 로그인은 사용하지 않습니다.
- **저장:** Firestore `users/{uid}/data/{키}` (프로필, 좋아요, 플레이리스트, 들은 곡 기록, 들은 순서, 추천 스냅샷, 가입 완료 표시). 브라우저 localStorage를 먼저 쓰고 클라우드와 동기화합니다.
- **계정 분리:** 다른 계정으로 로그인하거나 로그아웃하면 이 기기에 남은 이전 사용자의 데이터를 지워, 다른 사용자의 데이터가 섞이지 않습니다.
- **이미지:** 플레이리스트 커버와 프로필 사진은 문서 크기 한도 때문에 클라우드에 올리지 않고 이 기기에만 저장합니다.
- 비밀번호는 Firebase가 암호화해서 보관하며 어디에서도 조회할 수 없습니다.

Firestore 보안 규칙 (본인 데이터만 읽고 쓰기):

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{uid}/{document=**} {
      allow read, write: if request.auth != null && request.auth.uid == uid;
    }
  }
}
```

## 폴더 구조

```
web/                 웹 앱(정적 사이트, 빌드 없음)
  index.html         진입 페이지
  page/              화면별 HTML (home, playing, search, library, status, signup, dialogs 등)
  js/app.js          화면 이동·재생·검색·추천 등 앱 동작
  js/firebase.js     로그인·Firestore 동기화
  js/ui-scale.js     화면 너비에 따라 전체 크기를 키우고 줄임(폰 0.78배까지, 1600px 이상 1.22배까지)
  game/              앙코르 차트 미니게임(encore.html)과 프로필 연동(encore-profile.js)
  css/style.css      스타일
  data/              곡 목록(catalog.json), 장르 목록(genres.json)
  tools/             데이터 만드는 스크립트
server/              추천 서버(선택): v11 모델로 장르별 대리 사용자 추천 계산
ML 개발/             추천 모델(v1~v12)
ML 보정/             다양성 보정 실험
music data/          곡 메타데이터와 Jamendo 수집 결과
```

## 실행 방법

### 1. 웹 앱 (로컬)

`web` 폴더를 정적 서버로 열면 됩니다.

```bash
cd web
python3 -m http.server 8123
# http://localhost:8123 접속
```

### 2. Firebase 설정

`web/js/firebase.js`의 `firebaseConfig`를 본인 프로젝트 값으로 바꾸고, 콘솔에서 아래를 설정합니다.

1. Authentication → 로그인 방법에서 **이메일/비밀번호**와 **Google**을 켭니다(익명은 켜지 않습니다).
2. Authentication → 설정 → **승인된 도메인**에 배포 주소를 추가합니다(`localhost`는 기본 포함).
3. Firestore Database를 만들고 위의 보안 규칙을 게시합니다.

### 3. 추천 서버 (선택)

가입 직후 처음 취향의 참고 추천을 쓰고 싶을 때만 실행합니다. 자세한 내용은 [server/README.md](server/README.md)를 보세요.

```bash
pip install -r server/requirements.txt
python3 server/app.py          # 포트 8010
```

서버 주소는 `localhost`에서만 연결됩니다. 배포 환경에서는 서버 없이 개인 추천만 동작합니다.

### 4. 곡 데이터 다시 만들기

Jamendo 수집 CSV에서 `web/data/catalog.json`을 만듭니다(API 호출 없음).

```bash
python3 web/tools/build_catalog.py
```

> 이 스크립트를 다시 실행하면 카탈로그에서 일부러 뺀 곡이 되살아날 수 있습니다.

## 배포 (Vercel)

빌드가 필요 없는 정적 사이트라서 설정이 간단합니다.

| 항목 | 값 |
|---|---|
| Root Directory | `web` |
| Framework Preset | Other |
| Build / Output | 비워 둠 |

배포한 뒤 위의 Firebase **승인된 도메인**에 배포 주소를 꼭 추가하세요. 링크 공유 미리보기 이미지는 `web/icon/og-image.png`입니다.

## 곡 데이터

- 곡 349곡은 Jamendo에서 수집한 실제 음원입니다(`web/data/catalog.json`).
- 곡마다 대표 장르를 하나로 정해 분류합니다: 태그 순서에서 처음 나오는 장르이고, "기타" 그룹 태그는 건너뜁니다. 태그가 없는 곡은 "기타"입니다.

## 관련 문서

- `web/기능정의서.md`: 웹 기능 정의
- `web/서버연동_계획.md`: 추천 서버 연결 계획
- `ML 개발/modelA_deliverables/README_modelA.md`: 모델 A 산출물 설명
