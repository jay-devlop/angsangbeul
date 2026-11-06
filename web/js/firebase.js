/* Firebase 연결: 사용자 데이터(프로필·좋아요·플레이리스트·들은 곡 기록)를 Firestore 에 저장·불러오기
   - 로그인: 이메일/비밀번호, 구글. 로그인해야만 앱을 쓸 수 있음(익명 로그인 없음)
   - 저장 위치: users/{uid}/data/{키}  (보안 규칙: 본인 uid 만 읽기·쓰기)
   - app.js 는 그대로 localStorage 를 씀. 여기서 localStorage 변경을 감지해 Firestore 로 보내고,
     시작할 때 Firestore 값이 있으면 localStorage 에 반영(달라졌으면 한 번 새로고침)
   - Firebase 가 안 되면(규칙·로그인 설정 전, 오프라인 등) 지금처럼 localStorage 만으로 그대로 동작 */
import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-app.js";
import { getAuth, onAuthStateChanged, GoogleAuthProvider, signInWithPopup, createUserWithEmailAndPassword, signInWithEmailAndPassword, sendPasswordResetEmail, sendEmailVerification, deleteUser, signOut as fbSignOut } from "https://www.gstatic.com/firebasejs/10.12.2/firebase-auth.js";
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

const SYNC_KEYS = ["ms-profile", "ms-likes", "ms-playlists", "ms-played-ids", "ms-play-history", "ms-recs", "ms-onboarded", "ms-encore"];
const MAX_DOC = 900000;                 // Firestore 문서 한도 1MB 보다 작게
const status = { state: "starting", uid: null, error: null, google: false };
window.MusicSync = status;              // 상태 확인용 (콘솔에서 MusicSync)

const rawSet = Storage.prototype.setItem;
const rawRemove = Storage.prototype.removeItem;
let db = null, auth = null, uid = null, applying = false, timer = null;
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
    return true;
  }
  if (!changed) sessionStorage.removeItem("ms-fb-reload");
  return false;
}

try {
  const app = initializeApp(firebaseConfig);
  auth = getAuth(app);
  auth.languageCode = "ko";            // 인증 메일(비밀번호 재설정 등)을 한국어로
  db = getFirestore(app);
  onAuthStateChanged(auth, async (user) => {
    if (!user) {                       // 로그아웃 상태: 앱이 로그인 화면을 보여 줌
      uid = null; status.uid = null; status.state = "signed-out"; status.google = false;
      if (window.MusicApp && window.MusicApp.setAuth) window.MusicApp.setAuth(null);
      return;
    }
    // 다른 계정으로 바뀌었으면 이 기기에 남은 이전 사용자의 데이터를 비움(다른 사용자 데이터가 섞이거나 새 계정으로 올라가지 않게)
    // 단, 방금 이메일로 가입하는 중이면 이 기기의 값이 새 사용자 자신의 가입 정보라서 비우지 않음
    const owner = localStorage.getItem("ms-owner"), signingUp = sessionStorage.getItem("ms-signing-up") === "1";
    if (owner && owner !== user.uid && !signingUp) {
      applying = true;
      try { SYNC_KEYS.forEach((k) => rawRemove.call(localStorage, k)); rawSet.call(localStorage, "ms-owner", user.uid); } finally { applying = false; }
      if (!sessionStorage.getItem("ms-fb-owner-reload")) { sessionStorage.setItem("ms-fb-owner-reload", "1"); location.reload(); return; }
    } else if (!owner || owner !== user.uid) { rawSet.call(localStorage, "ms-owner", user.uid); }
    sessionStorage.removeItem("ms-fb-owner-reload");
    uid = user.uid; status.uid = uid; status.state = "signed-in";
    status.google = user.providerData.some((p) => p.providerId === "google.com");
    let reloading = false;
    try { reloading = await initialSync(); status.state = "synced"; }
    catch (e) { status.state = "error"; status.error = String(e && e.code || e); console.warn("[MusicSync] 동기화 실패(Firestore 규칙·설정 확인):", e); }
    if (!reloading && window.MusicApp && window.MusicApp.setAuth) window.MusicApp.setAuth(user);   // 데이터를 반영한 뒤 앱에 로그인 사실을 알림
  });
} catch (e) {
  status.state = "error"; status.error = String(e && e.code || e);
  console.warn("[MusicSync] 초기화 실패:", e);
}

