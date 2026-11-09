# 앙상블 웹 앱

`web/` 폴더는 빌드 도구 없이 동작하는 정적 사이트입니다. HTML·CSS·JavaScript만으로 만들었고, 별도의 설치 없이 폴더를 정적 서버로 열면 실행됩니다. 프로젝트 전체 소개는 [../README.md](../README.md)를 보세요.

## 실행

```bash
cd web
python3 -m http.server 8123
# http://localhost:8123 접속
```

- 화면 파일을 `fetch`로 불러오기 때문에 `index.html`을 파일로 직접 열면 동작하지 않습니다. 반드시 서버로 여세요.
- 로그인하거나 "게스트로 시작하기"를 눌러야 앱이 보입니다. Firebase 설정은 아래 "로그인과 데이터 저장"을 보세요.
- `app.js`·`style.css`·`firebase.js`를 고쳤다면 `index.html`의 `?v=` 번호를 올려야 브라우저가 옛 파일을 쓰지 않습니다(게임 파일은 `game/encore-profile.js`의 iframe 주소 `?v=`도 같이).

## 폴더 구조

```
web/
├─ index.html          진입 페이지(헤더 자리, 화면 자리, 알림창, 오디오). 사이트 아이콘·공유 미리보기 메타 태그
├─ page/               화면별 HTML 조각 (app.js 가 불러와 #pages 에 붙임)
│  ├─ header.html      상단 헤더: 로고, 검색창, 내 계정
│  ├─ sidebar.html     사이드바: 홈·검색·재생 목록·내 라이브러리, 내 현황 카드
│  ├─ signup.html      로그인(LoginEmail: 이메일·Google·게스트), 회원가입(Login), 가입 완료(SignupDone)
│  ├─ home.html        홈: 추천(Main), 전체 음악(HomeBallad)
│  ├─ playing.html     재생 화면(Playing): LP, 곡 정보, 다음 곡·추천곡 목록
│  ├─ search.html      검색: 검색 메인, 전체·곡·아티스트·장르 결과, 아티스트·장르 상세
│  ├─ library.html     내 라이브러리: 좋아요한 곡, 플레이리스트 상세, 새 플레이리스트
│  ├─ status.html      내 현황(Status), 내 계정(Profile)
│  └─ dialogs.html     팝업 마크업(이미지 편집, 플레이리스트 추가, 장르 선택, 비밀번호 찾기)
├─ js/
│  ├─ app.js           앱 동작 전체: 화면 이동, 재생, 검색, 추천, 플레이리스트, 로그인 화면 처리
│  ├─ firebase.js      Firebase 로그인·가입·게스트(익명)·로그아웃, 사용자 데이터 동기화
│  └─ ui-scale.js      화면 너비에 따른 전체 배율(폰 0.78배~1600px 이상 1.22배)
├─ game/               미니게임 앙코르 차트
│  ├─ encore.html      게임 본체(시작·장면·결말·상점). 사이트 안에서는 iframe으로 열림
│  └─ encore-profile.js  헤더 로고로 게임 열기·닫기, 얻은 칭호를 프로필에 표시, 진행(ms-encore) 저장 연동
├─ css/style.css       스타일 전체
├─ data/
│  ├─ catalog.json     곡 목록(Jamendo 실제 곡)과 KKBox 곡 연결표
│  └─ genres.json      장르 11개(이름·색·태그)
├─ icon/               사이트 아이콘, 공유 이미지, 헤드폰·LP·스틱 이미지, 버튼 아이콘
├─ tools/              데이터 만드는 스크립트 (build_catalog.py 등)
└─ demo/               처음 만든 시연용 초안 HTML (앱에서 쓰이지 않음)
```

## 동작 방식

### 화면 이동
- 주소의 해시(`#Main`, `#Playing` 등)로 화면을 바꿉니다. `app.js`가 시작할 때 `page/*.html`을 모두 불러와 한 문서에 붙이고, 해시에 맞는 `<section class="screen">`만 보여 줍니다.
- 헤더와 사이드바는 한 번만 만들어 화면마다 복사해서 씁니다. 재생바는 화면 아래에 떠 있는 하나의 요소입니다.
- 로그인하지 않았으면 어느 화면으로 가든 로그인 화면(`#LoginEmail`)으로 보냅니다. 계정으로 로그인한 사람이 로그인·가입 화면으로 가면 홈으로 보냅니다. 게스트는 로그인 화면을 볼 수 있습니다.

### 화면 목록

