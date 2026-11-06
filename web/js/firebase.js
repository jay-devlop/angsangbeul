/* Firebase 연결: 사용자 데이터(프로필·좋아요·플레이리스트·들은 곡 기록)를 Firestore 에 저장·불러오기
   - 로그인: 익명 로그인(가입 없이 같은 브라우저에서 이어짐). 나중에 구글 로그인으로 연결 가능
   - 저장 위치: users/{uid}/data/{키}  (보안 규칙: 본인 uid 만 읽기·쓰기)
   - app.js 는 그대로 localStorage 를 씀. 여기서 localStorage 변경을 감지해 Firestore 로 보내고,
     시작할 때 Firestore 값이 있으면 localStorage 에 반영(달라졌으면 한 번 새로고침)
   - Firebase 가 안 되면(규칙·로그인 설정 전, 오프라인 등) 지금처럼 localStorage 만으로 그대로 동작 */
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, onAuthStateChanged, signInAnonymously } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
import { getFirestore, doc, getDoc, setDoc, serverTimestamp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-firestore.js";

// 웹 앱 설정값: 공개되어도 되는 값 (데이터 보호는 Firestore 보안 규칙이 함)
const firebaseConfig = {
  apiKey: "AIzaSyAClx7scy_uNFIedHNhNlKORSzCHrO7Kjs",
  authDomain: "music-stream-89dcd.firebaseapp.com",
  projectId: "music-stream-89dcd",
  storageBucket: "music-stream-89dcd.firebasestorage.app",
  messagingSenderId: "64219879931",
  appId: "1:64219879931:web:9999e3ebe41f1fc279535e"
};

const SYNC_KEYS = ["ms-profile", "ms-likes", "ms-playlists", "ms-played-ids"];
const MAX_DOC = 900000;                 // Firestore 문서 한도 1MB 보다 작게
const status = { state: "starting", uid: null, error: null };
window.MusicSync = status;              // 상태 확인용 (콘솔에서 MusicSync)

const rawSet = Storage.prototype.setItem;
const rawRemove = Storage.prototype.removeItem;
let db = null, uid = null, applying = false, timer = null;
const dirty = new Set();

// 큰 이미지(data:...)는 문서 한도 때문에 클라우드에 올리지 않음(이 기기에는 그대로 남음)
function slim(key, raw) {
  if (raw == null || raw.length <= MAX_DOC) return raw;
  try {
    const v = JSON.parse(raw);
    if (key === "ms-playlists" && Array.isArray(v)) v.forEach((p) => { if (p && typeof p.cover === "string" && p.cover.startsWith("data:")) delete p.cover; });
    if (key === "ms-profile" && v && typeof v.avatar === "string" && v.avatar.startsWith("data:")) delete v.avatar;
    const out = JSON.stringify(v);
    return out.length <= MAX_DOC ? out : undefined;
  } catch (e) { return undefined; }
}

// 이 기기의 이미지는 보존하면서 클라우드 값을 합침
function mergeImages(key, remoteRaw, localRaw) {
  if (remoteRaw == null || localRaw == null) return remoteRaw;
  try {
    const r = JSON.parse(remoteRaw), l = JSON.parse(localRaw);
    if (key === "ms-playlists" && Array.isArray(r) && Array.isArray(l)) {
      r.forEach((p, i) => { if (p && !p.cover && l[i] && l[i].name === p.name && l[i].cover) p.cover = l[i].cover; });
      return JSON.stringify(r);
    }
    if (key === "ms-profile" && r && l && !r.avatar && l.avatar) { r.avatar = l.avatar; return JSON.stringify(r); }
  } catch (e) { /* 그대로 */ }
  return remoteRaw;
}

async function pushKey(key) {
  const raw = localStorage.getItem(key);
  const value = slim(key, raw);
  if (value === undefined) { console.warn("[MusicSync] 너무 커서 올리지 못함:", key); return; }
  await setDoc(doc(db, "users", uid, "data", key), { value: value, updatedAt: serverTimestamp() }); // 지워진 값은 null 로 남김
}

function flush() {
  timer = null;
  if (!uid) return;
  const keys = Array.from(dirty); dirty.clear();
  keys.forEach((k) => pushKey(k).catch((e) => { status.error = String(e && e.code || e); console.warn("[MusicSync] 저장 실패:", k, e); }));
}

function schedule(key) {
  dirty.add(key);
  if (!uid) return;                      // 로그인 전: 로그인 후 처음 동기화에서 처리
  clearTimeout(timer); timer = setTimeout(flush, 800);
}

// app.js 가 localStorage 에 쓰거나 지울 때 감지
Storage.prototype.setItem = function (k, v) {
  rawSet.call(this, k, v);
  if (this === window.localStorage && !applying && SYNC_KEYS.includes(k)) schedule(k);
};
Storage.prototype.removeItem = function (k) {
  rawRemove.call(this, k);
  if (this === window.localStorage && !applying && SYNC_KEYS.includes(k)) schedule(k);
};

async function initialSync() {
  const remote = {};
  await Promise.all(SYNC_KEYS.map(async (k) => {
    const snap = await getDoc(doc(db, "users", uid, "data", k));
    if (snap.exists()) remote[k] = snap.data().value;    // 문자열 또는 null(지움)
  }));
  const hasRemote = Object.keys(remote).length > 0;
  let changed = false;
  applying = true;
  try {
    for (const k of SYNC_KEYS) {
      const local = localStorage.getItem(k);
      if (k in remote) {
        const merged = mergeImages(k, remote[k], local);
        if (merged !== local) {
          if (merged == null) rawRemove.call(localStorage, k); else rawSet.call(localStorage, k, merged);
          changed = true;
        }
      } else if (local != null && !hasRemote) {
        dirty.add(k);                                    // 클라우드가 비어 있으면 이 기기 값을 올림
      } else if (local != null) {
        dirty.add(k);                                    // 이 키만 클라우드에 없음
      }
    }
  } finally { applying = false; }
  if (dirty.size) flush();
  if (changed && !sessionStorage.getItem("ms-fb-reload")) {
    sessionStorage.setItem("ms-fb-reload", "1");         // 반영한 값으로 앱을 다시 그리기 위해 한 번만 새로고침
    location.reload();
    return;
  }
  if (!changed) sessionStorage.removeItem("ms-fb-reload");
}

try {
  const app = initializeApp(firebaseConfig);
  const auth = getAuth(app);
  db = getFirestore(app);
  onAuthStateChanged(auth, async (user) => {
    if (!user) {
      try { await signInAnonymously(auth); } catch (e) { status.state = "error"; status.error = String(e && e.code || e); console.warn("[MusicSync] 로그인 실패(콘솔에서 익명 로그인을 켰는지 확인):", e); }
      return;
    }
    uid = user.uid; status.uid = uid; status.state = "signed-in";
    try { await initialSync(); status.state = "synced"; }
    catch (e) { status.state = "error"; status.error = String(e && e.code || e); console.warn("[MusicSync] 동기화 실패(Firestore 규칙·설정 확인):", e); }
  });
} catch (e) {
  status.state = "error"; status.error = String(e && e.code || e);
  console.warn("[MusicSync] 초기화 실패:", e);
}
