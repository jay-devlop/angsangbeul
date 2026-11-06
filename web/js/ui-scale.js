/* 화면 너비에 따라 페이지 전체(글자·이미지·간격)를 같은 비율로 키우고 줄임.
   폰(480px 미만)은 너비에 비례해 0.8배까지 줄고, 480~1600px 는 그대로(1배), 1600px 이상 큰 화면은 1.2배까지 커짐.
   값을 바꾸려면 아래 네 숫자만 고치면 됨. CSS 의 vh·vw 는 이 배율(--z)로 나눠 쓰고 있어 화면을 꽉 채움. */
(function () {
  var SMALL_W = 480, MIN_Z = 0.8, LARGE_W = 1600, MAX_Z = 1.2;
  var root = document.documentElement;
  function apply() {
    if (window.parent !== window && root.hasAttribute('data-ui-inherit')) { root.style.removeProperty('--z'); root.style.zoom = ''; return; }   /* 사이트 안 게임 창(iframe, data-ui-inherit)은 바깥 페이지의 배율을 그대로 받음 */
    var w = window.innerWidth, z = 1;
    if (w < SMALL_W) z = Math.max(MIN_Z, w / SMALL_W);
    else if (w > LARGE_W) z = Math.min(MAX_Z, w / LARGE_W);
    z = Math.round(z * 1000) / 1000;
    root.style.setProperty('--z', z);
    root.style.zoom = z === 1 ? '' : z;
  }
  apply();
  window.addEventListener('resize', apply);
  window.addEventListener('orientationchange', apply);
})();