| 화면(해시) | 내용 |
|---|---|
| `#LoginEmail` | 로그인. 하단에 회원가입, 비밀번호 찾기, "Google로 계속하기", "게스트로 시작하기" |
| `#Login` | 회원가입 1단계(이메일·비밀번호·닉네임), 2단계(장르 선택) |
| `#Main` | 홈 추천(10곡). 넘치면 줄 양 끝에 `<` `>` 버튼으로 옆으로 넘김 |
| `#HomeBallad` | 전체 음악(많이 재생된 순) |
| `#Playing` | 재생 화면 |
| `#SearchHome` 외 | 검색(전체, 곡, 아티스트, 장르), 아티스트·장르 상세 |
| `#Library` | 좋아요한 곡, 내 플레이리스트 |
| `#Status` | 내 현황: 지금까지 들은 곡, 자주 듣는 장르, 초기화 |
| `#Profile` | 내 계정: 닉네임·사진·장르 편집, 로그아웃(게스트는 "로그인" 버튼) |

### 곡 데이터와 재생
- `data/catalog.json`의 곡(Jamendo 실제 음원 주소, 앨범 이미지, 장르 태그, 재생 수)을 목록·검색·추천에 씁니다. `<audio>`로 재생하고, 사용자가 곡을 눌러야만 재생됩니다.
- 곡마다 **대표 장르 하나**를 정합니다(태그 순서에서 처음 나오는 장르, "기타" 그룹 태그는 건너뜀, 태그가 없으면 "기타"). 곡 목록의 장르 표기, 재생 화면 칩, 장르 둘러보기, 장르 지도가 모두 이 값을 씁니다.
- 곡 목록의 한 줄은 화면 파일에 있는 견본 한 줄을 복사해 데이터로 채운 것입니다. 화면 파일에 적힌 "겨울의 끝에서" 같은 글자는 견본이라 화면에 나오지 않습니다.

### 추천
- 서로 다른 3곡을 듣기 전에는 추천이 없습니다(재생 화면의 하단 목록은 전체 곡).
- 3곡부터 이 사용자의 기록(들은 곡, 좋아요, 가입 때 고른 장르)으로 점수를 계산해 10곡을 추천하고, 이후 3곡 더 들을 때마다 새로 구성합니다. 이미 들은 곡은 제외하고 한 장르가 6곡을 넘지 않으며, 마지막 2곡은 아직 안 들어 본 장르입니다.
- 추천 서버(`../server`)가 켜져 있으면(`localhost`에서만) 처음 취향의 참고로 쓰고, 곡을 들을수록 영향이 줄어 12곡이면 0이 됩니다. 서버가 없어도 동작합니다.
- 추천 목록은 스냅샷(`ms-recs`)으로 저장되어 새로고침해도 같고, 재생 화면의 다음 곡·추천곡도 이 목록을 따릅니다.

### 로그인과 데이터 저장
- `firebase.js`가 Firebase Authentication(이메일/비밀번호, Google, 익명)과 Firestore를 연결합니다. 설정값은 파일 위쪽 `firebaseConfig`에 있습니다.
- **게스트로 시작하기**는 Firebase 익명 로그인(`signInAnonymously`)입니다. 이미 이 브라우저에서 게스트였다면 바로 홈으로 가고, 처음이면 익명 계정을 만든 뒤 홈으로 갑니다(취향 선택 기록이 없으면 장르 선택 팝업). 게스트 데이터는 그 브라우저에만 이어지며, 게스트가 계정으로 로그인하면 게스트 기록은 비워집니다. 콘솔의 Authentication에서 **익명**을 켜야 동작합니다.
- 앱은 브라우저 `localStorage`를 읽고 쓰고, `firebase.js`가 변경을 감지해 Firestore `users/{uid}/data/{키}`에 동기화합니다. 시작할 때 클라우드에 값이 있으면 이 기기에 반영합니다(달라지면 한 번 새로고침).
- 다른 계정으로 로그인하거나 로그아웃하면 이 기기에 남은 이전 사용자의 데이터를 지웁니다.
- `app.js`의 `window.MusicApp`과 `firebase.js`의 `window.MusicAuth`, `window.MusicSync`로 서로 연결됩니다(`MusicSync`는 콘솔에서 상태 확인용: `state`, `uid`, `anonymous` 등).

#### 저장하는 값 (localStorage 키)

| 키 | 내용 | 클라우드 동기화 |
|---|---|---|
| `ms-profile` | 닉네임, 사진, 장르 | O |
| `ms-likes` | 좋아요한 곡 | O |
| `ms-playlists` | 내 플레이리스트 | O (큰 이미지 제외) |
| `ms-played-ids`, `ms-play-history` | 들은 곡 기록과 순서 | O |
| `ms-recs` | 추천 스냅샷 | O |
| `ms-onboarded` | 가입(취향 선택) 완료 표시 | O |
| `ms-encore` | 앙코르 차트 진행(코인·구매내역·장착 칭호) | O |
| `ms-owner` | 이 기기의 현재 사용자 | X |
| `ms-nicknames`, `ms-recent`, `ms-sidebar`, `ms-volume`, `ms-upnext-collapsed` | 닉네임 목록, 최근 검색어, 화면 설정 | X |

