(function () {
  var PLAY_ICON = '<path d="M7 4.5v15l13-7.5z"/>';
  var PAUSE_ICON = '<path d="M6 5h4v14H6zM14 5h4v14h-4z"/>';
  var HEART = '<path d="M12 21s-7-4.6-9.3-9.2C1.2 8.6 3 5 6.4 5c2 0 3.7 1.2 4.6 2.8h2C13.9 6.2 15.6 5 17.6 5 21 5 22.8 8.6 21.3 11.8 19 16.4 12 21 12 21z"/>';
  var GENRE_COLORS = { '발라드': '#d4d4e0', 'R&B': '#b79cff', '인디': '#3ddc97', '일렉트로닉': '#ff9f6b' };
  var ART_GRADIENTS = ['linear-gradient(160deg,#3a3a48,#23232d)', 'linear-gradient(160deg,#2e2e3a,#1a1a22)'];

  var data = { songs: [], genres: [] };
  var state = { view: 'home', genre: '전체', query: '', current: null, playing: false, t: 0 };
  var timer = null;

  var $ = function (id) { return document.getElementById(id); };
  var el = {
    tracks: $('tracks'), chips: $('chips'), empty: $('empty'), title: $('listTitle'), sub: $('listSub'),
    input: $('searchInput'), player: $('player'), pTitle: $('playerTitle'), pArtist: $('playerArtist'),
    play: $('playBtn'), seek: $('seek'), cur: $('curTime'), tot: $('totTime'),
    bar: $('genreBar'), legend: $('genreLegend')
  };

  function mmss(s) { s = Math.floor(s); return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2); }
  function byId(id) { return data.songs.filter(function (s) { return s.id === id; })[0]; }

  /* 좋아요 상태는 브라우저에 저장 (사용할 수 없으면 무시) */
  function loadLikes() {
    try {
      var saved = JSON.parse(localStorage.getItem('ms-likes') || 'null');
      if (saved) data.songs.forEach(function (s) { s.liked = saved.indexOf(s.id) > -1; });
    } catch (e) {}
  }
  function saveLikes() {
    try {
      localStorage.setItem('ms-likes', JSON.stringify(data.songs.filter(function (s) { return s.liked; }).map(function (s) { return s.id; })));
    } catch (e) {}
  }

  /* 현재 조건(장르·검색어)에 맞는 곡 */
  function visible() {
    var q = state.query.trim().toLowerCase();
    return data.songs.filter(function (s) {
      if (state.genre !== '전체' && s.genre !== state.genre) return false;
      if (!q) return true;
      return (s.title + ' ' + s.artist + ' ' + s.genre).toLowerCase().indexOf(q) > -1;
    });
  }

  function renderChips() {
    el.chips.textContent = '';
    ['전체'].concat(data.genres).forEach(function (g) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'chip' + (g === state.genre ? ' is-active' : '');
      b.textContent = g; b.dataset.genre = g; b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', g === state.genre);
      el.chips.appendChild(b);
    });
  }

  function renderGenreMix() {
    var count = {}, total = data.songs.length;
    data.songs.forEach(function (s) { count[s.genre] = (count[s.genre] || 0) + 1; });
    el.bar.textContent = ''; el.legend.textContent = '';
    data.genres.forEach(function (g) {
      if (!count[g]) return;
      var seg = document.createElement('div');
      seg.style.flex = count[g]; seg.style.background = GENRE_COLORS[g] || '#d4d4e0';
      el.bar.appendChild(seg);
      var li = document.createElement('span');
      var dot = document.createElement('i'); dot.style.background = seg.style.background;
      li.appendChild(dot); li.appendChild(document.createTextNode(g + ' ' + Math.round(count[g] / total * 100) + '%'));
      el.legend.appendChild(li);
    });
  }

  function renderList() {
    var list = visible(), searching = state.query.trim() !== '';
    el.title.textContent = searching ? '"' + state.query.trim() + '" 검색 결과' : (state.genre === '전체' ? '추천 목록' : state.genre);
    el.sub.textContent = searching ? list.length + '곡' : '내 청취 이력을 바탕으로 한 추천';
    el.tracks.textContent = '';
    el.empty.hidden = list.length > 0;
    if (!list.length) el.empty.textContent = searching ? '검색 결과가 없어요. 다른 검색어를 입력해 보세요.' : '이 장르의 곡이 아직 없어요.';

    list.forEach(function (s, i) {
      var li = document.createElement('li');
      li.className = 'track' + (state.current === s.id ? ' is-current' : '');
      li.dataset.id = s.id;

      var no = document.createElement('span'); no.className = 't-no'; no.textContent = ('0' + (i + 1)).slice(-2);
      var art = document.createElement('div'); art.className = 't-art'; art.style.background = ART_GRADIENTS[i % 2];
      var main = document.createElement('button'); main.type = 'button'; main.className = 't-main'; main.dataset.play = s.id;
      var t = document.createElement('div'); t.className = 't-title'; t.textContent = s.title;
      var sub = document.createElement('div'); sub.className = 't-sub'; sub.textContent = s.artist + ' · ' + s.genre;
      main.appendChild(t); main.appendChild(sub);
      var dur = document.createElement('span'); dur.className = 't-dur'; dur.textContent = mmss(s.duration);
      var like = document.createElement('button'); like.type = 'button';
      like.className = 'like' + (s.liked ? ' is-on' : ''); like.dataset.like = s.id;
      like.setAttribute('aria-label', s.title + ' 좋아요'); like.setAttribute('aria-pressed', !!s.liked);
      like.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="' + (s.liked ? 'currentColor' : 'none') +
        '" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true">' + HEART + '</svg>';

      [no, art, main, dur, like].forEach(function (n) { li.appendChild(n); });
      el.tracks.appendChild(li);
    });
  }

  function renderPlayer() {
    var s = byId(state.current);
    el.player.hidden = !s;
    if (!s) return;
    el.pTitle.textContent = s.title;
    el.pArtist.textContent = s.artist;
    el.tot.textContent = mmss(s.duration);
    el.seek.max = s.duration; el.seek.value = state.t; el.cur.textContent = mmss(state.t);
    el.play.setAttribute('aria-label', state.playing ? '일시정지' : '재생');
    el.play.querySelector('svg').innerHTML = state.playing ? PAUSE_ICON : PLAY_ICON;
  }

  function renderView() {
    document.querySelectorAll('[data-view]').forEach(function (b) {
      b.classList.toggle('is-active', b.dataset.view === state.view);
    });
    if (state.view === 'search') el.input.focus();
  }

  /* 재생 (시연용: 실제 오디오 없이 시간만 흐름) */
  function tick() {
    var s = byId(state.current);
    if (!s || !state.playing) return;
    state.t += 1;
    if (state.t >= s.duration) { step(1); return; }
    el.seek.value = state.t; el.cur.textContent = mmss(state.t);
  }
  function setPlaying(on) {
    state.playing = on;
    clearInterval(timer);
    if (on) timer = setInterval(tick, 1000);
    renderPlayer();
  }
  function play(id) {
    state.current = id; state.t = 0;
    setPlaying(true);
    renderList();
  }
  function step(dir) {
    var list = visible();
    if (!list.length) return;
    var i = list.map(function (s) { return s.id; }).indexOf(state.current);
    play(list[(i + dir + list.length) % list.length].id);
  }

  /* 이벤트 */
  document.addEventListener('click', function (e) {
    var t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.play) return play(+t.dataset.play);
    if (t.dataset.like) {
      var s = byId(+t.dataset.like); s.liked = !s.liked; saveLikes(); return renderList();
    }
    if (t.dataset.genre) { state.genre = t.dataset.genre; renderChips(); return renderList(); }
    if (t.dataset.view) { state.view = t.dataset.view; return renderView(); }
    if (t === el.play) return setPlaying(!state.playing);
    if (t.id === 'prevBtn') return step(-1);
    if (t.id === 'nextBtn') return step(1);
  });
  el.input.addEventListener('input', function () {
    state.query = el.input.value;
    if (state.query.trim() && state.view !== 'search') { state.view = 'search'; renderView(); }
    renderList();
  });
  el.seek.addEventListener('input', function () {
    state.t = +el.seek.value; el.cur.textContent = mmss(state.t);
  });

  /* 시작: 샘플 데이터 불러오기 */
  fetch('data/demo.json')
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (json) {
      data = json;
      if (json.user) {
        $('nickname').textContent = json.user.nickname;
        $('avatar').textContent = json.user.nickname.charAt(0);
      }
      loadLikes();
      renderChips(); renderGenreMix(); renderList(); renderPlayer(); renderView();
    })
    .catch(function () {
      el.empty.hidden = false;
      el.empty.textContent = '샘플 데이터를 불러오지 못했어요. 파일을 직접 열지 말고 web 폴더에서 "python3 -m http.server"로 실행해 주세요.';
    });
})();
