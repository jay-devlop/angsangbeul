/* 화면 너비에 따라 페이지 전체(글자·이미지·간격)를 같은 비율로 키우고 줄임.
   폰(480px 미만)은 너비에 비례해 0.75배까지 줄고, 480~1600px 는 그대로(1배), 1600px 이상 큰 화면은 1.25배까지 커짐.
   값을 바꾸려면 아래 네 숫자만 고치면 됨. CSS 의 vh·vw 는 이 배율(--z)로 나눠 쓰고 있어 화면을 꽉 채움. */
(function () {
  var SMALL_W = 480, MIN_Z = 0.75, LARGE_W = 1600, MAX_Z = 1.25;
  var root = document.documentElement;
  function apply() {
    if (window.parent !== window && root.hasAttribute('data-ui-inherit')) { root.style.removeProperty('--z'); root.style.zoom = ''; return; }   /* 사이트 안 게임 창(iframe, data-ui-inherit)은 바깥 페이지의 배율을 그대로 받음 */
    var w = window.innerWidth, z = 1;
    var canZoom = !!(window.CSS && CSS.supports && CSS.supports('zoom', '1.2'));   /* zoom 을 못 쓰는 오래된 브라우저는 배율을 적용하지 않고(1배) 원래대로 둠: 배율만 나눠 쓰면 화면이 어긋나기 때문 */
    if (!canZoom) z = 1;
    else if (w < SMALL_W) z = Math.max(MIN_Z, w / SMALL_W);
    else if (w > LARGE_W) z = Math.min(MAX_Z, w / LARGE_W);
    z = Math.round(z * 1000) / 1000;
    root.style.setProperty('--z', z);
    root.style.zoom = z === 1 ? '' : z;
  }
  apply();
  window.addEventListener('resize', apply);
  window.addEventListener('orientationchange', apply);
})();