`ms-guest-go`, `ms-signing-up`, `ms-fb-reload`, `ms-fb-owner-reload`는 로그인 흐름을 이어 가려고 잠깐 쓰는 값이라 localStorage가 아닌 sessionStorage에 둡니다.

### 앙코르 차트 (미니게임)
- 헤더의 헤드폰 로고(또는 `data-encore-open` 요소)를 누르면 `game/encore.html`이 전체 화면 창(iframe)으로 열립니다. 닫아도 진행 상황이 남고 음악 재생은 끊기지 않습니다. 게임 안의 홈 버튼이나 Esc로 닫습니다.
- 사이트는 폰에서 화면 전체에 `zoom`을 적용하기 때문에, 게임 창은 그 배율을 상쇄(`fitShell`)해 실제 화면 크기로 열고 게임 안의 `ui-scale.js`가 메인 사이트와 같은 방식으로 배율을 맞춥니다.
- 진행은 `ms-encore`에 저장되고 게임이 iframe 안에서 돌기 때문에 저장은 부모 창이 다시 해서 Firestore와 동기화됩니다.

### 알림
- **토스트:** `showToast`로 하단에 잠깐 뜨는 안내(로그인 결과 등).
- **앙상블 Coupon:** `showCoupon`. 로그인한 상태로 앱을 연 지 10분(`COUPON_DELAY_MS`)이 지나면 오른쪽 아래에 초록 티켓 모양 알림("36시간 동안 광고 제거")이 한 번 뜨고 ✕로 닫습니다. 접속할 때마다 새로 셉니다. 아직 광고 기능이 없어 문구만 보여 줍니다.

### 팝업
팝업의 마크업은 `page/dialogs.html`의 `<template>`에 있고, `app.js`가 복제해서 곡·플레이리스트 같은 가변 부분만 채웁니다.

| 팝업 | 템플릿 |
|---|---|
| 이미지 편집(플레이리스트 이미지, 프로필 사진) | `tplImageEditor` |
| 플레이리스트에 추가 | `tplPlaylistPicker` |
| 구글 첫 로그인·게스트 시작 후 장르 선택 | `tplGenrePicker` |
| 비밀번호 찾기(재설정 메일 발송) | `tplForgotPassword` |
| 이메일 인증 안내(이메일로 가입했을 때. 인증하기 전에는 닫을 수 없음) | `tplVerifyEmail` |

## 디자인 메모

- **색:** 본문 `#121313`, 헤더·사이드바 `#101010`, 카드 `#17171d`, 포인트 `#3ddc97`. 색 변수는 `css/style.css`의 `:root`에 있습니다.
- **재생 화면:** LP는 `lp.png` 위에 앨범 이미지를 얹고, 스틱(`lp_stick2.png`)과 원형·타원형 받침이 재생 상태에 맞춰 600ms 동안 움직입니다. 값은 `.arm-set`의 CSS 변수(`--play-x`, `--rest-rotate` 등)로 조절합니다.
- **글꼴:** Noto Sans KR(Google Fonts).
- **화면 배율:** `ui-scale.js`가 화면 너비에 맞춰 문서 전체에 `zoom`을 적용합니다(480px 미만은 0.78배까지 줄고 1600px 초과는 1.22배까지 커짐). CSS의 `vh`·`vw`는 이 배율(`--z`)로 나눠 써서 화면을 꽉 채웁니다.
- **사이트 아이콘·공유 이미지:** `icon/favicon-*.png`, `apple-touch-icon.png`, `og-image.png`는 `headphone.png`(투명 배경)를 정사각형·가로형으로 만든 것입니다.

## 곡 데이터 다시 만들기

```bash
python3 tools/build_catalog.py
```

수집해 둔 Jamendo CSV로 `data/catalog.json`을 만듭니다(API는 호출하지 않습니다). 입력 CSV는 저장소에 없고, 스크립트가 `music data/` 아래의 `jamendo_results/jamendo_381_full/jamendo_381_full.csv`, `jamendo/jamendo_full/jamendo_full.csv` 순서로 찾습니다. 다른 위치라면 경로를 인자로 넘기세요(`python3 tools/build_catalog.py <CSV 경로>`).

다시 실행하면 카탈로그에서 일부러 뺀 곡이 되살아날 수 있습니다.

## 배포 (Vercel)

Root Directory를 `web`으로, Framework Preset을 Other로 두고 Build·Output은 비워 두면 됩니다. 배포 후 Firebase 콘솔의 Authentication → 설정 → **승인된 도메인**에 배포 주소를 추가해야 로그인이 됩니다.

## 알아둘 점

- 게스트로 쓰다가 사이트 데이터를 지우거나 다른 브라우저로 열면 이전 기록은 사라집니다. 이어서 쓰려면 이메일이나 Google로 가입하세요.
- 비밀번호 찾기는 비밀번호를 보여 주지 않고 재설정 링크를 이메일로 보냅니다.
- 플레이리스트 삭제는 PC는 오른쪽 클릭, 모바일은 꾹 누르기입니다.