// 이메일 가입·로그인·로그아웃 (app.js 가 window.MusicAuth 로 부름)
const unavailable = () => Promise.reject({ code: "auth/unavailable" });
async function flushNow() {            // 로그아웃 전에 아직 못 올린 변경을 올림
  clearTimeout(timer); timer = null;
  const keys = Array.from(dirty); dirty.clear();
  if (uid && db) await Promise.all(keys.map((k) => pushKey(k).catch(() => {})));
}
window.MusicAuth = {
  signUp: (email, pw) => (auth ? createUserWithEmailAndPassword(auth, email, pw) : unavailable()),
  signIn: (email, pw) => (auth ? signInWithEmailAndPassword(auth, email, pw) : unavailable()),
  sendVerification: () => (auth && auth.currentUser ? sendEmailVerification(auth.currentUser, { url: location.origin + "/#Login" }) : unavailable()),   // 인증 메일 발송(재전송 포함)
  discardUser: async () => { if (auth && auth.currentUser) { try { await deleteUser(auth.currentUser); } catch (e) { await fbSignOut(auth); } } },   // 인증 전에 이메일을 바꿀 때: 만들어 둔 미인증 계정을 지움
  checkVerified: async () => { if (!auth || !auth.currentUser) return false; await auth.currentUser.reload(); return !!auth.currentUser.emailVerified; },   // 메일의 링크를 눌렀는지 서버에서 다시 확인
  resetPassword: (email) => (auth ? sendPasswordResetEmail(auth, email) : unavailable()),   // 재설정 링크 메일 발송
  signOut: async () => {
    try { await flushNow(); } catch (e) { /* 그래도 로그아웃 */ }
    applying = true;
    try { SYNC_KEYS.concat(["ms-owner"]).forEach((k) => rawRemove.call(localStorage, k)); } finally { applying = false; }   // 이 기기에서 다음 사용자에게 이전 사용자의 데이터가 보이지 않게
    try { if (auth) await fbSignOut(auth); } catch (e) { console.warn("[MusicSync] 로그아웃 실패:", e); }
    sessionStorage.clear();
    location.hash = "#LoginEmail";
    location.reload();
  }
};

// 'Google로 계속하기': 구글 계정으로 로그인(처음이면 가입). 이후 이동·장르 선택 팝업은 MusicApp.setAuth 가 처리
function toast(msg) { if (window.MusicApp && window.MusicApp.showToast) window.MusicApp.showToast(msg); else console.log("[MusicSync]", msg); }
async function googleLogin(btn) {
  if (!auth) { toast("로그인을 사용할 수 없어요. 잠시 뒤 다시 시도해 주세요."); return; }
  btn.disabled = true;
  try {
    await signInWithPopup(auth, new GoogleAuthProvider());
    toast("Google 계정으로 로그인했어요.");
  } catch (e) {
    const code = e && e.code || "";
    if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") { /* 사용자가 창을 닫음 */ }
    else if (code === "auth/popup-blocked") toast("팝업이 차단됐어요. 팝업을 허용한 뒤 다시 눌러 주세요.");
    else if (code === "auth/operation-not-allowed") toast("Google 로그인이 아직 켜져 있지 않아요.");
    else if (code === "auth/unauthorized-domain") toast("이 주소는 Google 로그인이 허용되지 않았어요.");
    else { toast("Google 로그인에 실패했어요. 다시 시도해 주세요."); console.warn("[MusicSync] 구글 로그인 실패:", e); }
  } finally { btn.disabled = false; }
}
document.addEventListener("click", (e) => {
  const btn = e.target.closest && e.target.closest("[data-google-login]");
  if (btn) { e.preventDefault(); googleLogin(btn); }
});
