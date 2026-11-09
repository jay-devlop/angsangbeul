/* 앙코르 차트 프로필 꾸미기. 사이트에 script 한 줄로 붙인다. 안내는 연동안내.md 참고 */
(function () {
"use strict";
function rngOf(seed) { let a = seed >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
/* 움직이는 픽셀 그림. 장면은 120×40, 결말은 96×60 캔버스에 프레임 번호 f로 다시 그린다. */
const PX = { night: "#14283a", deep: "#0c1b28", teal: "#2f6066", gold: "#f4bc3f", coral: "#ff7a5c", mint: "#7fd8be", cream: "#f6ecd6", ink: "#0a151c", red: "#b93a22", plum: "#3d2a4d", wine: "#5b2e45", skin: "#f0c39a", hair: "#2a1a14", blue: "#5a8fb0", wood: "#8a5a34", wood2: "#5e3a22", brick: "#6e3b34", brick2: "#57302c", gray: "#5d6f78", sun: "#ffd166", peach: "#ff9e6d", pink: "#d9667a", wall: "#27424a" };
function kit(cv, f, seed) {
  const c = cv.getContext("2d"), W = cv.width, H = cv.height, r0 = rngOf(seed * 131 + 17);
  c.imageSmoothingEnabled = false; c.globalAlpha = 1;
  const R = (x, y, w, h, fc) => { c.fillStyle = fc; c.fillRect(Math.round(x), Math.round(y), Math.round(w), Math.round(h)); };
  const wave = (sp, ph = 0) => Math.sin(f * sp + ph);
  const bob = (ph = 0) => wave(0.9, ph) > 0 ? 1 : 0;
  const stars = (n, h, fc) => { for (let i = 0; i < n; i++) { const x = Math.floor(r0() * W), y = Math.floor(r0() * h), p = r0() * 6; if (wave(0.5, p) > -0.5) R(x, y, 1, 1, fc || PX.cream); } };
  const person = (x, y, shirt, o = {}) => {
    const d = o.still ? 0 : bob(o.ph || x); const yy = y + d;
    R(x, yy, 4, 4, PX.skin); R(x, yy, 4, 2, o.hair || PX.hair); R(x + 1, yy + 2, 1, 1, PX.ink); R(x, yy + 4, 4, 4, shirt); R(x, yy + 8, 1, 3 - d, PX.ink); R(x + 3, yy + 8, 1, 3 - d, PX.ink);
    if (o.mic) { R(x + 4, yy + 4, 2, 1, PX.skin); R(x + 5, yy + 2, 1, 2, PX.gray); R(x + 5, yy + 1, 2, 1, PX.cream); }
    if (o.guitar) { R(x - 1, yy + 5, 4, 3, PX.wood); R(x + 3, yy + 5, 5, 1, PX.wood2); R(x, yy + 6, 1, 1, PX.ink); R(x + 1 + (f % 2), yy + 4, 1, 1, PX.skin); }
  };
  const crowd = (y, n, fc, sp = 0.9) => { for (let i = 0; i < n; i++) { const x = Math.floor(i * W / n) + Math.floor(r0() * 3), h = 2 + Math.floor(r0() * 3), up = wave(sp, i * 1.7) > 0 ? 1 : 0; R(x, y - h - up, 3, 3, fc); R(x - 1, y - h + 3 - up, 5, 14, fc); if (i % 3 === 0) R(x + 3, y - h - 3 - up * 2, 1, 4, i % 2 ? PX.gold : PX.mint); } };
  const note = (x, y, fc) => { R(x, y, 2, 2, fc); R(x + 1, y - 4, 1, 4, fc); R(x + 2, y - 4, 2, 1, fc); };
  const notes = (x, base, h, fc, ph = 0) => { const t = (f + ph) % h; note(x + Math.round(Math.sin((f + ph) * 0.5) * 2), base - t, fc); };
  const beam = (x0, x1, fc, top = 0, bot = 44, w0 = 2, spread = 13) => { c.globalAlpha = 0.28; for (let y = top; y < bot; y++) { const t = (y - top) / (bot - top), cx = x0 + (x1 - x0) * t, w = w0 + t * spread; R(cx - w, y, w * 2, 1, fc); } c.globalAlpha = 1; };
  const rain = (n, fc) => { for (let i = 0; i < n; i++) { const x = Math.floor(r0() * W), y = (Math.floor(r0() * H) + f * 3) % H; R(x, y, 1, 2, fc); } };
  const confetti = n => { for (let i = 0; i < n; i++) { const x = (Math.floor(r0() * W) + Math.round(Math.sin(f * 0.3 + i) * 2)), y = (Math.floor(r0() * H) + f * (1 + i % 3)) % H; R(x, y, 1, 2, [PX.gold, PX.coral, PX.mint, PX.cream][i % 4]); } };
  const eq = (x, y, n, h, fc) => { for (let i = 0; i < n; i++) { const v = 2 + Math.round((Math.sin(f * 0.8 + i * 1.3) + 1) * (h - 2) / 2); R(x + i * 2, y - v, 1, v, fc); } };
  const heart = (x, y, fc) => { R(x, y, 2, 2, fc); R(x + 3, y, 2, 2, fc); R(x, y + 1, 5, 2, fc); R(x + 1, y + 3, 3, 1, fc); R(x + 2, y + 4, 1, 1, fc); };
  const room = (wall, floor) => { R(0, 0, W, H, wall); R(0, H - 9, W, 9, floor); R(0, H - 9, W, 1, PX.ink); };
  const city = (y, h) => { for (let i = 0, x = 0; x < W; i++) { const w = 8 + Math.floor(r0() * 8), t = y + Math.floor(r0() * 8); R(x, t, w, h, PX.ink); for (let k = 0; k < 3; k++) { const wx = x + 2 + Math.floor(r0() * (w - 3)), wy = t + 2 + Math.floor(r0() * 6); if (wave(0.3, k + i) > -0.6) R(wx, wy, 1, 1, PX.gold); } x += w; } };
  const speech = (x, y, w, fc, tx) => { R(x, y, w, 7, fc); R(x + 2, y + 7, 2, 2, fc); for (let i = 0; i < 3; i++) R(x + 2, y + 1 + i * 2, w - 4 - i * 3, 1, tx); };
  return { c, W, H, R, wave, bob, stars, person, crowd, note, notes, beam, rain, confetti, eq, heart, room, city, speech, f, rnd: r0 };
}
const SCENE_ART = {
  start(k) { const { R, W, f } = k; R(0, 0, W, 40, PX.night); k.stars(18, 14); k.city(16, 24); R(0, 31, W, 9, PX.gray); R(0, 31, W, 1, PX.teal);
    R(14, 8, 30, 12, PX.ink); R(15, 9, 28, 10, f % 4 < 2 ? PX.pink : PX.wine); R(19, 12, 20, 2, PX.cream); k.person(56, 20, PX.mint, { ph: 1 }); k.person(72, 20, PX.gray, { hair: PX.ink, ph: 2 }); R(64 + (f % 6 < 3 ? 0 : 1), 24, 6, 3, PX.cream); R(65, 25, 3, 1, PX.gray); },
  yun(k) { const { R } = k; k.room(PX.wall, PX.wood); for (let x = 6; x < 114; x += 26) { R(x, 4, 24, 22, PX.blue); R(x + 2, 6, 6, 18, PX.teal); } R(0, 26, 120, 2, PX.gray); k.person(40, 20, PX.coral, { ph: 0 }); k.person(66, 20, PX.mint, { hair: PX.wine, ph: 3 }); k.notes(54, 20, 14, PX.gold); k.notes(78, 20, 14, PX.cream, 7); },
  debut(k) { const { R } = k; R(0, 0, 120, 40, PX.deep); R(0, 0, 58, 40, PX.plum); R(58, 0, 3, 40, PX.ink); k.person(22, 19, PX.coral, { still: false }); R(32, 12, 2, 19, PX.gray); R(30, 11, 6, 5, PX.cream); R(0, 31, 58, 9, PX.wood2); R(70, 24, 42, 10, PX.ink); R(72, 6, 38, 16, PX.ink); R(73, 7, 36, 14, PX.teal); k.eq(75, 20, 17, 12, PX.mint); for (let i = 0; i < 10; i++) R(72 + i * 4, 26, 2, 2, (k.f + i) % 3 ? PX.gray : PX.gold); },
  viral(k) { const { R, f } = k; R(0, 0, 120, 40, PX.plum); k.stars(12, 40, PX.pink); R(46, 2, 28, 36, PX.ink); R(48, 4, 24, 30, PX.coral); k.person(58, 14, PX.mint, { ph: 0 }); R(49, 5, 22, 3, PX.wine); for (let i = 0; i < 4; i++) { const y = 34 - ((f * 2 + i * 9) % 34); k.heart(16 + i * 6 + Math.round(Math.sin(f * 0.4 + i) * 2), y, i % 2 ? PX.coral : PX.pink); k.heart(84 + i * 6, 34 - ((f * 2 + i * 13) % 34), i % 2 ? PX.gold : PX.coral); } },
  still(k) { const { R, f } = k; k.room(PX.wall, PX.wood2); R(30, 6, 60, 26, PX.ink); R(32, 8, 56, 22, PX.cream); R(38, 12, 44, 12, PX.wood); const reel = (x) => { R(x - 4, 14, 9, 9, PX.ink); R(x - 2, 16, 5, 5, PX.cream); const a = f % 4; R(x + [0, 1, 0, -1][a], 18 + [-1, 0, 1, 0][a], 1, 1, PX.ink); }; reel(50); reel(70); R(50, 22, 20, 2, PX.gold); for (let i = 0; i < 5; i++) k.person(4 + i * 5, 21, PX.teal, { still: true, hair: PX.ink }); for (let i = 0; i < 5; i++) k.person(95 + i * 5, 21, PX.teal, { still: true, hair: PX.ink }); },
  lambda(k) { const { R, f } = k; R(0, 0, 120, 40, PX.deep); R(8, 3, 104, 34, PX.ink); const t = (Math.sin(f * 0.25) + 1) / 2, rows = [[PX.gray, 60 - t * 18], [PX.gray, 50 - t * 14], [PX.mint, 22 + t * 34], [PX.gray, 40 - t * 8], [PX.gold, 16 + t * 28]]; rows.forEach((r, i) => { R(14, 6 + i * 6, 3, 4, PX.teal); R(20, 6 + i * 6, r[1] * 1.3, 4, r[0]); }); if (f % 4 < 2) { R(100, 7, 8, 3, PX.coral); } k.notes(106, 34, 16, PX.gold); },
  bside(k) { const { R, f } = k; k.room(PX.wall, PX.gray); R(8, 4, 44, 20, PX.cream); R(11, 8, 18, 2, PX.coral); R(11, 13, 30, 2, PX.teal); R(11, 18, 22, 2, PX.teal); R(22, 28, 76, 3, PX.wood); R(24, 31, 2, 9, PX.wood2); R(94, 31, 2, 9, PX.wood2); [34, 52].forEach((x, i) => { R(x, 21 - (f % 6 < 3 && i ? 1 : 0), 10, 7, i ? PX.gold : PX.coral); }); k.person(66, 18, PX.mint, { ph: 1 }); k.person(82, 18, PX.gray, { hair: PX.ink, ph: 3 }); k.person(100, 18, PX.coral, { hair: PX.wine, ph: 5 }); },
  album(k) { const { R, f } = k; R(0, 0, 120, 40, PX.plum); R(8, 4, 44, 22, PX.ink); R(10, 6, 40, 18, PX.deep); k.eq(12, 22, 19, 15, PX.coral); R(0, 28, 120, 12, PX.wood2); R(58, 12, 54, 18, PX.ink); for (let i = 0; i < 12; i++) { R(61 + i * 4, 15, 1, 12, PX.gray); R(60 + i * 4, 16 + Math.round((Math.sin(f * 0.4 + i) + 1) * 4), 3, 2, i % 3 ? PX.cream : PX.gold); } k.notes(54, 12, 10, PX.gold); },
  edition(k) { const { R, f } = k; k.room(PX.wall, PX.wood); R(16, 22, 88, 3, PX.wood2); [PX.coral, PX.gold, PX.mint, PX.pink, PX.blue].forEach((col, i) => { const y = 8 + (((f + i * 2) % 8 < 4) ? 0 : 1); R(20 + i * 17, y, 13, 13, col); R(23 + i * 17, y + 3, 7, 7, PX.ink); R(25 + i * 17, y + 5, 3, 3, PX.cream); }); k.person(8, 18, PX.gray, { hair: PX.ink }); k.person(108, 18, PX.mint); },
  ab(k) { const { R, f } = k; k.room(PX.plum, PX.wood2); k.person(14, 20, PX.coral, { mic: true }); for (let i = 0; i < 5; i++) { k.person(46 + i * 13, 20, [PX.mint, PX.gold, PX.blue, PX.pink, PX.mint][i], { ph: i * 2 }); R(46 + i * 13, 19, 4, 1, PX.ink); } k.speech(50, 3, 16, PX.cream, PX.gray); if (f % 8 > 3) k.speech(84, 5, 16, PX.gold, PX.wood2); },
  encore(k) { const { R } = k; R(0, 0, 120, 40, PX.deep); k.stars(16, 16); k.beam(14, 58, PX.gold, 0, 26, 2, 9); k.beam(106, 62, PX.coral, 0, 26, 2, 9); R(30, 25, 60, 3, PX.wood); k.person(58, 14, PX.mint, { mic: true }); k.crowd(36, 24, PX.ink); k.confetti(16); },
  three(k) { const { R } = k; R(0, 0, 120, 40, PX.deep); k.beam(60, 60, PX.gold, 0, 22, 2, 12); R(36, 21, 48, 3, PX.wood); k.person(58, 10, PX.coral, { guitar: true }); for (let y = 26; y < 40; y += 6) for (let x = 8; x < 116; x += 10) R(x, y, 7, 4, PX.teal); [[28, 26], [58, 32], [88, 26]].forEach(p => { R(p[0] + 1, p[1] - 3, 4, 4, PX.skin); R(p[0] + 1, p[1] - 3, 4, 2, PX.hair); R(p[0], p[1] + 1, 6, 3, PX.mint); }); },
  pay(k) { const { R, f } = k; k.room(PX.wall, PX.wood2); R(0, 24, 120, 16, PX.wood); R(36, 8, 34, 24, PX.cream); for (let i = 0; i < 5; i++) R(40, 12 + i * 3, i === 4 ? 12 : 26, 1, PX.gray); R(58, 24, 8, 2, PX.red); R(80, 14, 16, 18, PX.ink); R(82, 16, 12, 4, f % 6 < 3 ? PX.mint : PX.teal); for (let y = 0; y < 3; y++) for (let x = 0; x < 3; x++) R(82 + x * 4, 22 + y * 3, 3, 2, PX.gray); R(12, 26, 6, 2, PX.gold); R(14, 23, 6, 2, PX.gold); },
  cold(k) { const { R, f } = k; k.room(PX.plum, PX.wood2); R(20, 18, 66, 14, PX.cream); R(20, 22, 66, 10, PX.blue); R(16, 12, 6, 22, PX.wood); R(84, 18, 6, 16, PX.wood); R(26, 15 + k.bob(), 8, 7, PX.skin); R(26, 15 + k.bob(), 8, 3, PX.hair); R(98, 8, 2, 16, PX.cream); R(98, 14, 2, 10, PX.red); for (let i = 0; i < 3; i++) R(40 + i * 6 + Math.round(Math.sin(f * 0.6 + i)), 12 - ((f + i * 3) % 9), 2, 1, PX.cream); },
  mom(k) { const { R, f } = k; R(0, 0, 60, 40, PX.deep); R(60, 0, 60, 40, PX.gold); R(58, 0, 4, 40, PX.ink); k.stars(10, 40); k.person(26, 22, PX.mint); R(32, 25, 2, 5, PX.gray); R(64, 26, 52, 14, PX.wood); R(74, 21, 10, 5, PX.cream); R(92, 21, 10, 5, PX.cream); for (let i = 0; i < 2; i++) R(78 + i * 18, 18 - (f + i * 2) % 6, 1, 2, PX.cream); if (f % 6 < 3) { R(35, 18, 2, 2, PX.gold); R(38, 15, 2, 2, PX.gold); R(41, 12, 2, 2, PX.gold); } },
  hate(k) { const { R, f } = k; R(0, 0, 120, 40, PX.deep); k.c.globalAlpha = 0.3; R(30, 8, 40, 32, PX.blue); k.c.globalAlpha = 1; k.person(44, 24, PX.gray, { still: true }); R(52, 25, 5, 8, PX.blue); [[66, 4], [84, 12], [72, 20], [92, 26]].forEach((p, i) => { if ((f + i * 3) % 12 > i * 2) k.speech(p[0], p[1], 18, i % 2 ? PX.red : PX.wine, PX.cream); }); },
  street(k) { const { R, f } = k; R(0, 0, 120, 40, PX.plum); k.city(10, 30); R(0, 30, 120, 10, PX.gray); R(0, 30, 120, 1, PX.teal); k.person(54, 19, PX.coral, { guitar: true }); R(42, 28, 8, 3, PX.wood2); k.notes(66, 18, 12, PX.gold); k.person((f * 2) % 130 - 8, 19, PX.mint, { hair: PX.ink }); k.person(112 - (f * 1.5) % 130, 19, PX.gold, { hair: PX.wine, ph: 2 }); },
  radio(k) { const { R, f } = k; k.room(PX.deep, PX.wood2); R(6, 4, 26, 9, f % 4 < 2 ? PX.red : PX.wine); R(9, 7, 20, 3, PX.cream); k.person(40, 19, PX.coral); R(46, 15, 2, 8, PX.gray); R(44, 14, 5, 4, PX.cream); k.person(92, 19, PX.mint, { hair: PX.wine, ph: 3 }); R(58, 24, 30, 7, PX.ink); k.eq(60, 30, 13, 6, PX.gold); },
  voice(k) { const { R, f } = k; k.room(PX.cream, PX.gray); R(8, 6, 40, 22, PX.ink); R(10, 8, 36, 18, PX.deep); for (let i = 0; i < 34; i++) { const p = (i + f) % 12; R(11 + i, 17 + (p === 0 ? -5 : p === 1 ? 4 : 0), 1, 1, PX.mint); } k.person(64, 19, PX.mint); R(64, 23, 4, 2, PX.red); k.person(92, 19, PX.cream, { hair: PX.gray }); R(68, 13, 3, 3, PX.red); },
  abroad(k) { const { R, f } = k; R(0, 0, 120, 40, PX.blue); R(0, 26, 120, 14, PX.mint); for (let i = 0; i < 4; i++) { const x = (i * 40 - f * 2) % 150 + 130; R(x % 150 - 20, 6 + i * 5, 18, 3, PX.cream); R(x % 150 - 16, 4 + i * 5, 10, 2, PX.cream); } const y = 14 + Math.round(Math.sin(f * 0.3) * 2); R(46, y, 28, 5, PX.cream); R(70, y + 1, 7, 3, PX.gray); R(54, y - 4, 7, 4, PX.coral); R(56, y + 5, 10, 3, PX.gray); R(46, y - 4, 4, 4, PX.coral); },
  leave(k) { const { R } = k; R(0, 0, 120, 40, PX.deep); k.beam(44, 44, PX.cream, 0, 28, 2, 8); k.beam(72, 72, PX.gold, 0, 28, 2, 8); R(28, 28, 62, 3, PX.wood); k.person(42, 17, PX.coral, { mic: true }); k.person(70, 17, PX.mint, { hair: PX.wine, guitar: true, ph: 3 }); k.notes(58, 16, 12, PX.gold); R(0, 34, 120, 6, PX.ink); },
  contract(k) { const { R, f } = k; k.room(PX.wall, PX.wood2); R(0, 24, 120, 16, PX.wood); R(40, 8, 40, 26, PX.cream); for (let i = 0; i < 5; i++) R(44, 12 + i * 3, 30, 1, PX.gray); const x = 48 + (f % 16); R(x, 29, 12, 1, PX.ink); R(x + 12, 24, 2, 6, PX.red); R(x + 13, 22, 2, 3, PX.cream); k.person(14, 13, PX.gray, { hair: PX.ink, still: true }); k.person(100, 13, PX.mint); },
  rookie(k) { const { R, f } = k; k.room(PX.plum, PX.wood2); R(24, 24, 72, 3, PX.wood); R(38, 8, 44, 17, PX.ink); R(40, 10, 40, 13, PX.deep); k.eq(42, 22, 18, 10, PX.mint); R(34, 25, 52, 2, PX.gray); k.person(100, 18, PX.coral, { hair: PX.gold }); if (f % 8 < 4) { R(16, 8, 12, 8, PX.cream); R(16, 8, 12, 2, PX.gold); } },
  variety(k) { const { R, f } = k; R(0, 0, 120, 40, PX.plum); for (let i = 0; i < 12; i++) R(i * 10 + 2, 2, 6, 3, (f + i) % 3 ? PX.gold : PX.coral); R(10, 8, 100, 20, PX.wine); k.person(26, 17, PX.coral); k.person(44, 17, PX.mint, { ph: 2 }); k.person(62, 17, PX.gold, { ph: 4 }); k.person(80, 17, PX.blue, { ph: 1 }); R(0, 28, 120, 12, PX.ink); k.confetti(12); },
  burn(k) { const { R } = k; k.room(PX.deep, PX.ink); R(70, 4, 34, 22, PX.wood2); R(72, 6, 30, 18, PX.night); k.rain(0, PX.blue); for (let i = 0; i < 14; i++) R(73 + (i * 7) % 28, 7 + (i * 5 + k.f * 2) % 16, 1, 2, PX.blue); R(10, 22, 50, 10, PX.gray); R(10, 25, 50, 7, PX.teal); R(14, 19, 8, 6, PX.skin); R(14, 19, 8, 3, PX.hair); },
  debt(k) { const { R, f } = k; k.room(PX.wall, PX.gray); R(84, 4, 26, 30, PX.wood2); R(106, 18, 2, 3, PX.gold); for (let i = 0; i < 6; i++) { const y = 30 - i * 3 - (i === 5 ? (f % 6 < 3 ? 1 : 0) : 0); R(58 + (i * 5) % 8, y, 14, 3, i % 2 ? PX.cream : PX.coral); } k.person(26, 19, PX.mint); R(32, 23, 8, 5, PX.coral); }
};
const END_ART = {
  "글로벌 차트 1위"(k) { const { R, W, H } = k; R(0, 0, W, H, PX.deep); k.stars(18, 26); R(26, 5, 44, 22, PX.ink); R(27, 6, 42, 20, k.f % 6 < 3 ? PX.wine : PX.plum); R(45, 8, 6, 15, PX.gold); R(43, 10, 2, 2, PX.gold); R(42, 21, 12, 3, PX.gold); k.beam(8 + k.wave(0.4) * 8, 46 + k.wave(0.3) * 10, PX.gold); k.beam(88 - k.wave(0.4) * 8, 50 - k.wave(0.3) * 10, PX.coral); k.beam(48, 48, PX.cream); R(10, 42, 76, 4, PX.teal); R(10, 46, 76, 2, PX.gray); k.person(46, 30, PX.coral, { mic: true, hair: PX.gold }); k.crowd(55, 22, PX.ink); k.confetti(40); },
  "차트의 스타"(k) { const { R, W, H, f } = k; R(0, 0, W, H, PX.plum); R(0, 26, W, 34, PX.night); k.stars(26, 24); k.city(26, 34); R(35, 8, 28, 28, PX.ink); R(36, 9, 26, 26, f % 8 < 4 ? PX.coral : PX.pink); R(36, 27, 26, 8, PX.red); R(44, 14, 10, 10, PX.skin); R(44, 13, 10, 4, PX.hair); R(46, 18, 2, f % 12 < 11 ? 2 : 1, PX.ink); R(50, 18, 2, f % 12 < 11 ? 2 : 1, PX.ink); R(47, 21, 4, 1, PX.red); R(41, 24, 16, 11, PX.cream); R(47, 36, 4, 8, PX.gray); R(0, 50, W, 10, PX.ink); R(0, 50, W, 1, PX.teal); for (let i = 0; i < 16; i++) k.person(2 + i * 6, 44 + (i % 2), [PX.mint, PX.gold, PX.coral, PX.blue][i % 4], { hair: PX.ink, ph: i * 1.3 }); [[8, 6], [84, 8], [24, 4], [72, 5]].forEach((p, i) => { if (k.wave(0.6, i * 2) > -0.3) { R(p[0], p[1] - 2, 1, 5, PX.gold); R(p[0] - 2, p[1], 5, 1, PX.gold); } }); },
  "오래 듣는 가수"(k) { const { R, W, f } = k; R(0, 0, W, 60, PX.wine); R(62, 6, 26, 22, PX.wood2); R(64, 8, 22, 18, PX.night); [[67, 11], [81, 14], [70, 18], [83, 21]].forEach((p, i) => { if (k.wave(0.5, i) > -0.4) R(p[0], p[1], 1, 1, PX.cream); }); R(78, 11, 4, 4, PX.sun); R(74, 8, 1, 18, PX.wood2); R(64, 16, 22, 1, PX.wood2); R(0, 42, W, 18, PX.wood); for (let x = 0; x < W; x += 12) R(x, 42, 1, 18, PX.wood2); R(0, 42, W, 2, PX.wood2); R(14, 30, 42, 14, PX.wood2); R(16, 32, 38, 10, PX.wood); const cx = 32, cy = 28; for (let y = -7; y <= 7; y++) for (let x = -11; x <= 11; x++) { const d = (x * x) / 121 + (y * y) / 49; if (d <= 1) R(cx + x, cy + y, 1, 1, d < 0.12 ? PX.coral : ((Math.round(d * 6) + (x + y + f) % 2) % 2 ? PX.ink : PX.deep)); } R(31 + [1, 0, -1, 0][f % 4] * 7, 28 + [0, 1, 0, -1][f % 4] * 4, 2, 1, PX.gray); R(48, 21, 2, 8, PX.gray); R(40, 28, 9, 1, PX.gray); R(39, 28, 2, 2, PX.cream); k.notes(20, 22, 16, PX.gold); k.notes(30, 20, 16, PX.mint, 5); k.notes(42, 22, 16, PX.gold, 9); k.notes(52, 20, 16, PX.coral, 13); k.person(64, 33, PX.mint); R(70, 37, 7, 7, PX.wood2); R(68, 44, 11, 2, PX.wood2); },
  "톱 100의 뮤지션"(k) { const { R, W, H } = k; R(0, 0, W, H, PX.night); k.stars(14, 20, PX.teal); [[10, 22], [20, 30], [30, 18], [40, 26]].forEach((b, i) => { const h = b[1] + Math.round(k.wave(0.5, i) * 2); R(b[0], 40 - h, 8, h, PX.teal); R(b[0], 40 - h, 8, 1, PX.mint); }); const g = 30 + Math.round(k.wave(0.5, 2) * 2); R(52, 40 - g, 8, g, PX.gold); R(52, 40 - g, 8, 2, PX.sun); R(8, 40, 56, 1, PX.gray); R(78, 8, 2, 7, PX.gold); k.beam(79, 79 + k.wave(0.4) * 3, PX.cream, 8, 44, 2, 12); R(62, 44, 32, 4, PX.wood); R(62, 48, 32, 12, PX.wood2); k.person(76, 33, PX.coral, { mic: true }); R(0, 48, 62, 12, PX.deep); k.crowd(56, 11, PX.ink); },
  "동료들의 가수"(k) { const { R, W, H } = k; R(0, 0, W, H, PX.deep); R(0, 28, W, 14, PX.plum); k.stars(40, 26); for (let y = -7; y <= 7; y++) for (let x = -7; x <= 7; x++) if (x * x + y * y <= 49 && (x - 3) * (x - 3) + (y + 2) * (y + 2) > 30) R(74 + x, 12 + y, 1, 1, PX.sun); k.city(32, 12); R(0, 44, W, 4, PX.gray); R(0, 48, W, 12, PX.teal); R(0, 44, W, 1, PX.cream); k.person(28, 33, PX.coral, { guitar: true }); k.person(42, 33, PX.mint, { hair: PX.wine, ph: 2 }); k.person(54, 33, PX.gold, { hair: PX.blue, ph: 4 }); k.notes(48, 30, 16, PX.cream); k.notes(35, 30, 16, PX.gold, 8); },
  "골목의 음악가"(k) { const { R, W, f } = k; R(0, 0, W, 60, PX.night); k.stars(16, 12); R(0, 8, 24, 44, PX.brick); R(72, 4, 24, 48, PX.brick); for (let y = 10; y < 52; y += 4) for (let x = (y % 8 ? 0 : 3); x < 24; x += 6) { R(x, y, 5, 1, PX.brick2); R(72 + x, y, 5, 1, PX.brick2); } R(5, 16, 9, 10, PX.deep); R(6, 17, 7, 8, f % 16 < 13 ? PX.gold : PX.deep); R(80, 14, 9, 10, PX.deep); R(81, 15, 7, 8, PX.teal); R(0, 52, W, 8, PX.gray); for (let x = 0; x < W; x += 8) R(x, 54, 5, 1, PX.teal); R(62, 14, 2, 38, PX.ink); R(54, 13, 9, 2, PX.ink); R(53, 15, 4, 2, PX.sun); if (f % 18 !== 0) k.beam(55, 55, PX.sun, 17, 52, 2, 17); k.person(46, 41, PX.coral, { guitar: true }); R(34, 49, 9, 3, PX.wood2); R(35, 49, 7, 1, PX.wine); R(37, 49, 1, 1, PX.gold); R(40, 49, 1, 1, PX.gold); R(26, 47, 5, 4, PX.ink); R(26, 45, 3, 3, PX.ink); R(26, 44, 1, 1, PX.ink); R(28, 44, 1, 1, PX.ink); R(31, 45 - (f % 6 < 3 ? 1 : 0), 1, 3, PX.ink); k.notes(58, 40, 14, PX.cream); },
  "다시 시작하는 사람"(k) { const { R, W, H, f } = k; [PX.plum, PX.wine, PX.pink, PX.coral, PX.peach, PX.sun].forEach((c, i) => R(0, i * 6, W, 6, c)); const up = Math.round((Math.sin(f * 0.15) + 1)); for (let y = -11; y <= 0; y++) for (let x = -11; x <= 11; x++) if (x * x + y * y <= 121) R(48 + x, 36 - up + y, 1, 1, PX.cream); [[0, 34, 26, 6], [20, 36, 22, 4], [64, 35, 32, 5]].forEach(b => R(b[0], b[1], b[2], b[3], PX.wine)); R(0, 36, W, 24, PX.teal); for (let y = 36; y < H; y++) { const t = (y - 36) / 24, w = 3 + t * 26; R(48 - w, y, w * 2, 1, PX.gray); if ((y + f) % 5 < 2) R(47, y, 2, 1, PX.cream); } k.person(52, 41, PX.mint); R(49, 45, 3, 9, PX.wood2); R(50, 42, 1, 3, PX.wood2); [[12, 40], [18, 46], [76, 42], [84, 50], [8, 54]].forEach((p, i) => { R(p[0] + (k.wave(0.5, i) > 0 ? 1 : 0), p[1], 1, 3, PX.mint); R(p[0] + 2, p[1] + 1, 1, 2, PX.mint); }); }
};
function drawPixel(cv, key, f) {
  const fn = SCENE_ART[key] || END_ART[key]; if (!fn) return;
  fn(kit(cv, f, key.length * 7 + key.charCodeAt(0) % 97));
}

/* 새 장면 그림 (120×40). art2.js의 kit을 그대로 쓴다. */
Object.assign(SCENE_ART, {
  cover(k) { const { R, f } = k; k.room(PX.plum, PX.wood2); R(62, 5, 34, 21, PX.ink); R(64, 7, 30, 17, PX.blue); k.person(76, 11, PX.coral, { still: true }); R(70, 22, 18, 1, PX.gold); R(10, 23, 34, 8, PX.wood); k.person(22, 16, PX.mint, { guitar: true }); R(50, 14, 2, 17, PX.gray); R(47, 12, 8, 4, PX.ink); if (f % 6 < 3) R(49, 13, 1, 1, PX.red); [0, 1, 2].forEach(i => { const y = 22 - ((f + i * 5) % 16); R(100 + i * 5, y, 3, 3, PX.gold); }); },
  audition(k) { const { R, f } = k; k.room(PX.deep, PX.wood2); k.beam(30, 30, PX.gold, 0, 30, 2, 9); R(16, 29, 30, 2, PX.wood); k.person(28, 18, PX.coral, { mic: true }); R(62, 22, 52, 9, PX.ink); [68, 84, 100].forEach((x, i) => { k.person(x, 12, [PX.gray, PX.blue, PX.wine][i], { still: i !== 1, hair: PX.ink }); }); R(62, 22, 52, 1, PX.gold); R(30, 24, 7, 4, PX.cream); R(32, 25, 3, 1, PX.ink); if (f % 8 < 4) k.heart(90, 4, PX.coral); },
  eval(k) { const { R, f } = k; k.room(PX.wall, PX.wood); R(0, 2, 120, 22, PX.blue); for (let x = 4; x < 116; x += 28) R(x, 4, 24, 18, PX.teal); k.person(26, 19, PX.mint, { mic: true }); R(60, 22, 50, 9, PX.wood2); k.person(68, 12, PX.gray, { hair: PX.ink, still: true }); k.person(88, 12, PX.gold, { hair: PX.wine, still: true }); R(76, 18, 8, 4, PX.cream); R(77, 19, 2 + (f % 5), 1, PX.red); k.notes(40, 20, 12, PX.gold); },
  senior(k) { const { R, f } = k; k.room(PX.plum, PX.wood2); R(8, 6, 44, 20, PX.ink); R(10, 8, 40, 16, PX.deep); [PX.coral, PX.gold, PX.mint, PX.blue].forEach((c, i) => { R(13, 10 + i * 3, 4, 2, c); R(19, 10 + i * 3, 20 + ((f + i * 3) % 6), 2, i === (f >> 2) % 4 ? PX.cream : PX.gray); }); k.person(64, 19, PX.mint, { ph: 1 }); k.person(82, 19, PX.gray, { hair: PX.ink, ph: 3 }); R(78, 16, 3, 3, PX.ink); k.notes(100, 22, 14, PX.gold); k.notes(108, 22, 14, PX.coral, 6); },
  debutdemo(k) { const { R } = k; k.room(PX.wall, PX.gray); [14, 50, 86].forEach((x, i) => { R(x, 5, 22, 18, PX.ink); R(x + 2, 7, 18, 14, [PX.coral, PX.gold, PX.mint][i]); R(x + 6, 10, 10, 8, PX.ink); R(x + 9, 13, 4, 2, PX.cream); }); for (let i = 0; i < 9; i++) k.person(8 + i * 12, 27, [PX.gray, PX.blue, PX.teal][i % 3], { ph: i * 2 }); k.eq(44, 4, 0, 1, PX.gold); },
  debutfeat(k) { const { R } = k; R(0, 0, 120, 40, PX.deep); k.stars(10, 16); k.beam(38, 38, PX.gold, 0, 30, 2, 10); k.beam(78, 78, PX.cream, 0, 30, 2, 7); R(18, 29, 84, 3, PX.wood); k.person(36, 18, PX.gold, { mic: true, hair: PX.ink }); k.person(76, 18, PX.mint, { mic: true }); R(30, 6, 18, 5, PX.gold); R(68, 7, 14, 3, PX.gray); k.notes(58, 18, 12, PX.cream); k.crowd(38, 18, PX.ink); },
  drama(k) { const { R, f } = k; R(0, 0, 120, 40, PX.night); k.city(24, 16); R(30, 3, 60, 28, PX.ink); R(32, 5, 56, 24, f % 16 < 8 ? PX.wine : PX.plum); k.rain(16, PX.blue); k.person(50, 15, PX.mint, { still: true }); k.person(62, 15, PX.coral, { still: true, hair: PX.wine }); R(32, 25, 56, 4, PX.ink); R(36, 26, (f * 3) % 48, 2, PX.gold); R(52, 31, 16, 2, PX.gray); },
  banner(k) { const { R, f } = k; R(0, 0, 120, 40, PX.deep); R(40, 1, 40, 38, PX.ink); R(42, 3, 36, 34, PX.night); const u = f % 24 < 16 ? 0 : (f % 24 - 16); R(44, 5 - u, 32, 14, PX.gold); R(47, 8 - u, 10, 8, PX.coral); R(60, 9 - u, 13, 2, PX.ink); R(60, 13 - u, 9, 2, PX.ink); for (let i = 0; i < 4; i++) { R(44, 21 + i * 4, 6, 3, PX.teal); R(52, 22 + i * 4, 20 - i * 3, 1, PX.gray); } [10, 22, 96, 108].forEach((x, i) => { const n = 8 + Math.round((Math.sin(f * 0.5 + i) + 1) * 8); R(x, 36 - n, 6, n, i % 2 ? PX.coral : PX.mint); }); },
  youtuber(k) { const { R, f } = k; k.room(PX.wine, PX.wood2); R(10, 5, 42, 24, PX.ink); R(12, 7, 38, 20, PX.coral); R(26, 12, 2, 10, PX.cream); R(28, 13, 2, 8, PX.cream); R(30, 14, 2, 6, PX.cream); R(32, 16, 2, 2, PX.cream); k.person(68, 19, PX.gold, { hair: PX.pink }); R(76, 16, 8, 6, PX.ink); R(78, 18, 3, 2, f % 4 < 2 ? PX.red : PX.gray); [0, 1, 2].forEach(i => { if ((f + i * 4) % 12 > 3) k.speech(92, 4 + i * 11, 18, i === 1 ? PX.gold : PX.cream, PX.gray); }); },
  search(k) { const { R, f } = k; R(0, 0, 120, 40, PX.deep); R(4, 6, 54, 28, PX.ink); R(6, 8, 50, 8, PX.cream); R(9, 11, 2 + (f % 8) * 3, 2, PX.gray); R(50, 10, 3, 3, PX.teal); k.person(24, 21, PX.mint, { still: true }); R(62, 2, 54, 36, PX.ink); for (let i = 0; i < 5; i++) { R(66, 5 + i * 7, 5, 5, [PX.coral, PX.gold, PX.mint, PX.pink, PX.blue][i]); R(73, 6 + i * 7, 22 + (i * 7) % 16, 1, PX.gray); } for (let i = 0; i < 4; i++) k.person(98 + (i % 2) * 8, 6 + i * 7, PX.teal, { hair: PX.ink, ph: i * 2 }); },
  chartout(k) { const { R, f } = k; R(0, 0, 120, 40, PX.night); k.stars(12, 10); R(8, 4, 20, 34, PX.gold); R(30, 12, 14, 26, PX.teal); for (let i = 0; i < 34; i++) { const h = 3 + (i * 7) % 4; R(46 + i * 2, 38 - h, 1, h, PX.gray); } const x = 46 + ((f >> 1) % 34) * 2; R(x, 28, 1, 10, PX.mint); k.note(x - 1, 26, PX.mint); },
  month(k) { const { R, f } = k; k.room(PX.wall, PX.wood2); R(10, 3, 40, 26, PX.cream); R(10, 3, 40, 5, PX.coral); for (let y = 0; y < 3; y++) for (let x = 0; x < 6; x++) { R(13 + x * 6, 11 + y * 6, 4, 4, (x + y * 6) <= (f >> 1) % 18 ? PX.teal : PX.gray); } for (let i = 0; i < 10; i++) k.person(60 + (i % 5) * 11, 6 + (i >> 1 > 1 ? 13 : 0) - (i > 4 ? 2 : 0), i < 4 ? PX.mint : PX.ink, { still: true, hair: i < 4 ? PX.hair : PX.ink }); },
  letter(k) { const { R, f } = k; k.room(PX.plum, PX.wood); R(0, 26, 120, 14, PX.wood2); R(36, 8, 46, 24, PX.cream); for (let i = 0; i < 5; i++) R(41, 13 + i * 3, 34 - i * 3, 1, PX.gray); k.heart(70, 25, PX.coral); R(88, 14, 16, 12, PX.gold); R(88, 14, 16, 2, PX.coral); k.person(16, 15, PX.mint); if (f % 8 < 5) R(30, 8, 2, 2, PX.gold); },
  samefans(k) { const { R } = k; R(0, 0, 120, 40, PX.deep); R(30, 2, 60, 12, PX.plum); k.beam(60, 60, PX.gold, 0, 16, 2, 8); R(36, 12, 48, 2, PX.wood); k.person(58, 2, PX.coral, { mic: true }); for (let i = 0; i < 6; i++) k.person(30 + i * 11, 17, PX.mint, { ph: i * 1.5, hair: PX.wine }); for (let y = 29; y < 40; y += 5) for (let x = 6; x < 116; x += 9) R(x, y, 6, 3, PX.teal); },
  oldfans(k) { const { R, f } = k; k.room(PX.wall, PX.wood2); R(38, 2, 44, 32, PX.ink); R(40, 4, 40, 28, PX.cream); [PX.coral, PX.gold, PX.mint, PX.blue, PX.pink].forEach((c, i) => { R(44, 7 + i * 5, 5, 3, c); R(52, 8 + i * 5, 12 + (i * 5) % 12, 1, PX.gray); }); const y = 7 + ((f >> 1) % 5) * 5; R(42, y - 1, 36, 5, PX.gold); k.c.globalAlpha = 1; [PX.coral, PX.gold, PX.mint, PX.blue, PX.pink].forEach((c, i) => R(44, 7 + i * 5, 5, 3, c)); k.person(14, 20, PX.gray, { hair: PX.gray }); k.person(98, 20, PX.mint); },
  collab(k) { const { R, f } = k; R(0, 0, 60, 40, PX.wine); R(60, 0, 60, 40, PX.teal); k.eq(6, 34, 22, 20, PX.coral); k.eq(70, 34, 22, 20, PX.mint); k.person(38, 20, PX.gold, { hair: PX.ink }); k.person(72, 20, PX.cream, { hair: PX.blue, ph: 3 }); const s = (f % 8) < 4 ? 1 : 0; R(47 + s, 24, 10, 2, PX.skin); R(63 - s, 24, 10, 2, PX.skin); k.notes(58, 16, 12, PX.gold); },
  divscore(k) { const { R, f } = k; R(0, 0, 120, 40, PX.deep); R(6, 3, 48, 34, PX.ink); for (let i = 0; i < 6; i++) { const on = (f + i * 3) % 9 < 5; R(10, 6 + i * 5, 40, 3, on ? [PX.coral, PX.gold, PX.mint, PX.pink, PX.blue, PX.cream][(i + (f >> 2)) % 6] : PX.teal); } R(64, 6, 50, 8, PX.ink); const n = 12 + (f * 3) % 34; R(66, 8, n, 4, PX.gold); R(64, 20, 50, 8, PX.ink); R(66, 22, 8, 4, PX.mint); k.person(86, 29 - 18, PX.gray, { hair: PX.ink, still: true }); },
  mini(k) { const { R, f } = k; R(0, 0, 120, 40, PX.plum); R(0, 30, 120, 10, PX.wood2); [10, 32, 54, 76, 98].forEach((x, i) => { const y = 8 + (i === (f >> 2) % 5 ? -2 : 0); R(x, y, 18, 18, i === 3 ? PX.coral : PX.ink); R(x + 3, y + 3, 12, 12, i === 3 ? PX.gold : PX.teal); R(x + 7, y + 7, 4, 4, PX.cream); R(x + 7, 28, 4, 2, PX.gray); }); },
  strength(k) { const { R, f } = k; k.room(PX.wall, PX.gray); R(14, 8, 92, 16, PX.ink); R(18, 12, 84, 8, PX.deep); const t = (Math.sin(f * 0.3) + 1) / 2, x = 22 + t * 70; for (let i = 0; i < 10; i++) R(22 + i * 8, 15, 5, 2, i < 3 ? PX.mint : i < 7 ? PX.gold : PX.red); R(x, 10, 4, 12, PX.cream); k.person(34, 27 - 8, PX.mint, { still: true }); k.person(78, 27 - 8, PX.gray, { hair: PX.ink }); },
  fantype(k) { const { R } = k; R(0, 0, 120, 40, PX.deep); R(58, 0, 4, 40, PX.ink); R(0, 0, 58, 16, PX.plum); R(62, 0, 58, 16, PX.teal); k.beam(28, 28, PX.coral, 0, 18, 2, 8); k.beam(90, 90, PX.gold, 0, 18, 2, 8); k.person(26, 6, PX.coral, { mic: true }); k.person(88, 6, PX.gold, { mic: true }); k.crowd(36, 9, PX.mint); },
  unknown(k) { const { R, f } = k; k.room(PX.wall, PX.wood); R(8, 4, 58, 22, PX.cream); [[12, PX.mint], [30, PX.gold], [48, PX.coral]].forEach(p => { R(p[0], 8, 14, 14, p[1]); }); const n = f % 4; R(12 + (n % 3) * 18 + 5, 11, 4, 2, PX.ink); R(12 + (n % 3) * 18 + 8, 13, 2, 2, PX.ink); R(12 + (n % 3) * 18 + 6, 15, 2, 2, PX.ink); R(12 + (n % 3) * 18 + 6, 18, 2, 2, PX.ink); for (let i = 0; i < 4; i++) { k.person(74 + i * 11, 19, PX.gray, { hair: PX.gray, ph: i }); R(75 + i * 11, 15, 2, 2, PX.cream); } },
  newbie(k) { const { R, f } = k; k.room(PX.plum, PX.wood2); R(8, 3, 42, 26, PX.ink); for (let i = 0; i < 5; i++) { R(12, 6 + i * 4, 4, 3, i < 2 ? PX.gold : PX.teal); R(18, 7 + i * 4, i < 2 ? 26 : 16 - i, 1, PX.gray); } R(12, 26, 34, 2, f % 6 < 3 ? PX.wine : PX.ink); k.person(66, 19, PX.coral); k.person(84, 19, PX.mint, { hair: PX.gold, ph: 2 }); R(92, 22, 6, 7, PX.wood); k.notes(100, 18, 12, PX.cream); },
  mission(k) { const { R, f } = k; R(0, 0, 120, 40, PX.teal); R(38, 2, 44, 36, PX.ink); R(40, 4, 40, 32, PX.cream); for (let i = 0; i < 4; i++) { const d = i <= (f >> 2) % 5; R(44, 8 + i * 7, 5, 5, d ? PX.mint : PX.gray); if (d) R(45, 10 + i * 7, 3, 1, PX.ink); R(52, 10 + i * 7, 22, 1, PX.gray); } [12, 24, 92, 104].forEach((x, i) => { R(x, 26 - ((f + i * 3) % 6), 8, 8, i % 2 ? PX.gold : PX.coral); R(x + 3, 26 - ((f + i * 3) % 6), 2, 8, PX.cream); }); },
  smallapp(k) { const { R, f } = k; R(0, 0, 120, 40, PX.night); k.stars(10, 18); R(4, 6, 40, 34, PX.ink); R(8, 10, 32, 26, PX.gray); k.city(30, 10); R(64, 16, 22, 24, PX.ink); R(66, 18, 18, 20, PX.mint); R(70, 22, 10, 10, PX.ink); R(73, 25, 4, 4, f % 6 < 3 ? PX.gold : PX.cream); k.person(92, 25, PX.coral, { guitar: true }); k.notes(102, 24, 12, PX.gold); },
  h4(k) { const { R, f } = k; k.room(PX.wall, PX.wood2); R(8, 3, 50, 30, PX.cream); R(14, 25, 12, 4, PX.gray); R(30, 8, 12, 21, PX.coral); R(12, 29, 34, 1, PX.ink); const big = f % 16 < 8; R(70, 3, 44, 30, PX.ink); R(74, 25, 12, 4, PX.mint); R(92, big ? 22 : 24, 12, big ? 7 : 5, PX.mint); R(72, 29, 34, 1, PX.gray); k.person(58, 22, PX.mint, { still: true }); },
  predict(k) { const { R, f } = k; R(0, 0, 120, 40, PX.deep); R(10, 4, 100, 32, PX.ink); R(14, 30, 92, 1, PX.gray); for (let i = 0; i < 18; i++) { const h = 6 + Math.round((Math.sin(i * 0.5) + 1) * 8); R(16 + i * 5, 30 - h, 2, h, PX.teal); const p = h + (i % 2); R(17 + i * 5 + 1, 30 - p, 2, 1, PX.gold); } const x = 16 + ((f >> 1) % 18) * 5; R(x, 8, 1, 22, PX.coral); },
  title(k) { const { R, f } = k; R(0, 0, 120, 40, PX.deep); k.stars(14, 14); R(14, 22, 92, 18, PX.wood2); for (let i = 0; i < 40; i++) R(16 + i * 2, 25 + (i % 3) * 3, 1, 1, f % 8 < 4 ? PX.gold : PX.cream); k.person(56, 9, PX.coral, { mic: true }); R(40, 21, 40, 2, PX.wood); k.beam(58, 58, PX.gold, 0, 22, 2, 10); k.notes(30, 20, 14, PX.gold); k.notes(90, 20, 14, PX.mint, 7); },
  formula(k) { const { R, f } = k; k.room(PX.wall, PX.wood2); R(6, 4, 52, 24, PX.teal); for (let i = 0; i < 4; i++) R(10, 8 + i * 5, 40 - i * 6, 1, PX.cream); R(66, 8, 46, 22, PX.ink); const pts = [4, 6, 8, 11, 14, 17]; pts.forEach((p, i) => { R(70 + i * 7, 10 + p, 5, 18 - p, i < 3 ? PX.mint : PX.coral); }); R(30, 2, 4, 2, f % 4 < 2 ? PX.gold : PX.cream); k.person(30, 26 - 7, PX.mint, { still: true }); },
  keepsong(k) { const { R, f } = k; R(0, 0, 120, 40, PX.wine); R(0, 28, 120, 12, PX.wood); for (let i = 0; i < 6; i++) { const on = (f >> 2) % 7 > i; R(8 + i * 18, 6, 14, 14, on ? PX.gold : PX.plum); R(13 + i * 18, 11, 4, 4, PX.ink); } k.person(54, 17, PX.coral, { guitar: true }); k.notes(70, 18, 12, PX.gold); },
  twocity(k) { const { R } = k; R(0, 0, 120, 40, PX.night); R(58, 0, 4, 40, PX.ink); k.stars(12, 14); k.city(14, 16); R(0, 30, 120, 10, PX.deep); R(14, 26, 30, 3, PX.wood); R(76, 26, 30, 3, PX.wood); k.person(28, 15, PX.coral, { mic: true }); k.person(90, 15, PX.mint, { mic: true }); k.crowd(38, 18, PX.teal); },
  goalpost(k) { const { R, f } = k; k.room(PX.wall, PX.wood2); R(14, 4, 58, 26, PX.cream); R(20, 24, 46, 1, PX.gray); R(26, 15, 10, 9, PX.teal); R(44, 13, 10, 11, PX.teal); const y = f % 16 < 8 ? 8 : 18; R(20, y, 46, 1, PX.red); R(62, y - 1, 6, 3, PX.red); k.person(84, 19, PX.gray, { hair: PX.ink }); k.person(100, 19, PX.mint); },
  holdout(k) { const { R, f } = k; k.room(PX.plum, PX.wood2); for (let i = 0; i < 5; i++) k.person(8 + i * 9, 20, PX.mint, { ph: i, hair: PX.wine }); k.speech(10, 3, 34, f % 8 < 4 ? PX.gold : PX.cream, PX.gray); R(56, 2, 4, 32, PX.ink); for (let i = 0; i < 5; i++) k.person(66 + i * 10, 20, [PX.coral, PX.gold, PX.blue, PX.pink, PX.gray][i], { ph: i * 2, hair: PX.ink }); if (f % 12 > 5) k.speech(78, 3, 22, PX.cream, PX.red); },
  archive(k) { const { R, f } = k; R(0, 0, 120, 40, PX.deep); k.stars(12, 12); for (let i = 0; i < 14; i++) { const h = 8 + (i * 7) % 18; R(8 + i * 8, 36 - h, 6, h, i === 5 ? PX.gold : PX.teal); R(8 + i * 8, 36 - h, 6, 1, i === 5 ? PX.sun : PX.mint); } R(0, 36, 120, 4, PX.ink); const y = 8 - (f % 4 < 2 ? 1 : 0); k.note(51, y, PX.gold); }
});

/* 프로필 상점: 품목, 움직이는 그림, 저장값. 게임과 사이트 부착 스크립트가 같은 코드를 쓴다. */
const EP_KEY = "ms-encore";
const AVATAR_ART = {
  trainee(k) { const { R, f } = k; R(0, 0, 32, 32, PX.wall); R(0, 26, 32, 6, PX.wood); const y = k.bob(); R(8, 24 + y, 16, 8, PX.mint); R(10, 9 + y, 12, 14, PX.skin); R(9, 7 + y, 14, 6, PX.hair); R(9, 9 + y, 2, 7, PX.hair); R(21, 9 + y, 2, 7, PX.hair); if (f % 16) { R(13, 15 + y, 2, 2, PX.ink); R(18, 15 + y, 2, 2, PX.ink); } R(15, 20 + y, 3, 1, PX.red); },
  headset(k) { const { R, f } = k; R(0, 0, 32, 32, PX.plum); const y = k.bob(); R(8, 24 + y, 16, 8, PX.blue); R(10, 9 + y, 12, 14, PX.skin); R(9, 7 + y, 14, 5, PX.wine); R(8, 6 + y, 16, 2, PX.gold); R(6, 12 + y, 4, 8, PX.gold); R(22, 12 + y, 4, 8, PX.gold); if (f % 12 < 8) { R(13, 16 + y, 2, 1, PX.ink); R(18, 16 + y, 2, 1, PX.ink); } else { R(13, 15 + y, 2, 2, PX.ink); R(18, 15 + y, 2, 2, PX.ink); } R(14, 20 + y, 4, 1, PX.red); k.notes(2, 26, 18, PX.mint); k.notes(26, 26, 18, PX.gold, 9); },
  guitar(k) { const { R, f } = k; R(0, 0, 32, 32, PX.night); k.stars(8, 12); R(9, 20, 14, 12, PX.coral); R(11, 6, 10, 12, PX.skin); R(10, 4, 12, 5, PX.hair); R(13, 11, 2, 2, PX.ink); R(18, 11, 2, 2, PX.ink); R(14, 15, 4, 1, PX.red); R(5, 23, 12, 7, PX.wood); R(7, 25, 3, 3, PX.ink); R(17, 25, 14, 2, PX.wood2); R(11 + (f % 2) * 2, 21 + (f % 2), 2, 4, PX.skin); k.notes(26, 18, 14, PX.gold); },
  cat(k) { const { R, f } = k; R(0, 0, 32, 32, PX.deep); k.stars(10, 14); R(0, 27, 32, 5, PX.gray); R(22, 2, 5, 5, PX.sun); R(9, 13, 14, 15, PX.ink); R(9, 9, 4, 5, PX.ink); R(19, 9, 4, 5, PX.ink); if (f % 18 > 1) { R(12, 17, 2, 2, PX.gold); R(18, 17, 2, 2, PX.gold); } R(15, 21, 2, 1, PX.pink); const t = k.wave(0.5) > 0 ? 1 : 0; R(23, 20 - t * 2, 3, 8, PX.ink); R(25, 18 - t * 3, 3, 4, PX.ink); },
  star(k) { const { R, f } = k; R(0, 0, 32, 32, PX.plum); k.beam(8, 16 + k.wave(0.4) * 4, PX.gold, 0, 26, 1, 5); k.beam(24, 16 - k.wave(0.4) * 4, PX.coral, 0, 26, 1, 5); R(9, 23, 14, 9, PX.red); R(11, 9, 10, 12, PX.skin); R(10, 7, 12, 5, PX.gold); R(13, 14, 2, 2, PX.ink); R(18, 14, 2, 2, PX.ink); R(14, 18, 4, 1, PX.red); R(23, 16, 2, 8, PX.gray); R(22, 13, 4, 4, PX.cream); k.confetti(6); },
  mate(k) { const { R, f } = k; R(0, 0, 32, 32, PX.blue); R(0, 0, 32, 4, PX.teal); R(0, 26, 32, 6, PX.wood); const y = k.bob(2); R(8, 24 + y, 16, 8, PX.coral); R(10, 9 + y, 12, 14, PX.skin); R(9, 6 + y, 14, 6, PX.wine); R(8, 8 + y, 3, 14, PX.wine); R(21, 8 + y, 3, 14, PX.wine); if (f % 14) { R(13, 15 + y, 2, 2, PX.ink); R(18, 15 + y, 2, 2, PX.ink); } R(15, 19 + y, 3, 2, f % 10 < 5 ? PX.red : PX.pink); k.notes(27, 20, 14, PX.cream); },
  dj(k) { const { R, f } = k; R(0, 0, 32, 32, PX.deep); R(3, 3, 26, 6, f % 8 < 4 ? PX.red : PX.wine); R(6, 5, 20, 2, PX.cream); R(8, 22, 16, 10, PX.mint); R(10, 10, 12, 12, PX.skin); R(9, 9, 14, 4, PX.hair); R(13, 15, 2, 2, PX.ink); R(18, 15, 2, 2, PX.ink); R(14, 19, 4, 1, PX.red); R(23, 14, 2, 10, PX.gray); R(21, 11, 6, 5, PX.cream); k.eq(3, 31, 3, 7, PX.gold); },
  robot(k) { const { R, f } = k; R(0, 0, 32, 32, PX.teal); R(15, 3, 2, 5, PX.gray); R(14, 2, 4, 3, f % 6 < 3 ? PX.red : PX.gold); R(7, 8, 18, 15, PX.gray); R(9, 10, 14, 11, PX.ink); const e = f % 16 < 13; R(11, 13, 3, e ? 3 : 1, PX.mint); R(18, 13, 3, e ? 3 : 1, PX.mint); for (let i = 0; i < 5; i++) R(11 + i * 2, 18, 1, 1 + ((f + i) % 3 === 0 ? 1 : 0), PX.gold); R(9, 24, 14, 8, PX.gray); R(13, 26, 6, 3, PX.ink); R(14, 27, 1 + (f % 5), 1, PX.mint); },
  tape(k) { const { R, f } = k; R(0, 0, 32, 32, PX.plum); R(3, 7, 26, 18, PX.ink); R(5, 9, 22, 14, PX.cream); R(7, 10, 18, 3, PX.coral); const reel = x => { R(x - 3, 15, 7, 6, PX.ink); const a = f % 4; R(x + [0, 1, 0, -1][a], 17 + [-1, 0, 1, 0][a], 1, 1, PX.cream); R(x, 18, 1, 1, PX.gold); }; reel(11); reel(21); R(14, 19, 4, 1, PX.gold); k.notes(27, 6, 5, PX.gold); },
  vinyl(k) { const { R, f } = k; R(0, 0, 32, 32, PX.wine); for (let y = -13; y <= 13; y++) for (let x = -13; x <= 13; x++) { const d = x * x + y * y; if (d <= 169) R(16 + x, 16 + y, 1, 1, d < 16 ? PX.gold : d < 36 ? PX.coral : ((Math.floor(Math.sqrt(d)) + (x + y + f) % 3) % 3 ? PX.ink : PX.deep)); } const a = f * 0.5; R(16 + Math.round(Math.cos(a) * 10), 16 + Math.round(Math.sin(a) * 10), 2, 2, PX.cream); R(15, 15, 2, 2, PX.ink); }
};
const BADGE_ART = {
  b1(k) { const { R, f } = k; R(7, 3, 10, 10, PX.gold); R(3, 4, 4, 2, PX.gold); R(17, 4, 4, 2, PX.gold); R(3, 4, 2, 5, PX.gold); R(19, 4, 2, 5, PX.gold); R(9 + (f % 8 < 2 ? 3 : 0), 5, 2, 5, PX.cream); R(11, 13, 2, 5, PX.gold); R(7, 18, 10, 3, PX.sun); },
  b2(k) { const { R, f } = k; const w = [10, 7, 3, 7][(f >> 1) % 4]; R(12 - w, 10, w * 2, 4, PX.gold); R(12 - Math.ceil(w / 2), 5, Math.ceil(w / 2) * 2, 15, PX.gold); R(12 - Math.ceil(w / 3), 3, Math.ceil(w / 3) * 2, 18, PX.sun); },
  b3(k) { const { R, f } = k; for (let y = -10; y <= 10; y++) for (let x = -10; x <= 10; x++) { const d = x * x + y * y; if (d <= 100) R(12 + x, 12 + y, 1, 1, d < 9 ? PX.coral : ((x + y + f) % 4 ? PX.ink : PX.gray)); } R(11, 11, 2, 2, PX.cream); },
  b4(k) { [[3, 9], [9, 14], [15, 19]].forEach((b, i) => { const h = b[1] - (k.wave(0.5, i) > 0 ? 1 : 0); k.R(b[0], 21 - h, 5, h, i === 2 ? PX.gold : PX.teal); k.R(b[0], 21 - h, 5, 1, PX.mint); }); k.R(2, 21, 20, 1, PX.gray); },
  b5(k) { const { R, f } = k; k.heart(3 + (f % 6 < 3 ? 1 : 0), 4, PX.coral); k.heart(14, 7 + (f % 6 < 3 ? 0 : 1), PX.pink); R(5, 14, 5, 7, PX.mint); R(6, 12, 3, 3, PX.skin); R(15, 14, 5, 7, PX.gold); R(16, 12, 3, 3, PX.skin); },
  b6(k) { const { R, f } = k; R(15, 3, 2, 19, PX.gray); R(8, 3, 8, 2, PX.gray); R(7, 5, 4, 2, f % 14 ? PX.sun : PX.wood2); if (f % 14) { k.c.globalAlpha = 0.4; R(6, 7, 6, 3, PX.sun); R(4, 10, 10, 4, PX.sun); k.c.globalAlpha = 1; } R(3, 21, 18, 1, PX.gray); },
  b7(k) { const { R } = k; R(2, 15, 20, 7, PX.teal); const u = k.wave(0.25) > 0 ? 1 : 0; for (let y = -7; y <= 0; y++) for (let x = -7; x <= 7; x++) if (x * x + y * y <= 49) R(12 + x, 14 - u + y, 1, 1, PX.sun); R(2, 14, 20, 1, PX.peach); R(11, 16, 2, 2, PX.cream); R(11, 19, 2, 2, PX.cream); },
  replay(k) { const { R, f } = k; for (let i = 0; i < 12; i++) { const a = i / 12 * Math.PI * 2 + f * 0.3; R(11 + Math.round(Math.cos(a) * 8), 11 + Math.round(Math.sin(a) * 8), 2, 2, i < 8 ? PX.mint : PX.teal); } k.note(10, 14, PX.gold); },
  digger(k) { const { R, f } = k; const x = 8 + Math.round(k.wave(0.4) * 3); k.note(x, 14, PX.gold); for (let y = -7; y <= 7; y++) for (let t = -7; t <= 7; t++) { const d = t * t + y * y; if (d <= 49 && d > 30) R(10 + t, 10 + y, 1, 1, PX.cream); } R(15, 15, 2, 2, PX.wood); R(17, 17, 2, 2, PX.wood); R(19, 19, 2, 2, PX.wood); },
  tester(k) { const { R, f } = k; const on = f % 12 < 6; R(2, 5, 9, 14, on ? PX.mint : PX.teal); R(13, 5, 9, 14, on ? PX.teal : PX.coral); R(5, 9, 3, 2, PX.ink); R(5, 12, 3, 2, PX.ink); R(16, 9, 3, 2, PX.ink); R(16, 12, 3, 2, PX.ink); R(11, 3, 2, 18, PX.cream); }
};
const EP_ITEMS = [
  { id: "a_trainee", kind: "avatar", art: "trainee", name: "연습생", price: 0 },
  { id: "a_headset", kind: "avatar", art: "headset", name: "헤드폰 청취자", price: 150 },
  { id: "a_guitar", kind: "avatar", art: "guitar", name: "기타 든 신인", price: 200 },
  { id: "a_cat", kind: "avatar", art: "cat", name: "골목 고양이", price: 600 },
  { id: "a_star", kind: "avatar", art: "star", name: "무대의 주인공", price: 300 },
  { id: "a_vinyl", kind: "avatar", art: "vinyl", name: "돌아가는 레코드", price: 300, need: "replay", lock: "다시 찾는 곡 2개 만들기" },
  { id: "a_mate", kind: "avatar", art: "mate", name: "옆 연습실 동료", price: 170 },
  { id: "a_dj", kind: "avatar", art: "dj", name: "새벽 라디오 진행자", price: 200 },
  { id: "a_robot", kind: "avatar", art: "robot", name: "추천 로봇", price: 250 },
  { id: "a_tape", kind: "avatar", art: "tape", name: "되감는 카세트", price: 300, need: "digger", lock: "묻힌 수록곡을 역주행시키기" },
  { id: "g_street", kind: "bg", art: "street", name: "저녁의 거리", price: 150 },
  { id: "g_radio", kind: "bg", art: "radio", name: "새벽 라디오", price: 150 },
  { id: "g_three", kind: "bg", art: "three", name: "소극장", price: 200 },
  { id: "g_album", kind: "bg", art: "album", name: "녹음실", price: 250 },
  { id: "g_archive", kind: "bg", art: "archive", name: "다시 들린 곡들", price: 300, need: "replay", lock: "다시 찾는 곡 2개 만들기" },
  { id: "g_encore", kind: "bg", art: "encore", name: "앙코르 무대", price: 350, need: "e2", lock: "차트의 스타 이상 달성" },
  { id: "g_start", kind: "bg", art: "start", name: "명함을 받은 밤", price: 150 },
  { id: "g_abroad", kind: "bg", art: "abroad", name: "해외 무대 가는 길", price: 200 },
  { id: "g_collab", kind: "bg", art: "collab", name: "두 장르의 만남", price: 250 },
  { id: "g_lambda", kind: "bg", art: "lambda", name: "바뀐 추천 목록", price: 300, need: "e3", lock: "오래 듣는 가수 결말" },
  { id: "t_b1", kind: "badge", art: "b1", name: "글로벌 차트 1위", price: 300, need: "e1", lock: "글로벌 차트 1위 결말" },
  { id: "t_b2", kind: "badge", art: "b2", name: "차트의 스타", price: 250, need: "e2", lock: "차트의 스타 이상 달성" },
  { id: "t_b3", kind: "badge", art: "b3", name: "오래 듣는 가수", price: 200, need: "e3", lock: "오래 듣는 가수 결말" },
  { id: "t_b4", kind: "badge", art: "b4", name: "톱 100의 뮤지션", price: 150, need: "e4", lock: "톱 100의 뮤지션 결말" },
  { id: "t_b5", kind: "badge", art: "b5", name: "동료들의 가수", price: 150, need: "e5", lock: "동료들의 가수 결말" },
  { id: "t_b6", kind: "badge", art: "b6", name: "골목의 음악가", price: 150, need: "e6", lock: "골목의 음악가 결말" },
  { id: "t_b7", kind: "badge", art: "b7", name: "다시 시작하는 사람", price: 100, need: "e7", lock: "다시 시작하는 사람 결말" },
  { id: "t_replay", kind: "badge", art: "replay", name: "다시 듣게 만드는 사람", price: 200, need: "replay", lock: "다시 찾는 곡 2개 만들기" },
  { id: "t_digger", kind: "badge", art: "digger", name: "숨은 곡 발굴가", price: 200, need: "digger", lock: "묻힌 수록곡을 역주행시키기" },
  { id: "t_tester", kind: "badge", art: "tester", name: "먼저 들려주는 사람", price: 200, need: "tester", lock: "곡을 먼저 시험하고 내기" }
];
const EP_UNLOCKS = ["e1", "e2", "e3", "e4", "e5", "e6", "e7", "replay", "digger", "tester"];
const epItem = id => EP_ITEMS.find(x => x.id === id) || null;
function epBlank() { return { v: 1, coins: 0, owned: ["a_trainee"], unlocked: [], equip: { avatar: "a_trainee", bg: null, badge: null } }; }
/* 저장값은 사용자가 고칠 수 있으므로 읽을 때마다 형식과 품목 번호를 확인한다 */
function epClean(raw) {
  const s = epBlank(); if (!raw || typeof raw !== "object") return s;
  if (Number.isInteger(raw.coins) && raw.coins >= 0) s.coins = Math.min(raw.coins, 9999999);
  if (Array.isArray(raw.owned)) s.owned = Array.from(new Set(["a_trainee"].concat(raw.owned.filter(i => epItem(i)))));
  if (Array.isArray(raw.unlocked)) s.unlocked = Array.from(new Set(raw.unlocked.filter(u => EP_UNLOCKS.includes(u))));
  const e = raw.equip && typeof raw.equip === "object" ? raw.equip : {};
  ["avatar", "bg", "badge"].forEach(k => { const it = epItem(e[k]); s.equip[k] = it && it.kind === k && s.owned.includes(it.id) ? it.id : null; });
  return s;
}
let EP_MEMORY = null;
function epLoad() { try { const t = localStorage.getItem(EP_KEY); if (t) return epClean(JSON.parse(t)); } catch (_) { /* 저장소를 못 쓰면 메모리 값을 쓴다 */ } return epClean(EP_MEMORY); }
function epDraw(cv, kind, id, f) {
  const it = epItem(id); if (!it) return;
  if (kind === "bg") { const fn = SCENE_ART[it.art]; if (fn) fn(kit(cv, f, it.art.length * 7 + it.art.charCodeAt(0) % 97)); return; }
  const fn = (kind === "avatar" ? AVATAR_ART : BADGE_ART)[it.art]; if (!fn) return;
  const k = kit(cv, f, it.art.length * 5 + 3); k.c.clearRect(0, 0, cv.width, cv.height); fn(k);
}
const EP_SIZE = { avatar: [32, 32], bg: [120, 40], badge: [24, 24] };
const EP_LIVE = new Set(); let EP_F = 0, EP_TIMER = null;
function epCanvas(kind, id, cls) {
  const cv = document.createElement("canvas"), z = EP_SIZE[kind]; cv.width = z[0]; cv.height = z[1]; cv.dataset.epKind = kind; cv.dataset.epId = id; if (cls) cv.className = cls;
  cv.style.imageRendering = "pixelated"; cv.setAttribute("aria-hidden", "true"); epDraw(cv, kind, id, EP_F); EP_LIVE.add(cv); epTick(); return cv;
}
function epTick() {
  if (EP_TIMER || (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches)) return;
  EP_TIMER = setInterval(() => { EP_F += 1; EP_LIVE.forEach(cv => { if (!cv.isConnected) { EP_LIVE.delete(cv); return; } if (cv.offsetParent !== null || cv.getClientRects().length) epDraw(cv, cv.dataset.epKind, cv.dataset.epId, EP_F); }); }, 170);
}

/* 앙상블 사이트에 붙이는 부분. 헤더와 내 계정 화면을 찾아 장착한 그림을 얹는다. app.js는 고치지 않아도 된다. */
function fit(cv, css) { Object.assign(cv.style, css); cv.dataset.epMark = "1"; return cv; }
function place(host, kind, id, css) {
  let cv = host.querySelector(`:scope > canvas[data-ep-kind="${kind}"]`);
  if (!id) { if (cv) cv.remove(); return; }
  if (cv && cv.dataset.epId === id) return;
  if (cv) cv.remove();
  host.prepend(fit(epCanvas(kind, id), css));
}
const LAYER = { position: "absolute", inset: "0", width: "100%", height: "100%", borderRadius: "inherit", pointerEvents: "none" };
function decorate() {
  const s = epLoad(), eq = s.equip, bd = epItem(eq.badge);
  document.querySelectorAll(".avatar-btn, #Profile .account-avatar, [data-encore-avatar]").forEach(el => {
    if (getComputedStyle(el).position === "static") el.style.position = "relative";
    el.style.overflow = "hidden"; place(el, "avatar", eq.avatar === "a_trainee" ? null : eq.avatar, LAYER);
  });
  document.querySelectorAll("#Profile .account-card, [data-encore-bg]").forEach(el => place(el, "bg", eq.bg, { display: "block", width: "100%", height: "auto", aspectRatio: "3 / 1", borderRadius: "20px", marginBottom: "16px", pointerEvents: "none" }));
  document.querySelectorAll("#Profile .account-name-row, [data-encore-badge]").forEach(el => {
    const below = el.classList.contains("account-name-row"), host = below ? el.parentElement : el;   /* 내 계정: 칭호를 닉네임 줄 아래(바로 뒤 형제)에 둠 */
    let tag = host.querySelector(":scope > .encore-title");
    if (!bd) { if (tag) tag.remove(); return; }
    if (tag && tag.dataset.id === bd.id) return;
    if (tag) tag.remove();
    tag = document.createElement("span"); tag.className = "encore-title"; tag.dataset.id = bd.id; tag.title = bd.name;
    Object.assign(tag.style, { display: "inline-flex", alignItems: "center", gap: "6px", marginLeft: below ? "0" : "8px", marginTop: below ? "17.6px" : "0", padding: "2px 10px 2px 4px", borderRadius: "999px", background: "#23232d", color: "#f4f4f8", fontSize: "12px", fontWeight: "700", verticalAlign: "middle" });
    tag.append(fit(epCanvas("badge", bd.id), { width: "20px", height: "20px" }), document.createTextNode(bd.name)); if (below) el.after(tag); else el.append(tag);
  });
}
/* 왼쪽 위 헤드폰 로고나 data-encore-open 요소를 누르면 게임 창을 연다. 닫아도 진행 상황은 남고 음악 재생도 끊지 않는다 */
let shell = null, opener = null;
function closeGame() { if (!shell) return; shell.style.display = "none"; document.documentElement.style.overflow = ""; if (opener && opener.focus) opener.focus(); }
function openGame() {
  opener = document.activeElement;
  if (!shell) {
    shell = document.createElement("div"); shell.id = "encoreShell"; shell.setAttribute("role", "dialog"); shell.setAttribute("aria-modal", "true"); shell.setAttribute("aria-label", "앙코르 차트");
    Object.assign(shell.style, { position: "fixed", inset: "0", zIndex: "2147483000", display: "flex", flexDirection: "column", background: "#121313" });
    const f = document.createElement("iframe"); f.src = "game/encore.html?v=3"; f.title = "앙코르 차트"; Object.assign(f.style, { flex: "1", width: "100%", border: "0" });
    shell.append(f); document.body.append(shell);   /* 위쪽 바(앙코르 차트·닫기) 없이 게임만. 닫기는 게임 안 홈 버튼 또는 Esc */
  }
  fitShell(); shell.style.display = "flex"; document.documentElement.style.overflow = "hidden"; shell.querySelector("iframe").focus();
}
/* 사이트는 폰에서 화면 전체를 zoom 으로 줄여 쓴다. 게임 창은 그 배율을 상쇄해 실제 화면 크기(1배)로 만들고, 게임 안의 ui-scale.js 가 메인 사이트와 똑같이 스스로 배율을 맞춘다
   (iframe 이 바깥 zoom 을 어떻게 받아들이는지는 브라우저마다 달라서, 특히 아이폰 Safari 에서 게임이 줄어들어 보이던 문제를 막음) */
function fitShell() { if (!shell) return; const z = parseFloat(document.documentElement.style.getPropertyValue("--z")) || 1; shell.style.zoom = z === 1 ? "" : String(1 / z); }
window.addEventListener("resize", fitShell); window.addEventListener("orientationchange", fitShell);
const TRIGGER = "#appHeader .brand-logo, [data-encore-open]";   /* 로그인 전 화면의 로고는 누를 수 없게 헤더 로고만 */
document.addEventListener("click", e => { const t = e.target.closest && e.target.closest(TRIGGER); if (t) { e.preventDefault(); openGame(); } });
document.addEventListener("keydown", e => { if (e.key === "Escape" && shell && shell.style.display !== "none") { closeGame(); return; } const t = e.target.closest && e.target.closest(TRIGGER); if (t && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openGame(); } });
function markLogo() { document.querySelectorAll("#appHeader .brand-logo").forEach(el => { if (el.dataset.encoreReady) return; el.dataset.encoreReady = "1"; el.setAttribute("role", "button"); el.setAttribute("tabindex", "0"); el.setAttribute("aria-label", "미니게임 앙코르 차트 열기"); el.title = "미니게임"; el.style.cursor = "pointer"; }); }
let queued = false;
function refresh() { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; decorate(); markLogo(); }); }
function store(data) { try { localStorage.setItem(EP_KEY, JSON.stringify(epClean(data))); } catch (_) { EP_MEMORY = epClean(data); } refresh(); }
/* 게임은 iframe 안에서 돌기 때문에 저장을 부모 창이 다시 해야 firebase.js의 동기화가 동작한다 */
window.addEventListener("message", e => { if (e.origin === location.origin && e.data && e.data.type === "encore:save") store(e.data.data); });
window.addEventListener("storage", e => { if (e.key === EP_KEY) refresh(); });
function boot() { decorate(); markLogo(); new MutationObserver(refresh).observe(document.body, { childList: true, subtree: true }); }
if (document.body) boot(); else document.addEventListener("DOMContentLoaded", boot);
window.EncoreProfile = { get: epLoad, set: store, refresh, open: openGame, close: closeGame, items: EP_ITEMS };

})();
