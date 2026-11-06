(function () {
  var PLAY_ICON = '<path d="M7 4.5v15l13-7.5z"/>';
  var PAUSE_ICON = '<path d="M6 5h4v14H6zM14 5h4v14h-4z"/>';
  var SEARCH = /^Search(Songs|Artists|Genres)?$/;

  var data = { songs: [] };
  var userPlaylists = [];
  var profile = { nickname: '', avatar: '', avatarHue: 280, genres: [] };   // 로그인한 사용자의 값으로만 채워짐(기본 데모 프로필 없음)
  var authPending = true, signingUp = false;   // 로그인 상태 확인 중 / 이메일 가입 진행 중
  var profileGenresExpanded = false;
  var registeredNicknames = [];
  var genreList = [];            // data/genres.json (가입 칩·검색 장르 타일)
  var songToJamendo = {};        // KKBox song_id → [Jamendo 곡 id]  (추천 모델 연결용)
  // 처음에는 곡을 고르지 않은 상태: 정지, 재생바 숨김
  var state = { current: null, ctx: null, fullQueue: false, t: 0, dur: 0, playing: false, status: 'idle', query: '', started: false, artist: '', genre: '', modelRecs: null, activePlaylistIndex: 0, authUser: null };
  var byId = {};
  var tpl = new WeakMap();       // 목록 컨테이너 → 복제용 행 템플릿
  var audio = null;              // 재생용 <audio> 하나 (한 번에 한 곡만 재생)
  var defaultCover = '';         // 이미지가 없을 때 쓰는 기본 커버(CSS 변수 --cover 의 처음 값)
  var playerHideTimer = null;
  var PLAYER_IDLE_TIMEOUT = 5 * 60 * 1000;

  function keepPlayerVisible() {
    clearTimeout(playerHideTimer);
    playerHideTimer = null;
    state.started = true;
  }
  function schedulePlayerHide() {
    clearTimeout(playerHideTimer);
    if (state.playing) return;
    playerHideTimer = setTimeout(function () {
      state.started = false;
      playerHideTimer = null;
      render();
    }, PLAYER_IDLE_TIMEOUT);
  }

  // 현재 화면 이름(주소의 #뒤). 없으면 로그인
  function cur() {
    var id = (location.hash || '').replace('#', '');
    var el = document.getElementById(id);
    return el && el.classList.contains('screen') ? id : 'LoginEmail';
  }
  // 초 → "3:42"
  function mmss(s) { s = Math.floor(s || 0); return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2); }
  // 한 자리 숫자 앞에 0 붙이기
  function pad2(n) { return n < 10 ? '0' + n : String(n); }
  // 지금 재생 중인 곡
  function song() { return byId[state.current]; }
  // 재생 중인 곡 길이(초): 파일에서 읽은 값 우선, 없으면 데이터의 길이
  function dur() { return state.dur || (song() ? song().duration : 0) || 1; }
  // http(s) 주소만 허용 (데이터의 링크·이미지를 안전하게 쓰기 위해)
  function isHttp(u) { return typeof u === 'string' && /^https?:\/\//i.test(u); }
  function colorWithAlpha(hex, alpha) {
    var value = parseInt(hex.slice(1), 16);
    return 'rgba(' + (value >> 16) + ',' + ((value >> 8) & 255) + ',' + (value & 255) + ',' + alpha + ')';
  }

  /* ---------- 저장(좋아요) : 브라우저 저장소에 보관 ---------- */
  // 저장된 좋아요 불러오기
  function loadLikes() {
    try {
      var saved = JSON.parse(localStorage.getItem('ms-likes') || 'null');
      if (Array.isArray(saved)) data.songs.forEach(function (s) { s.liked = saved.indexOf(s.id) > -1; });
    } catch (e) {
      showToast('좋아요한 곡을 불러오지 못했어요. 브라우저 저장 공간을 확인해 주세요.');
    }
  }
  // 좋아요 저장
  function saveLikes() {
    try {
      localStorage.setItem('ms-likes', JSON.stringify(data.songs.filter(function (s) { return s.liked; }).map(function (s) { return s.id; })));
      return true;
    } catch (e) {
      return false;
    }
  }
  function nicknameKey(value) { return String(value || '').normalize('NFKC').trim().toLowerCase(); }
  function loadProfile() {
    try {
      var savedProfile = JSON.parse(localStorage.getItem('ms-profile') || 'null');
      if (savedProfile && typeof savedProfile.nickname === 'string' && savedProfile.nickname.trim()) {
        profile.nickname = savedProfile.nickname.trim();
        profile.avatar = typeof savedProfile.avatar === 'string' && /^data:image\/webp;base64,/i.test(savedProfile.avatar) ? savedProfile.avatar : '';
        profile.avatarHue = Number.isInteger(savedProfile.avatarHue) ? savedProfile.avatarHue : 280;
        if (Array.isArray(savedProfile.genres)) {
          profile.genres = savedProfile.genres.filter(function (name, index, genres) {
            return typeof name === 'string' && name.trim() && genres.indexOf(name) === index;
          }).slice(0, GENRE_MAX);
        }
      }
      var savedNicknames = JSON.parse(localStorage.getItem('ms-nicknames') || '[]');
      if (Array.isArray(savedNicknames)) registeredNicknames = savedNicknames.filter(function (name) { return typeof name === 'string' && name.trim(); });
    } catch (e) {
      showToast('계정 정보를 불러오지 못했어요.');
    }
    if (profile.nickname) {   // 저장된 프로필이 있을 때만 기록(없는 사용자에게 기본 프로필을 만들어 저장하지 않음)
      if (!registeredNicknames.some(function (name) { return nicknameKey(name) === nicknameKey(profile.nickname); })) registeredNicknames.push(profile.nickname);
      if (!saveProfile()) showToast('계정 정보를 저장하지 못했어요. 저장 공간을 확인해 주세요.');
    }
    renderProfile();
  }
  function saveProfile() {
    try {
      var previousNicknames = localStorage.getItem('ms-nicknames');
      localStorage.setItem('ms-nicknames', JSON.stringify(registeredNicknames));
      try {
        localStorage.setItem('ms-profile', JSON.stringify(profile));
        return true;
      } catch (profileError) {
        try {
          if (previousNicknames === null) localStorage.removeItem('ms-nicknames');
          else localStorage.setItem('ms-nicknames', previousNicknames);
        } catch (restoreError) {
          console.error('닉네임 저장 상태를 복구하지 못했어요.', restoreError);
        }
        return false;
      }
    } catch (e) {
      return false;
    }
  }
  function renderProfile() {
    document.querySelectorAll('#Profile [data-role=accountName]').forEach(function (name) { name.textContent = profile.nickname; });
    document.querySelectorAll('[data-role=accountEmail]').forEach(function (e) { e.textContent = state.authUser ? (state.authUser.email || '') : ''; });
    document.querySelectorAll('#Profile .profile-avatar-upload').forEach(function (avatar) {
      avatar.style.backgroundImage = profile.avatar ? 'url("' + profile.avatar + '")' : '';
      avatar.style.backgroundSize = profile.avatar ? 'cover' : '';
      avatar.style.backgroundPosition = profile.avatar ? 'center' : '';
      if (!profile.avatar) avatar.style.background = 'linear-gradient(145deg, hsl(' + profile.avatarHue + ' 58% 42%), hsl(' + ((profile.avatarHue + 36) % 360) + ' 52% 24%))';
    });
    document.querySelectorAll('.avatar-btn').forEach(function (avatar) {
      avatar.textContent = Array.from(profile.nickname)[0] || '나';
      avatar.setAttribute('aria-label', '내 계정: ' + profile.nickname);
      avatar.style.backgroundImage = profile.avatar ? 'url("' + profile.avatar + '")' : '';
      avatar.style.backgroundSize = profile.avatar ? 'cover' : '';
      avatar.style.backgroundPosition = profile.avatar ? 'center' : '';
      if (!profile.avatar) avatar.style.background = imageGradient(profile.avatarHue);
      avatar.classList.toggle('has-avatar', !!profile.avatar);
    });
    var selectedGenres = document.querySelector('#Profile [data-profile-selected-genres]');
    if (selectedGenres) {
      selectedGenres.textContent = '';
      profile.genres.forEach(function (genre) {
        var chip = document.createElement('span');
        chip.className = 'tag';
        chip.textContent = genre;
        selectedGenres.appendChild(chip);
      });
      selectedGenres.hidden = profileGenresExpanded;
    }
    var genreOptions = document.querySelector('#Profile [data-profile-genre-options]');
    if (genreOptions) {
      genreOptions.textContent = '';
      var availableGenres = genreList.map(function (genre) { return genre.name; }).concat(['발라드', '인디']);
      profile.genres.forEach(function (genre) {
        if (availableGenres.indexOf(genre) === -1) availableGenres.push(genre);
      });
      availableGenres.filter(function (genre, index) { return availableGenres.indexOf(genre) === index; }).forEach(function (genre) {
        var option = document.createElement('button');
        var selected = profile.genres.indexOf(genre) !== -1;
        option.type = 'button';
        option.className = 'chip' + (selected ? ' is-on' : '');
        option.dataset.profileGenre = genre;
        option.setAttribute('aria-pressed', selected ? 'true' : 'false');
        option.textContent = genre;
        genreOptions.appendChild(option);
      });
      genreOptions.hidden = !profileGenresExpanded;
    }
    var genreToggle = document.querySelector('#Profile [data-profile-genre-toggle]');
    if (genreToggle) {
      genreToggle.setAttribute('aria-expanded', profileGenresExpanded ? 'true' : 'false');
      genreToggle.setAttribute('aria-label', profileGenresExpanded ? '장르 선택 닫기' : '장르 선택 열기');
    }
  }
  function toggleProfileGenre(genre) {
    var previousGenres = profile.genres.slice();
    var selectedIndex = profile.genres.indexOf(genre);
    if (selectedIndex !== -1) profile.genres.splice(selectedIndex, 1);
    else if (profile.genres.length >= GENRE_MAX) {
      showToast('장르는 최대 3개까지 선택할 수 있어요.');
      return;
    } else profile.genres.push(genre);
    if (!saveProfile()) {
      profile.genres = previousGenres;
      showToast('장르를 저장하지 못했어요. 저장 공간을 확인해 주세요.');
      renderProfile();
      return;
    }
    renderProfile();
  }
  function finishNicknameEdit(input, cancel) {
    if (!input || input.hidden) return;
    var error = document.querySelector('#Profile [data-profile-name-error]');
    var nextNickname = input.value.normalize('NFKC').trim();
    if (cancel) nextNickname = profile.nickname;
    if (!nextNickname) {
      if (error) { error.textContent = '닉네임을 입력해 주세요.'; error.hidden = false; }
      input.value = profile.nickname;
      input.hidden = true;
      document.querySelector('#Profile [data-role=accountName]').hidden = false;
      document.querySelector('#Profile [data-profile-edit]').hidden = false;
      return;
    }
    var duplicate = registeredNicknames.some(function (name) {
      return nicknameKey(name) === nicknameKey(nextNickname) && nicknameKey(name) !== nicknameKey(profile.nickname);
    });
    if (duplicate) {
      if (error) { error.textContent = '이미 사용 중인 닉네임이에요.'; error.hidden = false; }
      input.value = profile.nickname;
      input.hidden = true;
      document.querySelector('#Profile [data-role=accountName]').hidden = false;
      document.querySelector('#Profile [data-profile-edit]').hidden = false;
      return;
    }
    var previousNickname = profile.nickname;
    profile.nickname = nextNickname;
    registeredNicknames = registeredNicknames.filter(function (name) { return nicknameKey(name) !== nicknameKey(previousNickname); });
    registeredNicknames.push(nextNickname);
    if (!saveProfile()) {
      profile.nickname = previousNickname;
      registeredNicknames = registeredNicknames.filter(function (name) { return nicknameKey(name) !== nicknameKey(nextNickname); });
      registeredNicknames.push(previousNickname);
      if (error) { error.textContent = '저장하지 못했어요. 저장 공간을 확인해 주세요.'; error.hidden = false; }
    } else if (error) {
      error.hidden = true;
      error.textContent = '';
    }
    input.hidden = true;
    document.querySelector('#Profile [data-role=accountName]').hidden = false;
    document.querySelector('#Profile [data-profile-edit]').hidden = false;
    renderProfile();
  }
  function loadUserPlaylists() {
    try {
      var saved = JSON.parse(localStorage.getItem('ms-playlists') || '[]');
      if (Array.isArray(saved)) userPlaylists = saved.filter(function (p) { return p && typeof p.name === 'string'; }).map(function (p) {
        return {
          name: p.name,
          trackIds: Array.isArray(p.trackIds) ? p.trackIds.filter(Number.isFinite) : [],
          colorHue: Number.isInteger(p.colorHue) ? p.colorHue : Math.floor(Math.random() * 360),
          cover: typeof p.cover === 'string' && /^data:image\/(?:png|jpeg|webp|gif);base64,/i.test(p.cover) ? p.cover : ''
        };
      });
      if (!saveUserPlaylists()) showToast('플레이리스트를 저장하지 못했어요. 브라우저 저장 공간을 확인해 주세요.');
    } catch (e) {
      showToast('저장된 플레이리스트를 불러오지 못했어요.');
    }
  }
  function saveUserPlaylists() {
    try { localStorage.setItem('ms-playlists', JSON.stringify(userPlaylists)); return true; } catch (e) { return false; }
  }
  function setPlaylistCover(art, playlist) {
    if (!art || !playlist) return;
    art.style.background = playlist.cover
      ? 'url("' + playlist.cover + '") center / cover no-repeat'
      : 'linear-gradient(145deg, hsl(' + playlist.colorHue + ' 58% 42%), hsl(' + ((playlist.colorHue + 36) % 360) + ' 52% 24%))';
  }
  function processImageFile(file, done) {
    if (!/^image\//i.test(file.type)) { done('이미지 파일만 업로드할 수 있어요.'); return; }
    if (file.size > 10 * 1024 * 1024) { done('이미지는 10MB 이하만 업로드할 수 있어요.'); return; }
    var reader = new FileReader();
    reader.onerror = function () { done('이미지를 읽지 못했어요. 다시 시도해 주세요.'); };
    reader.onload = function () {
      var image = new Image();
      image.onerror = function () { done('이미지 파일을 열 수 없어요.'); };
      image.onload = function () {
        var scale = Math.min(1, 640 / Math.max(image.naturalWidth, image.naturalHeight));
        var canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
        canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
        var context = canvas.getContext('2d');
        if (!context) { done('이미지를 처리할 수 없어요.'); return; }
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        var result;
        try { result = canvas.toDataURL('image/webp', 0.82); } catch (error) {
          done('이미지를 저장할 수 없어요. 다른 이미지를 선택해 주세요.');
          return;
        }
        if (result.length > 2.5 * 1024 * 1024) { done('이미지 용량이 너무 커요. 더 작은 이미지를 선택해 주세요.'); return; }
        done(null, result);
      };
      image.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  }
  var imageEditorState = null;
  var imageEditorColors = [
    { hue: 0, name: '빨강' }, { hue: 30, name: '주황' }, { hue: 55, name: '노랑' },
    { hue: 120, name: '초록' }, { hue: 210, name: '파랑' }, { hue: 245, name: '남색' },
    { hue: 280, name: '보라' }
  ];
  var imageEditorInput = null;
  function imageGradient(hue) {
    return 'linear-gradient(145deg, hsl(' + hue + ' 58% 42%), hsl(' + ((hue + 36) % 360) + ' 52% 24%))';
  }
  function closeImageEditor() {
    var backdrop = document.querySelector('.image-editor-backdrop');
    if (backdrop) backdrop.remove();
    imageEditorState = null;
  }
  function updateImageEditorPreview() {
    if (!imageEditorState) return;
    var preview = document.querySelector('.image-editor-preview');
    var hue = imageEditorState.hue;
    if (preview) {
      preview.style.backgroundImage = imageEditorState.image ? 'url("' + imageEditorState.image + '")' : imageGradient(hue);
      preview.style.backgroundSize = imageEditorState.image ? 'cover' : '';
      preview.style.backgroundPosition = imageEditorState.image ? 'center' : '';
    }
    document.querySelectorAll('.image-editor-color').forEach(function (button) {
      var selected = +button.dataset.hue === hue && !imageEditorState.image;
      button.classList.toggle('is-selected', selected);
      button.setAttribute('aria-pressed', selected ? 'true' : 'false');
    });
  }
  function openImageEditor(type, index) {
    closeImageEditor();
    var playlist = type === 'playlist' ? userPlaylists[index] : null;
    if (type === 'playlist' && !playlist) return;
    imageEditorState = {
      type: type,
      index: index,
      hue: playlist ? playlist.colorHue : profile.avatarHue,
      image: playlist ? playlist.cover : profile.avatar
    };
    var backdrop = document.getElementById('tplImageEditor').content.firstElementChild.cloneNode(true); // 마크업: page/dialogs.html
    var colors = backdrop.querySelector('.image-editor-colors');
    imageEditorColors.forEach(function (color) {
      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'image-editor-color';
      button.dataset.hue = color.hue;
      button.setAttribute('aria-label', color.name);
      button.setAttribute('title', color.name);
      button.setAttribute('aria-pressed', 'false');
      button.style.background = imageGradient(color.hue);
      colors.appendChild(button);
    });
    var cancel = backdrop.querySelector('[data-image-editor-cancel]');
    document.body.appendChild(backdrop);
    updateImageEditorPreview();
    cancel.focus();
  }
  function chooseEditorImage() {
    if (!imageEditorInput) {
      imageEditorInput = document.createElement('input');
      imageEditorInput.type = 'file';
      imageEditorInput.accept = 'image/*';
      imageEditorInput.hidden = true;
      imageEditorInput.addEventListener('change', function () {
        var file = imageEditorInput.files && imageEditorInput.files[0];
        imageEditorInput.value = '';
        var editing = imageEditorState;
        if (!file || !editing) return;
        processImageFile(file, function (error, image) {
          if (error) { showToast(error); return; }
          if (imageEditorState !== editing) return;
          editing.image = image;
          updateImageEditorPreview();
        });
      });
      document.body.appendChild(imageEditorInput);
    }
    imageEditorInput.click();
  }
  function saveImageEditor() {
    if (!imageEditorState) return;
    var editing = imageEditorState;
    if (editing.type === 'playlist') {
      var playlist = userPlaylists[editing.index];
      if (!playlist) { closeImageEditor(); return; }
      var previousCover = playlist.cover;
      var previousHue = playlist.colorHue;
      playlist.cover = editing.image;
      playlist.colorHue = editing.hue;
      if (!saveUserPlaylists()) {
        playlist.cover = previousCover;
        playlist.colorHue = previousHue;
        showToast('저장 공간이 부족해 이미지를 저장하지 못했어요.');
        return;
      }
      closeImageEditor();
      renderUserPlaylists();
      renderPlaylistDetail();
      return;
    }
    var previousAvatar = profile.avatar;
    var previousHue = profile.avatarHue;
    profile.avatar = editing.image;
    profile.avatarHue = editing.hue;
    if (!saveProfile()) {
      profile.avatar = previousAvatar;
      profile.avatarHue = previousHue;
      showToast('저장 공간이 부족해 프로필 사진을 저장하지 못했어요.');
      return;
    }
    closeImageEditor();
    renderProfile();
  }
  function beginNicknameEdit() {
    var name = document.querySelector('#Profile [data-role=accountName]');
    var input = document.querySelector('#Profile [data-profile-name-input]');
    var button = document.querySelector('#Profile [data-profile-edit]');
    var error = document.querySelector('#Profile [data-profile-name-error]');
    if (!name || !input || !button) return;
    if (error) error.hidden = true;
    input.value = profile.nickname;
    name.hidden = true;
    button.hidden = true;
    input.hidden = false;
    input.focus();
    input.select();
  }
  function renderUserPlaylists() {
    document.querySelectorAll('[data-user-playlists]').forEach(function (box) {
      box.textContent = '';
      userPlaylists.forEach(function (playlist) {
        var card = document.createElement('a'); card.className = 'playlist-card user-playlist-card'; card.href = '#PlaylistDetail';
        card.dataset.playlistIndex = userPlaylists.indexOf(playlist);
        var art = document.createElement('div'); art.className = 'playlist-art--a';
        var hue = Number.isInteger(playlist.colorHue) ? playlist.colorHue : Math.floor(Math.random() * 360);
        playlist.colorHue = hue;
        setPlaylistCover(art, playlist);
        var info = document.createElement('div');
        var name = document.createElement('div'); name.className = 'text-title'; name.textContent = playlist.name;
        var count = document.createElement('div'); count.className = 'caption'; count.textContent = (playlist.trackIds || []).length + '곡';
        info.appendChild(name); info.appendChild(count);
        card.appendChild(art); card.appendChild(info); box.appendChild(card);
      });
    });
  }
  /* 내 라이브러리 플레이리스트: PC 오른쪽 클릭 / 모바일 꾹 누르기 → '삭제' 메뉴 */
  var playlistMenuSuppressClick = false;
  function closePlaylistMenu() { var m = document.querySelector('.playlist-menu'); if (m) m.remove(); }
  function deleteUserPlaylist(index) {
    var removed = userPlaylists.splice(index, 1)[0];
    if (!removed) return;
    if (!saveUserPlaylists()) {
      userPlaylists.splice(index, 0, removed);
      showToast('플레이리스트를 삭제하지 못했어요. 브라우저 저장 공간을 확인해 주세요.');
      return;
    }
    if (state.activePlaylistIndex === index) state.activePlaylistIndex = 0;
    else if (state.activePlaylistIndex > index) state.activePlaylistIndex--;
    renderUserPlaylists();
    showToast('플레이리스트를 삭제했어요.');
  }
  function showPlaylistMenu(card, x, y) {
    closePlaylistMenu();
    var index = +card.dataset.playlistIndex;
    if (!userPlaylists[index]) return;
    var menu = document.createElement('div'); menu.className = 'playlist-menu'; menu.setAttribute('role', 'menu');
    var del = document.createElement('button'); del.type = 'button'; del.className = 'playlist-menu-delete'; del.setAttribute('role', 'menuitem');
    del.textContent = "'" + userPlaylists[index].name + "' 삭제";
    del.addEventListener('click', function () { closePlaylistMenu(); deleteUserPlaylist(index); });
    menu.appendChild(del); document.body.appendChild(menu);
    var r = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(x, window.innerWidth - r.width - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(y, window.innerHeight - r.height - 8)) + 'px';
    del.focus();
  }
  (function () {
    var timer = null, sx = 0, sy = 0;
    function cancel() { if (timer) { clearTimeout(timer); timer = null; } }
    document.addEventListener('contextmenu', function (e) {
      var card = e.target.closest && e.target.closest('.user-playlist-card');
      if (!card) return;
      e.preventDefault(); cancel(); showPlaylistMenu(card, e.clientX, e.clientY);
    });
    document.addEventListener('touchstart', function (e) {
      var card = e.target.closest && e.target.closest('.user-playlist-card');
      if (!card || e.touches.length !== 1) return;
      sx = e.touches[0].clientX; sy = e.touches[0].clientY;
      cancel();
      timer = setTimeout(function () {
        timer = null; playlistMenuSuppressClick = true;
        setTimeout(function () { playlistMenuSuppressClick = false; }, 800);
        showPlaylistMenu(card, sx, sy);
      }, 500);
    }, { passive: true });
    document.addEventListener('touchmove', function (e) {
      if (timer && (Math.abs(e.touches[0].clientX - sx) > 10 || Math.abs(e.touches[0].clientY - sy) > 10)) cancel();
    }, { passive: true });
    document.addEventListener('touchend', cancel);
    document.addEventListener('touchcancel', cancel);
    // 꾹 누른 뒤 손을 뗄 때 생기는 클릭(=플레이리스트 열기)은 막음
    document.addEventListener('click', function (e) {
      if (playlistMenuSuppressClick && e.target.closest('.user-playlist-card')) { e.preventDefault(); e.stopPropagation(); return; }
      if (!e.target.closest('.playlist-menu')) closePlaylistMenu();
    }, true);
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closePlaylistMenu(); });
    window.addEventListener('scroll', closePlaylistMenu, true);
    window.addEventListener('hashchange', closePlaylistMenu);
  })();
  /* 아티스트 가로 목록: 마우스로 끌어서도 좌우 스크롤 (터치·트랙패드는 기본 스크롤) */
  (function () {
    var rail = null, startX = 0, startLeft = 0, moved = false;
    document.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      rail = e.target.closest ? e.target.closest('.rail[data-artists]') : null;
      if (!rail) return;
      startX = e.clientX; startLeft = rail.scrollLeft; moved = false;
    });
    document.addEventListener('mousemove', function (e) {
      if (!rail) return;
      var dx = e.clientX - startX;
      if (!moved && Math.abs(dx) > 5) { moved = true; rail.classList.add('is-dragging'); }
      if (moved) rail.scrollLeft = startLeft - dx;
    });
    document.addEventListener('mouseup', function () { if (rail) rail.classList.remove('is-dragging'); rail = null; });
    // 끌고 난 뒤 손을 뗄 때 생기는 클릭(=아티스트 열기)은 막음
    document.addEventListener('click', function (e) {
      if (moved && e.target.closest('.rail[data-artists]')) { e.preventDefault(); e.stopPropagation(); }
      moved = false;
    }, true);
  })();
  function activePlaylist() { return userPlaylists[state.activePlaylistIndex] || null; }
  function renderPlaylistDetail() {
    var playlist = activePlaylist();
    var title = document.querySelector('#PlaylistDetail [data-role=playlistName]');
    var count = document.querySelector('#PlaylistDetail [data-role=playlistCount]');
    var art = document.querySelector('#PlaylistDetail [data-role=playlistArt]');
    if (title) title.textContent = playlist ? playlist.name : '플레이리스트';
    if (count) count.textContent = (playlist && playlist.trackIds ? playlist.trackIds.length : 0) + '곡';
    if (art && playlist) {
      art.dataset.playlistIndex = state.activePlaylistIndex;
      art.setAttribute('role', 'button'); art.setAttribute('tabindex', '0');
      art.setAttribute('aria-label', playlist.name + ' 이미지 편집');
      art.classList.add('playlist-cover-upload');
      if (!art.querySelector('.upload-hint')) {
        var hint = document.createElement('span'); hint.className = 'upload-hint'; hint.textContent = '편집'; hint.setAttribute('aria-hidden', 'true');
        art.appendChild(hint);
      }
      setPlaylistCover(art, playlist);
    }
    renderLists(document.getElementById('PlaylistDetail'));
  }
  function ensureTrackActions(row) {
    if (!row || row.querySelector('.track-actions')) return;
    var like = row.querySelector('.like-btn, .like-btn--on');
    if (!like) return;
    var actions = document.createElement('div'); actions.className = 'track-actions';
    var add = document.createElement('button'); add.type = 'button'; add.className = 'add-to-playlist';
    add.setAttribute('aria-label', '플레이리스트에 추가'); add.title = '플레이리스트에 추가';
    var icon = document.createElement('img'); icon.src = 'icon/plus.png'; icon.alt = ''; icon.width = 20; icon.height = 20;
    add.appendChild(icon);
    like.parentNode.insertBefore(actions, like);
    actions.appendChild(like); actions.appendChild(add);
  }
  var playlistPickerTrackId = null;
  var pendingNewPlaylistTrackId = null; // 팝업의 '새 플레이리스트 만들기'로 넘어온 곡: 만들기를 누르면 새 목록에 넣음
  function closePlaylistPicker() {
    var picker = document.querySelector('.playlist-picker-backdrop');
    if (picker) picker.remove();
    playlistPickerTrackId = null;
  }
  function showPlaylistPicker(trackId) {
    closePlaylistPicker();
    playlistPickerTrackId = trackId;
    var backdrop = document.getElementById('tplPlaylistPicker').content.firstElementChild.cloneNode(true); // 마크업: page/dialogs.html
    var dialog = backdrop.querySelector('.playlist-picker');
    var options = dialog.querySelector('.playlist-picker-options');
    if (!userPlaylists.length) {
      options.remove();   // 플레이리스트가 없으면 '먼저 만들어 주세요' 안내와 만들기 버튼만 남김
    } else {
      dialog.querySelector('[data-picker-empty]').remove();
      dialog.querySelector('[data-picker-create]').remove();
      userPlaylists.forEach(function (playlist, index) {
        var option = document.createElement('button'); option.type = 'button'; option.className = 'playlist-picker-option'; option.dataset.playlistIndex = index;
        var name = document.createElement('span'); name.textContent = playlist.name;
        var count = document.createElement('span'); count.className = 'caption'; count.textContent = (playlist.trackIds || []).length + '곡';
        option.appendChild(name); option.appendChild(count); options.appendChild(option);
      });
    }
    document.body.appendChild(backdrop);
    var firstOption = dialog.querySelector('.playlist-picker-option, .playlist-picker-close');
    if (firstOption) firstOption.focus();
  }

  /* ---------- 검색·정렬 ---------- */
  var topCache = null;
  // Jamendo에서 많이 재생된 순
  function topTracks() {
    if (!topCache) topCache = data.songs.slice().sort(function (a, b) { return b.listens - a.listens; });
    return topCache;
  }
  function norm(x) { return String(x || '').normalize('NFKC').toLowerCase(); }
  // 곡명·아티스트·앨범명에 검색어(공백으로 나눈 단어 모두)가 들어 있는 곡
  function searchTracks(q) {
    var toks = norm(q).split(/\s+/).filter(Boolean);
    if (!toks.length) return [];
    return topTracks().filter(function (s) {
      var hay = norm(s.title + ' ' + s.artist + ' ' + s.album);
      return toks.every(function (t) { return hay.indexOf(t) > -1; });
    });
  }
  // 곡 목록 → 아티스트 목록(처음 나온 순서 유지)
  function artistsOf(tracks) {
    var map = {}, out = [];
    tracks.forEach(function (s) {
      var a = map[s.artist];
      if (!a) { a = map[s.artist] = { name: s.artist, tracks: [], first: s }; out.push(a); }
      a.tracks.push(s);
    });
    return out;
  }
  function tracksOfArtist(name) { return topTracks().filter(function (s) { return s.artist === name; }); }
  function genreDef(name) { return genreList.filter(function (g) { return g.name === name; })[0]; }
  function tracksOfGenre(name) {
    var def = genreDef(name);
    if (def) return topTracks().filter(function (s) { return s.primaryGenre === def.name; });   // 한 곡은 대표 장르 하나에만 분류
    return topTracks().filter(function (s) { return s.genres.some(function (g) { return g === norm(name); }); });
  }
  function likedTracks() { return topTracks().filter(function (s) { return s.liked; }); }
  // 지금 곡 다음에 재생될 곡 n개
  function nextTracks(n) {
    // 재생할 곡을 고르지 않았으면: 추천이 생긴 뒤(서로 다른 3곡 이후)에는 추천 곡 목록을, 추천이 아직 없으면 전체 곡(많이 재생된 순)을 보여 줌
    if (state.current === null || !byId[state.current]) return distinctPlays() >= 3 ? (state.modelRecs || topTracks()).slice(0, n) : topTracks();
    var ids = state.ctx && state.ctx.length ? state.ctx : topTracks().map(function (s) { return s.id; });
    var i = ids.indexOf(state.current), out = [];
    if (state.fullQueue) return ids.slice(i + 1).map(function (id) { return byId[id]; }).filter(Boolean);
    for (var k = 1; k <= Math.min(n, ids.length - 1); k++) out.push(byId[ids[(i + k + ids.length) % ids.length]]);
    return out.filter(Boolean);
  }

  /* ---------- 이미지: image → album_image → 기본 이미지 ---------- */
  var imgOk = {}; // 주소 → 불러오기 성공 여부
  function pickImage(s, cb) {
    var urls = [s.image, s.albumImage || s.album_image].filter(isHttp);
    (function next(i) {
      if (i >= urls.length) return cb(null);
      var u = urls[i];
      if (imgOk[u] === true) return cb(u);
      if (imgOk[u] === false) return next(i + 1);
      var im = new Image();
      im.onload = function () { imgOk[u] = true; cb(u); };
      im.onerror = function () { imgOk[u] = false; next(i + 1); };
      im.src = u;
    })(0);
  }
  function cssUrl(u) { return 'url("' + u.replace(/"/g, '%22') + '")'; }
  // 요소 배경에 곡 이미지를 입힘 (실패하면 CSS의 기본 배경 그대로)
  function paintArt(el, s, shade) {
    if (!el) return;
    pickImage(s, function (u) {
      if (!u) return;
      el.style.backgroundImage = (shade ? 'linear-gradient(180deg, rgba(0,0,0,0) 45%, rgba(0,0,0,.6) 100%), ' : '') + cssUrl(u);
      el.style.backgroundSize = 'cover';
      el.style.backgroundPosition = 'center';
    });
  }
  // 재생 중인 곡의 커버를 CSS 변수(--cover)로 전달: 재생바·재생 화면 LP 라벨·배경 빛이 함께 바뀜
  function setCover(s) {
    var root = document.documentElement;
    root.style.setProperty('--cover', defaultCover);
    var discImage = document.querySelector('#Playing [data-role=discImage]');
    if (discImage) discImage.style.visibility = s ? 'hidden' : '';
    if (!s) return;
    pickImage(s, function (u) {
      if (state.current !== s.id) return;
      if (u) root.style.setProperty('--cover', cssUrl(u));
      if (discImage) {
        if (u) discImage.src = u;
        else discImage.removeAttribute('src');
        discImage.style.visibility = '';
      }
    });
  }
  // 요소 안의 첫 글자(텍스트 노드)만 바꿈: 안에 있는 다른 요소(재생 버튼 등)는 그대로 둠
  function setLabel(el, text) {
    var node = Array.prototype.filter.call(el.childNodes, function (n) { return n.nodeType === 3; })[0];
    if (node) node.nodeValue = text;
    else if (text) el.insertBefore(document.createTextNode(text), el.firstChild);
  }

  /* ---------- 곡 목록 그리기 (data/catalog.json → 화면의 목록 자리) ---------- */
  // 목록 종류: 곡 행(row) 또는 카드(card·tile)
  function rowKind(c) { return c.dataset.kind === 'card' || c.dataset.kind === 'tile' ? 'card' : 'row'; }
  function isCurrentNode(k) { return Array.prototype.some.call(k.classList, function (c) { return /--current$/.test(c); }); }

  // 목록 자리마다 복제할 행 모양(일반·재생 중)과 아티스트 카드 모양을 기억해 둠
  function setupLists() {
    document.querySelectorAll('[data-list]').forEach(function (box) {
      if (box.dataset.list === 'Genre') {
        box.className = 'stack-xs genre-track-list';
        box.dataset.kind = 'row';
        box.innerHTML = '<div class="track-row"><span class="track-no">01</span><div class="track-art"></div><a href="#Playing" class="track-main"><div class="text-title"></div><div class="caption"></div></a><span></span><span class="track-dur"></span><button aria-label="곡 좋아요" class="like-btn"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M12 21s-7.5-4.6-9.6-9.3C.9 8.3 3 4.5 6.7 4.5c2 0 3.4 1 5.3 3 1.9-2 3.3-3 5.3-3 3.7 0 5.8 3.8 4.3 7.2C19.5 16.4 12 21 12 21z"/></svg></button></div>';
      }
      var normal = null, current = null;
      Array.prototype.forEach.call(box.children, function (k) {
        if (isCurrentNode(k)) { if (!current) current = k; } else if (!normal) normal = k;
      });
      ensureTrackActions(normal); ensureTrackActions(current);
      tpl.set(box, { normal: normal && normal.cloneNode(true), current: current && current.cloneNode(true) });
    });
    document.querySelectorAll('[data-artists]').forEach(function (box) {
      if (box.children[0]) tpl.set(box, { normal: box.children[0].cloneNode(true) });
    });
  }

  // 이 목록에 보여 줄 곡들
  function listTracks(box) {
    var key = box.dataset.list, q = state.query.trim();
    switch (key) {
      case 'rail-Main': return distinctPlays() >= 3 ? (state.modelRecs || topTracks()).slice(0, 10) : [];   // 서로 다른 3곡을 듣기 전에는 추천 목록을 비움(첫 사용자는 1~2곡을 들어도 추천 없음)
      case 'HomeBallad': return topTracks().slice(0, 100);
      case 'Played': return playedTracks();   // 내 현황: 지금까지 들은 곡(최근 순)
      case 'upnext': return nextTracks(10);   // 다음 곡·추천곡 모두 10곡 (보고서의 Top-10 기준)
      case 'Search': return q ? searchTracks(q).slice(0, 4) : topTracks().slice(0, 4);
      case 'SearchSongs': return q ? searchTracks(q).slice(0, 60) : topTracks().slice(0, 12);
      case 'ArtistDetail': return tracksOfArtist(state.artist);
      case 'Genre': return tracksOfGenre(state.genre || (genreList[0] && genreList[0].name));
      case 'Library': case 'NewPlaylist': return likedTracks();
      case 'PlaylistDetail': {
        var playlist = activePlaylist();
        return playlist ? (playlist.trackIds || []).map(function (id) { return byId[id]; }).filter(Boolean) : [];
      }
    }
    return [];
  }

  // 곡 행 한 줄에 곡 정보 채우기 (비어 있는 장르는 생략)
  function fillRow(node, s, i) {
    node.dataset.id = s.id;
    var c = node.children;
    c[0].textContent = pad2(i + 1);
    paintArt(c[1], s);
    var d = c[2].children;
    d[0].textContent = s.title;
    d[1].textContent = [s.artist, s.genre].filter(Boolean).join(' · ');
    var duration = node.querySelector('.track-dur');
    var like = node.querySelector('.track-actions .like-btn, .track-actions .like-btn--on');
    if (duration) duration.textContent = mmss(s.duration);
    if (like) {
      like.setAttribute('aria-label', s.title + ' 좋아요');
      var sv = like.querySelector('svg');
      if (sv) sv.setAttribute('fill', s.liked ? 'currentColor' : 'none');
      like.style.color = s.liked ? '#3ddc97' : '#a0a0b4';
    }
  }
  // 카드 한 장에 곡 정보 채우기
  function fillCard(node, s) {
    node.dataset.id = s.id;
    var d = node.children;
    setLabel(d[0], '');   // 앨범 이미지 위에 장르 이름을 쓰지 않음
    paintArt(d[0], s, true);
    var fab = d[0].querySelector('a');
    if (fab) fab.setAttribute('aria-label', s.title + ' 재생');
    d[1].textContent = s.title;
    d[2].textContent = s.artist;
  }

  // 목록 자리를 데이터로 다시 그리기
  function renderLists(scope) {
    (scope || document).querySelectorAll('[data-list]').forEach(function (box) {
      var t = tpl.get(box); if (!t) return;
      var tracks = listTracks(box), card = rowKind(box) === 'card';
      var frag = document.createDocumentFragment();
      tracks.forEach(function (s, i) {
        var base = (s.id === state.current && t.current) ? t.current : (t.normal || t.current);
        if (!base) return;
        var node = base.cloneNode(true);
        if (card) fillCard(node, s); else fillRow(node, s, i);
        frag.appendChild(node);
      });
      box.textContent = '';
      if (!tracks.length && box.dataset.empty) {
        var note = document.createElement('div'); note.className = 'empty-note'; note.textContent = box.dataset.empty;
        frag.appendChild(note);
      }
      box.appendChild(frag);
      if (box.dataset.list === 'upnext') {
        document.querySelectorAll('[data-role=upnextCount]').forEach(function (count) { count.textContent = tracks.length + '곡'; });
      }
    });
  }

  // 아티스트 카드(검색): 검색어가 있으면 관련 아티스트, 없으면 곡이 많이 재생된 아티스트
  function renderArtists(scope) {
    (scope || document).querySelectorAll('[data-artists]').forEach(function (box) {
      var t = tpl.get(box); if (!t) return;
      var q = state.query.trim();
      var list = artistsOf(q ? searchTracks(q) : topTracks()).slice(0, box.dataset.artists === 'rail' ? 8 : 40);
      box.textContent = '';
      list.forEach(function (a) {
        var node = t.normal.cloneNode(true);
        node.dataset.artist = a.name;
        var d = node.children;
        paintArt(d[0], a.first);
        d[1].textContent = a.name;
        d[2].textContent = '아티스트 · ' + a.tracks.length + '곡';
        box.appendChild(node);
      });
      if (!list.length) { var n = document.createElement('div'); n.className = 'empty-note'; n.textContent = '일치하는 아티스트가 없어요'; box.appendChild(n); }
    });
  }

  // 화면 속 제목·설명 글자 갱신 (검색 결과 수, 아티스트·장르 상세 머리말)
  function setRole(role, text) { document.querySelectorAll('[data-role="' + role + '"]').forEach(function (e) { e.textContent = text; }); }
  function genreChip(g) { var a = document.createElement('a'); a.href = '#Genre'; a.className = 'filter-chip'; a.dataset.genre = g.name; a.textContent = g.name; return a; }
  function renderTexts() {
    var q = state.query.trim(), n = q ? searchTracks(q).length : 0, na = q ? artistsOf(searchTracks(q)).length : 0;
    setRole('songSub', q ? '"' + q + '" 검색 결과 · ' + n + '곡' : '많이 들은 곡');
    setRole('artistSub', q ? '"' + q + '"와 관련된 아티스트 ' + na + '팀' : '곡이 많이 재생된 아티스트');
    // 아티스트 상세
    if (!state.artist && data.songs.length) state.artist = topTracks()[0].artist;
    var at = tracksOfArtist(state.artist);
    setRole('artistName', state.artist);
    setRole('artistMeta', '곡 ' + at.length + '개');
    document.querySelectorAll('[data-role=artistArt]').forEach(function (e) { if (at[0]) paintArt(e, at[0]); });
    // 장르 상세
    if (!state.genre && genreList.length) state.genre = genreList[0].name;
    var gt = tracksOfGenre(state.genre);
    setRole('genreName', state.genre);
    setRole('genreMeta', gt.length ? '곡 ' + gt.length + '곡' : '이 장르의 곡이 아직 없어요');
    var genre = genreDef(state.genre);
    document.querySelectorAll('.genre-hero').forEach(function (hero) {
      hero.style.background = 'var(--bg)';
    });
    document.querySelectorAll('[data-role=genreName]').forEach(function (name) {
      name.style.color = genre && genre.color ? genre.color : 'var(--text)';
    });
    // 검색의 장르 탭: 검색어와 이름이 맞는 장르
    var gm = q ? genreList.filter(function (g) { return norm(g.name).indexOf(norm(q)) > -1 || (g.tags || []).some(function (t) { return t.indexOf(norm(q)) > -1; }); }) : [];
    setRole('genreTitle', q ? (gm.length ? '"' + q + '"와 일치하는 장르' : '"' + q + '"와 일치하는 장르가 없어요') : '장르를 골라 보세요');
    setRole('genreSub', gm.length ? '장르를 누르면 곡을 볼 수 있어요' : '곡이나 아티스트 탭에서는 결과를 볼 수 있어요. 이런 장르는 어때요?');
    // 검색 '전체' 화면의 장르 칸: 일치하는 장르 칩, 없으면 안내 문구(아티스트 칸과 같은 스타일)
    document.querySelectorAll('[data-genre-result]').forEach(function (box) {
      box.textContent = '';
      if (!q) return;
      if (!gm.length) { var n = document.createElement('div'); n.className = 'empty-note'; n.textContent = '일치하는 장르가 없어요'; box.appendChild(n); return; }
      gm.forEach(function (g) { box.appendChild(genreChip(g)); });
    });
    document.querySelectorAll('[data-role=genreChips]').forEach(function (box) {
      box.textContent = '';
      (gm.length ? gm : genreList.slice(0, 3)).forEach(function (g) {
        var a = document.createElement('a'); a.href = '#Genre'; a.className = 'filter-chip'; a.dataset.genre = g.name; a.textContent = g.name; box.appendChild(a);
      });
    });
  }
  // 곡 목록·아티스트·글자를 한꺼번에 다시 그림
  function renderAll(scope) { renderLists(scope); renderArtists(scope); renderTexts(); renderCredit(); }

  /* ---------- 재생 상태 → 화면 ---------- */
  // 재생바에 보일 두 번째 줄: 불러오는 중·오류가 아니면 아티스트
  function statusText(s) {
    if (state.status === 'error') return '재생할 수 없는 곡이에요';
    if (state.status === 'loading') return '불러오는 중…';
    return s ? s.artist : '';
  }
  // LP 회전: 재생 시작 시 스틱 이동(600ms)이 끝난 뒤에 시작, 멈출 때는 바로 정지
  var lpSpinTimer = null, lpSpinWanted = false;
  function syncLpSpin(on) {
    if (on === lpSpinWanted) return;
    lpSpinWanted = on;
    clearTimeout(lpSpinTimer); lpSpinTimer = null;
    if (!on) { document.body.classList.remove('lp-spin'); return; }
    lpSpinTimer = setTimeout(function () { lpSpinTimer = null; if (lpSpinWanted) document.body.classList.add('lp-spin'); }, 600);
  }
  // 진행 막대·시간·재생 버튼·곡 정보 등 상태 반영
  function render() {
    var sec = document.getElementById(cur()); if (!sec) return;
    var D = dur(), s = song();
    document.body.classList.toggle('paused', !state.playing);
    document.body.classList.toggle('arm-on', !!state.playing); // LP 스틱·받침: 재생 중일 때만 LP 위로
    syncLpSpin(!!state.playing);
    document.body.classList.toggle('player-off', !state.started); // 곡을 고르기 전에는 재생바를 숨김
    document.body.classList.toggle('no-current-track', !s);
    document.body.classList.toggle('player-excluded', /^(Status|Profile)$/.test(sec.id));
    document.body.classList.toggle('no-header', /^(Login|LoginEmail|SignupDone)$/.test(sec.id));
    var pct = Math.min(100, state.t / D * 100).toFixed(1) + '%';
    sec.querySelectorAll('[data-role=progress]').forEach(function (p) { p.firstElementChild.style.width = pct; });
    sec.querySelectorAll('[data-role=cur]').forEach(function (e) { e.textContent = mmss(state.t); });
    sec.querySelectorAll('[data-role=tot]').forEach(function (e) { e.textContent = s ? mmss(D) : '0:00'; });
    sec.querySelectorAll('[data-role=curTot]').forEach(function (e) { e.textContent = mmss(state.t) + ' / ' + (s ? mmss(D) : '0:00'); });
    sec.querySelectorAll('[data-role=npTitle]').forEach(function (e) { e.textContent = s ? s.title : (e.dataset.emptyText || '재생할 곡을 골라 주세요'); }); // 빈 상태 문구는 playing.html 의 data-empty-text (미니 플레이어는 기본 문구)
    sec.querySelectorAll('[data-role=upnextTitle]').forEach(function (e) { e.textContent = s ? (e.dataset.title || '다음 곡') : (distinctPlays() >= 3 ? (e.dataset.emptyTitle || '추천곡') : (e.dataset.allTitle || '전체 곡')); }); // 곡을 고르기 전: 추천이 있으면 '추천곡', 없으면 '전체 곡'
    sec.querySelectorAll('[data-role=npArtist]').forEach(function (e) { e.textContent = statusText(s); });
    sec.querySelectorAll('[data-role=npArtistLine]').forEach(function (e) { e.textContent = s ? s.artist : ''; });
    sec.querySelectorAll('[data-role=npAlbum]').forEach(function (e) { e.textContent = s && s.album ? (e.dataset.prefix || '앨범: ') + s.album : ''; });
    sec.querySelectorAll('[data-role=npGenre]').forEach(function (e) {
      var genre = s && genreList.filter(function (g) { return g.name === s.primaryGenre; })[0];   // 곡마다 대표 장르 하나
      e.textContent = genre ? genre.name : '';
      e.style.backgroundColor = genre ? genre.color : '';
      e.style.color = genre ? '#0E0E12' : '';
    });
    sec.querySelectorAll('button').forEach(function (b) {
      var l = b.getAttribute('aria-label') || '';
      if (l === '일시정지' || l === '재생') {
        b.setAttribute('aria-label', state.playing ? '일시정지' : '재생');
        var sv = b.querySelector('svg'); if (sv) sv.innerHTML = state.playing ? PAUSE_ICON : PLAY_ICON;
      }
    });
    sec.querySelectorAll('.like-circle').forEach(function (b) { // 재생 화면의 하트
      var on = !!(s && s.liked), sv = b.querySelector('svg');
      if (sv) sv.setAttribute('fill', on ? 'currentColor' : 'none');
      b.style.color = on ? '#3ddc97' : '#a0a0b4';
    });
  }

  // 재생 화면의 곡 정보: 아티스트·앨범·장르, Jamendo 곡 페이지와 라이선스 링크, 가사 (다운로드 기능은 없음)
  function renderCredit() {
    document.querySelectorAll('[data-credit]').forEach(function (box) {
      box.textContent = '';
      var s = song(); if (!s) return;
      var links = document.createElement('div'); links.className = 'credit-links';
      var lyrics = document.createElement('button'); lyrics.type = 'button'; lyrics.className = 'credit-link lyrics-trigger'; lyrics.dataset.lyricsOpen = 'true';
      lyrics.textContent = s.lyrics ? (box.dataset.lyricsLabel || '가사') : (box.dataset.noLyricsLabel || '가사 없음'); lyrics.disabled = !s.lyrics;
      links.appendChild(lyrics);
      [[box.dataset.licenseLabel || '라이선스 보기', s.license]].forEach(function (x) {
        if (!isHttp(x[1])) return;
        var a = document.createElement('a'); a.className = 'credit-link'; a.href = x[1]; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = x[0];
        links.appendChild(a);
      });
      box.appendChild(links);
      var lyricsText = document.querySelector('#Playing [data-role=lyricsText]');
      if (lyricsText) lyricsText.textContent = s.lyrics || lyricsText.dataset.emptyText || '가사가 등록되어 있지 않습니다.';
    });
  }

  /* ---------- 닉네임 랜덤 생성 ---------- */
  var NICK_ADJ = ['잔잔한', '따뜻한', '느긋한', '반짝이는', '포근한', '경쾌한', '새벽의', '푸른', '고요한', '설레는'];
  var NICK_NOUN = ['리스너', '멜로디', '음악친구', '플레이어', '드라이버', '탐험가', '수집가', '여행자'];
  // 형용사 + 명사 + 숫자 닉네임
  function randomNickname() {
    var pick = function (a) { return a[Math.floor(Math.random() * a.length)]; };
    return pick(NICK_ADJ) + ' ' + pick(NICK_NOUN) + ' ' + (10 + Math.floor(Math.random() * 90));
  }
  // 닉네임 입력창
  function nickInput() { return document.getElementById('nickname'); }
  // 닉네임 새로 뽑기
  function rollNickname() { var i = nickInput(); if (i) { i.value = randomNickname(); state.nickname = i.value; } }

  /* 로그인 폼 높이를 재서 CSS 변수로 전달: 회원가입 폼을 로그인 폼과 같은 위치에서 시작시키는 데 사용 */
  function measureLogin() {
    var s = document.getElementById('LoginEmail'), f = s && s.querySelector('.auth-form');
    if (!f) return;
    var wasHidden = s.hidden;
    if (wasHidden) { s.hidden = false; s.style.visibility = 'hidden'; }
    var h = f.scrollHeight;
    if (wasHidden) { s.hidden = true; s.style.visibility = ''; }
    document.documentElement.style.setProperty('--login-h', h + 'px');
  }


  /* ---------- 내 장르 지도: 들은 곡의 장르 비율을 도넛(원형 바)과 퍼센트로 보여 줌 ---------- */
  // 들은 곡 기록: {곡 id: 장르}. 같은 곡을 여러 번 들어도 1곡으로 센다. 장르 지도·3곡 갱신 모두 이 기록 하나만 사용.
  var playedIds = {};
  try { playedIds = JSON.parse(localStorage.getItem('ms-played-ids') || '{}') || {}; } catch (e) { playedIds = {}; }
  Object.keys(playedIds).forEach(function (id) { if (typeof playedIds[id] !== 'string') delete playedIds[id]; });   // 예전 형식의 기록은 버림
  try { localStorage.removeItem('ms-genre-plays'); } catch (e) {}
  // 들은 순서(최근 곡이 앞): 내 현황의 '지금까지 들은 곡' 목록용. 곡 id 배열
  var playHistory = [];
  try { playHistory = JSON.parse(localStorage.getItem('ms-play-history') || '[]'); } catch (e) { playHistory = []; }
  if (!Array.isArray(playHistory)) playHistory = [];
  function playedTracks() {
    var seen = {}, out = [];
    function add(id) { id = +id; if (seen[id] || !byId[id] || playedIds[id] === undefined) return; seen[id] = 1; out.push(byId[id]); }
    playHistory.forEach(add);
    Object.keys(playedIds).forEach(add);   // 순서 기록이 없는 예전 기록도 포함
    return out;
  }
  // 개인 추천 스냅샷: 마지막으로 추천을 계산한 시점의 들은 곡 수(at)와 추천 곡 id 목록. 새로고침해도 같은 목록이 유지되고, 3곡 더 들을 때마다 새로 계산
  var recSnap = null;
  try { recSnap = JSON.parse(localStorage.getItem('ms-recs') || 'null'); } catch (e) { recSnap = null; }
  if (!recSnap || !Array.isArray(recSnap.ids) || typeof recSnap.at !== 'number') recSnap = null;
  function saveRecSnap() { try { if (recSnap) localStorage.setItem('ms-recs', JSON.stringify(recSnap)); else localStorage.removeItem('ms-recs'); } catch (e) {} }
  var genrePlays = {};   // 장르 -> 들은 서로 다른 곡 수 (playedIds 에서 계산)
  function rebuildGenrePlays() {
    genrePlays = {};
    Object.keys(playedIds).forEach(function (id) { genrePlays[playedIds[id]] = (genrePlays[playedIds[id]] || 0) + 1; });
  }
  rebuildGenrePlays();
  function distinctPlays() { return Object.keys(playedIds).length; }
  // 곡의 대표 장르: 태그 순서대로 보아 처음 나오는 장르. 단, '기타' 그룹 태그는 건너뛰고 다음 태그를 봄(다른 장르 태그가 하나도 없을 때만 기타)
  function genreOf(s) {
    var etc = false;
    for (var i = 0; i < (s.genres || []).length; i++) {
      for (var j = 0; j < genreList.length; j++) if (genreList[j].tags.indexOf(s.genres[i]) !== -1) {
        if (genreList[j].name !== '기타') return genreList[j].name;
        etc = true;
      }
    }
    return '기타';
  }
  function recordPlay(s) {
    var g = genreOf(s);
    playedIds[s.id] = g;
    playHistory = [s.id].concat(playHistory.filter(function (x) { return x !== s.id; })).slice(0, 500);
    try { localStorage.setItem('ms-play-history', JSON.stringify(playHistory)); } catch (e) {}
    rebuildGenrePlays();
    try { localStorage.setItem('ms-played-ids', JSON.stringify(playedIds)); } catch (e) {}
    renderGenreMap();
    renderLists();
    setRailSub(railSubDefault());
  }
  function genreShares() {
    var total = 0, rows = [];
    Object.keys(genrePlays).forEach(function (g) { total += genrePlays[g]; rows.push({ name: g, n: genrePlays[g] }); });
    rows.sort(function (a, b) { return b.n - a.n; });
    var ints = rows.map(function (r) { return Math.floor(r.n * 100 / total); }), left = 100 - ints.reduce(function (a, b) { return a + b; }, 0);
    rows.forEach(function (r, i) { r.fr = r.n * 100 / total - ints[i]; r.i = i; });
    rows.slice().sort(function (a, b) { return b.fr - a.fr; }).slice(0, left).forEach(function (r) { ints[r.i]++; }); // 합이 100%가 되도록 반올림
    rows.forEach(function (r, i) { r.pct = ints[i]; r.color = (genreList.filter(function (g) { return g.name === r.name; })[0] || {}).color || '#8a8aa0'; });
    return { total: total, rows: rows };
  }
  function donutSvg(rows, total, size) {
    var R = 40, C = 2 * Math.PI * R, off = 0;
    var segs = rows.map(function (r) {
      var len = C * r.n / total, el = '<circle cx="50" cy="50" r="' + R + '" fill="none" stroke="' + r.color + '" stroke-width="14" stroke-dasharray="' + (rows.length > 1 ? Math.max(len - 1.5, 0.1) : len) + ' ' + C + '" stroke-dashoffset="' + (-off) + '" transform="rotate(-90 50 50)"><title>' + r.name + ' ' + r.pct + '%</title></circle>';
      off += len; return el;
    }).join('');
    return '<svg viewBox="0 0 100 100" width="' + size + '" height="' + size + '" role="img" aria-label="장르 비율: ' + rows.map(function (r) { return r.name + ' ' + r.pct + '%'; }).join(', ') + '">' +
      '<circle cx="50" cy="50" r="' + R + '" fill="none" stroke="#2a2a36" stroke-width="14"/>' + segs +
      '<text x="50" y="48" text-anchor="middle" fill="#f4f4f8" font-size="14" font-weight="700">' + total + '</text><text x="50" y="62" text-anchor="middle" fill="#a0a0b4" font-size="8">곡 들음</text></svg>';
  }
  function legendHtml(rows) {
    return rows.map(function (r) { return '<li><span class="dot" style="background:' + r.color + '"></span><span class="gname">' + r.name + '</span><span class="gpct">' + r.pct + '%</span></li>'; }).join('');
  }
  function renderGenreMap() {
    var sh = genreShares(), has = sh.total > 0;
    document.querySelectorAll('[data-donut]').forEach(function (box) {
      box.innerHTML = has ? donutSvg(sh.rows, sh.total, 150) : donutSvg([], 0, 150).replace('>0<', '>0<');
      var note = box.parentNode.querySelector('[data-donut-note]');
      if (note) { note.innerHTML = has ? '<ul class="donut-legend">' + legendHtml(sh.rows.slice(0, 4)) + '</ul>' : '아직 들은 곡이 없어요'; }
    });
    document.querySelectorAll('[data-donut-status]').forEach(function (box) {
      var panel = box.closest('.panel');
      if (panel) panel.querySelectorAll('.headline, .page-sub').forEach(function (e) { e.hidden = has; });
      box.innerHTML = has ? '<div class="donut-status">' + donutSvg(sh.rows, sh.total, 200) + '<ul class="donut-legend">' + legendHtml(sh.rows) + '</ul></div>' : '';
    });
  }
  /* ---------- 회원가입 2단계: 다음 → 장르 선택 → 시작하기(로그인으로 이동) ---------- */
  var GENRE_MAX = 3; // 가입 시 고를 수 있는 장르 수(최대)
  function genreCount() { return document.querySelectorAll('#Login .chip.is-on').length; }
  // 장르를 하나도 안 골랐으면 '시작하기'를 누를 수 없게 함
  function updateStart() {
    var btn = document.getElementById('signupNext');
    if (btn) btn.setAttribute('aria-disabled', btn.dataset.step === '2' && genreCount() < 1);
  }
  function setSignupStep(n) {
    var sec = document.getElementById('Login'), btn = document.getElementById('signupNext');
    if (!sec || !btn) return;
    sec.querySelectorAll('.signup-step').forEach(function (s) { s.hidden = (+s.dataset.step !== n); });
    btn.dataset.step = n;
    btn.textContent = n === 1 ? '다음' : '시작하기';
    // 2단계 '시작하기': 구글로 로그인한 사용자는 바로 홈으로, 그 밖에는 기존처럼 로그인 화면으로
    btn.setAttribute('href', n === 1 ? '#' : (window.MusicSync && window.MusicSync.google ? '#Main' : '#LoginEmail'));
    updateStart();
  }

  // 공통 사이드바(page/sidebar.html)를 각 화면의 자리(data-sidebar)에 복사해 넣음
  function buildSidebars(tplHTML) {
    document.querySelectorAll('[data-sidebar]').forEach(function (ph) {
      var box = document.createElement('div');
      box.innerHTML = tplHTML;
      var sb = box.querySelector('.sidebar'), p = ph.dataset;
      // 활성 메뉴 표시 · 홈 링크 대상 (보상 팝업 뒤 화면은 링크 비활성)
      sb.querySelectorAll('[data-nav]').forEach(function (a) {
        if (a.dataset.nav === 'home') a.setAttribute('href', p.home || '#Main');
        if (p.disabled !== undefined) a.setAttribute('href', '#');
        if (a.dataset.nav === p.active) a.className = 'nav-item--active';
        a.removeAttribute('data-nav');
      });
      // 프로필 카드: 상태(initial / done / hint)에 맞는 부분만 남김
      sb.querySelectorAll('[data-show]').forEach(function (e) {
        if (e.dataset.show.split(' ').indexOf(p.profile) < 0) e.remove(); else e.removeAttribute('data-show');
      });
      if (p.scroll !== undefined) sb.classList.add('sidebar--scroll');
      // 팝업 뒤 화면: 장르 지도 카드는 링크가 아닌 일반 상자
      if (p.disabled !== undefined) {
        sb.querySelectorAll('a.map-card').forEach(function (a) {
          var d = document.createElement('div');
          d.className = a.className + '--div';
          while (a.firstChild) d.appendChild(a.firstChild);
          a.replaceWith(d);
        });
      }
      ph.replaceWith(sb);
    });
  }

  // '앙상블' 글자: 새로고침처럼 처음 상태의 홈으로 (로그인 화면에서는 로그인 화면으로)
  function goHome() {
    var home = /^(Login|LoginEmail|SignupDone)$/.test(cur()) ? '#LoginEmail' : '#Main';
    location.hash = home;
    location.reload();
  }

  // 검색어 지우기 버튼 표시
  function syncSearch() {
    var clr = document.getElementById('searchClear');
    if (clr) clr.hidden = state.query === '';
  }

  // 사이드바 접기/펴기 (상태는 브라우저에 저장, 사용할 수 없으면 무시)
  function setSidebar(collapsed) {
    document.body.classList.toggle('sidebar-collapsed', collapsed);
    document.querySelectorAll('.side-toggle').forEach(function (b) {
      b.setAttribute('aria-expanded', !collapsed);
      b.setAttribute('aria-label', collapsed ? '사이드바 펴기' : '사이드바 접기');
      b.setAttribute('title', collapsed ? '사이드바 펴기' : '사이드바 접기');
    });
    try { localStorage.setItem('ms-sidebar', collapsed ? '1' : '0'); } catch (e) {}
  }
  function initSidebar() {
    var saved = window.innerWidth <= 900; // 저장된 값이 없으면 좁은 화면은 접힌 막대로 시작
    try { var v = localStorage.getItem('ms-sidebar'); if (v !== null) saved = v === '1'; } catch (e) {}
    setSidebar(saved);
  }

  // 위쪽 알림창 (2.8초 뒤 사라짐)
  var toastTimer = null;
  function showToast(msg) {
    var box = document.getElementById('appToast'), txt = document.getElementById('appToastText');
    if (!box || !txt) return;
    txt.textContent = msg;
    box.hidden = false;
    box.style.animation = 'none'; void box.offsetWidth; box.style.animation = ''; // 연속으로 떠도 다시 나타나게
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { box.hidden = true; }, 2800);
  }

  // 장르 목록(data/genres.json)으로 회원가입 칩과 검색의 장르 타일을 그림
  function renderGenres(list) {
    document.querySelectorAll('[data-genres="chips"]').forEach(function (box) {
      box.textContent = '';
      list.forEach(function (g) {
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'chip'; b.setAttribute('aria-pressed', 'false'); b.textContent = g.name;
        box.appendChild(b);
      });
    });
    document.querySelectorAll('[data-genres="tiles"]').forEach(function (box) {
      box.textContent = '';
      list.forEach(function (g) {
        var a = document.createElement('a');
        a.href = '#Genre'; a.className = 'genre-tile--' + (g.tile || 'a'); a.dataset.genre = g.name;
        if (g.color) { a.style.background = 'linear-gradient(135deg, rgba(255,255,255,.14), rgba(255,255,255,0) 58%, rgba(0,0,0,.08)), ' + colorWithAlpha(g.color, 0.95); a.style.color = '#0e0e12'; }
        a.appendChild(document.createTextNode(g.name));
        if (g.badge) {
          var t = document.createElement('span');
          t.className = g.isNew ? 'tile-tag--new' : 'tile-tag'; t.textContent = g.badge;
          a.appendChild(t);
        }
        var c = document.createElement('span'); c.className = 'tile-circle'; a.appendChild(c);
        box.appendChild(a);
      });
    });
  }

  // ---------- 최근 검색어: 엔터로 검색한 단어를 저장(최대 8개), x로 삭제 ----------
  var RECENT_MAX = 8;
  var recent = [];
  try { recent = JSON.parse(localStorage.getItem('ms-recent') || '[]'); } catch (e) {}
  function saveRecent() { try { localStorage.setItem('ms-recent', JSON.stringify(recent)); } catch (e) {} }
  function addRecent(q) {
    q = q.trim();
    if (!q) return;
    recent = [q].concat(recent.filter(function (x) { return x !== q; })).slice(0, RECENT_MAX);
    saveRecent(); renderRecent();
  }
  function renderRecent() {
    document.querySelectorAll('[data-recent-list]').forEach(function (box) {
      box.textContent = '';
      recent.forEach(function (term) {
        var chip = document.createElement('span'); chip.className = 'recent-chip';
        var t = document.createElement('span'); t.className = 'recent-term'; t.dataset.term = term; t.textContent = term;
        var x = document.createElement('button'); x.type = 'button'; x.className = 'recent-x'; x.dataset.term = term;
        x.setAttribute('aria-label', term + ' 검색어 삭제');
        x.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#a0a0b4" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
        chip.appendChild(t); chip.appendChild(x); box.appendChild(chip);
      });
    });
    document.querySelectorAll('[data-recent]').forEach(function (s) { s.hidden = recent.length === 0; });
  }

  // 끌어서 옆으로 넘기기: data-drag-scroll 영역을 마우스로 잡고 좌우로 끌면 스크롤됨 (끌었을 때는 클릭으로 처리하지 않음)
  (function () {
    var box = null, startX = 0, startLeft = 0, moved = false;
    document.addEventListener('mousedown', function (e) {
      if (e.button !== 0) return;
      box = e.target.closest('[data-drag-scroll]');
      if (!box) return;
      startX = e.clientX; startLeft = box.scrollLeft; moved = false;
    });
    document.addEventListener('mousemove', function (e) {
      if (!box) return;
      var dx = e.clientX - startX;
      if (!moved && Math.abs(dx) > 5) { moved = true; box.classList.add('is-dragging'); }
      if (moved) box.scrollLeft = startLeft - dx;
    });
    function end() { if (box) box.classList.remove('is-dragging'); box = null; }
    document.addEventListener('mouseup', function () { var wasMoved = moved; end(); if (wasMoved) setTimeout(function () { moved = false; }, 0); });
    document.addEventListener('click', function (e) { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
  })();

  // 주소에 맞는 화면 보이기
  function route() {
    var id = cur(), el = document.getElementById(id);
    if (!el) return; // 페이지 불러오기 전
    // 로그인해야만 앱 화면을 볼 수 있음: 로그인 안 했으면 로그인 화면으로, 로그인했는데 로그인·가입 화면이면 홈으로
    if (!authPending && !state.authUser && !/^(Login|LoginEmail|LoginError)$/.test(id)) { location.hash = '#LoginEmail'; return; }
    if (state.authUser && !signingUp && /^(Login|LoginEmail|SignupDone)$/.test(id)) { location.hash = '#Main'; return; }
    document.body.classList.toggle('on-player-screen', id === 'Playing');
    if (id !== 'Profile') {
      var editingName = document.querySelector('#Profile [data-profile-name-input]');
      if (editingName && !editingName.hidden) finishNicknameEdit(editingName, false);
    }
    var searchBox = document.getElementById('globalSearch'); searchBox = (searchBox && (document.activeElement === searchBox || searchBox.dataset.typing === '1')) ? searchBox : null; // 검색창에 입력 중이었는지
    document.querySelectorAll('.screen').forEach(function (s) { s.hidden = (s !== el); });
    if (!/^(Status|Profile)$/.test(id) && !el.querySelector('.mini-player')) {
      var playerTemplate = document.querySelector('.mini-player');
      var screenRoot = el.querySelector('.screen-root');
      if (playerTemplate && screenRoot) screenRoot.appendChild(playerTemplate.cloneNode(true));
    }
    // 검색 결과 화면인데 검색어가 없으면(새로고침 등) 기본 화면(검색 메인)으로. 브라우저가 복원한 검색창 글자가 있으면 그걸 검색어로 씀
    if (SEARCH.test(id) && id !== 'SearchHome' && !state.query.trim()) {
      var restored = document.getElementById('globalSearch');
      if (restored && restored.value.trim()) state.query = restored.value.trim();
      else { location.hash = '#SearchHome'; return; }
    }
    if (id === 'SearchHome') { state.query = ''; var gs = document.getElementById('globalSearch'); if (gs && gs.value !== '') gs.value = ''; } // 검색 메인은 빈 검색창으로
    syncSearch();
    if (id === 'Login' && nickInput() && !nickInput().value.trim()) rollNickname();
    if (id === 'SignupDone' && state.nickname) {
      el.querySelectorAll('div').forEach(function (d) {
        if (!d.children.length && /님, 반가워요$/.test(d.textContent)) d.textContent = state.nickname + '님, 반가워요';
      });
    }
    if (!/^(Login|LoginEmail|SignupDone)$/.test(id)) loadRecs(false);   // 어느 화면에서 새로고침해도 이 사용자의 추천을 불러옴(같은 장르면 서버 추천은 항상 동일)
    if (id === 'Login') {
      el.querySelectorAll('.chip').forEach(function (c) { c.classList.remove('is-on'); c.setAttribute('aria-pressed', 'false'); });
      setSignupStep(1);
    }
    measureLogin();
    renderAll(el);
    renderUserPlaylists();
    if (id === 'Profile') renderProfile();
    if (id === 'PlaylistDetail') renderPlaylistDetail();
    window.scrollTo(0, 0);
    var ct = el.querySelector('.content'); if (ct) ct.scrollTop = 0; // 화면을 바꾸면 본문 스크롤도 맨 위로
    render();
    if (searchBox) { searchBox.focus(); }
    if (searchBox) setTimeout(function () { searchBox.dataset.typing = '0'; }, 300);
    // 글자를 다 지워 검색 메인으로 가도 커서는 검색창에 그대로 둠
  }

  /* ---------- 재생: 실제 Jamendo 음원을 <audio> 하나로 재생 (한 번에 한 곡) ---------- */
  var SPEAKER_MUTED = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M17 9.5l5 5M22 9.5l-5 5"/></svg>';
  var SPEAKER = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>';

  function onPlayError(err) {
    if (err && err.name === 'AbortError') return; // 다른 곡을 고르면서 이전 재생이 취소된 경우
    state.playing = false;
    if (err && err.name === 'NotAllowedError') state.status = 'idle'; // 브라우저가 소리 재생을 막음: 재생 버튼을 직접 눌러야 함
    else { state.status = 'error'; showToast('이 곡은 재생할 수 없어요. 다른 곡을 골라 보세요.'); }
    render();
    schedulePlayerHide();
  }
  function startAudio() { var p = audio.play(); if (p && p.catch) p.catch(onPlayError); }

  // 곡 재생 시작 (사용자가 곡을 눌렀을 때만 호출됨 — 저절로 소리가 나지 않음)
  // 추천이 생긴 뒤(서로 다른 3곡 이후)에는 다음 곡이 추천 모델의 추천 목록(10곡)을 따름: 현재 곡 + 추천곡(현재 곡 제외)
  // '전체 재생'(fullQueue)처럼 순서가 정해진 목록은 그대로 둠
  function applyRecQueue() {
    if (state.fullQueue || distinctPlays() < 3 || !state.modelRecs || !state.modelRecs.length) return;
    var rest = state.modelRecs.slice(0, 10).map(function (t) { return t.id; }).filter(function (x) { return x !== state.current; });
    state.ctx = [state.current].concat(rest);
  }
  function playSong(id, ctx, fullQueue) {
    var s = byId[id]; if (!s) return;
    keepPlayerVisible();
    state.current = id; state.t = 0; state.dur = 0; state.started = true; state.status = 'loading'; state.playing = true;
    if (ctx) state.ctx = ctx;
    state.fullQueue = !!fullQueue;
    recordPlay(s);
    onPlayed(id);
    applyRecQueue();
    setCover(s);
    audio.src = s.audio; // 주소의 쿼리 매개변수는 그대로 사용
    startAudio();
    renderAll(); render();
  }
  // 재생/일시정지
  function togglePlay() {
    if (!state.current) return;
    if (audio.paused) { keepPlayerVisible(); if (audio.readyState < 3) { state.status = 'loading'; render(); } startAudio(); } else audio.pause();
  }
  // 다음(1)/이전(-1) 곡
  function step(dir) {
    var ids = state.ctx && state.ctx.length ? state.ctx : topTracks().map(function (s) { return s.id; });
    var i = ids.indexOf(state.current);
    var next = i + dir;
    if (state.fullQueue && (next < 0 || next >= ids.length)) return;
    playSong(ids[(next + ids.length) % ids.length], ids, state.fullQueue);
  }
  // 진행 막대를 눌러 이동 (frac: 0~1)
  function seekTo(frac) {
    if (!state.current) return;
    var t = Math.max(0, Math.min(1, frac)) * dur();
    try { audio.currentTime = t; } catch (e) {}
    state.t = t; render();
  }
  // 모든 볼륨 막대를 현재 볼륨에 맞춤
  function syncVolume() {
    document.querySelectorAll('.vol-range').forEach(function (r) { r.value = audio.muted ? 0 : Math.round(audio.volume * 100); });
    var silent = audio.muted || audio.volume === 0;
    document.querySelectorAll('.vol-btn').forEach(function (b) { b.setAttribute('aria-label', '볼륨 조절'); b.setAttribute('aria-haspopup', 'true'); b.innerHTML = silent ? SPEAKER_MUTED : SPEAKER; });
  }
  function setupAudio() {
    audio = document.getElementById('audio');
    audio.preload = 'none';
    var vol = 0.8;
    try { var v = localStorage.getItem('ms-volume'); if (v !== null) vol = Math.max(0, Math.min(1, +v)); } catch (e) {}
    audio.volume = vol;
    audio.addEventListener('playing', function () { keepPlayerVisible(); state.playing = true; state.status = 'playing'; render(); });
    audio.addEventListener('pause', function () { if (!audio.ended) { state.playing = false; render(); schedulePlayerHide(); } });
    audio.addEventListener('waiting', function () { state.playing = false; state.status = 'loading'; render(); });
    audio.addEventListener('canplay', function () { if (state.status === 'loading') { state.status = state.playing ? 'playing' : 'idle'; render(); } });
    audio.addEventListener('durationchange', function () { if (isFinite(audio.duration) && audio.duration > 0) { state.dur = audio.duration; render(); } });
    audio.addEventListener('timeupdate', function () { state.t = audio.currentTime; render(); });
    audio.addEventListener('ended', function () {
      state.playing = false;
      var ids = state.ctx || [];
      if (state.fullQueue && ids.indexOf(state.current) === ids.length - 1) {
        state.t = 0; state.status = 'idle'; render();
      } else if (ids.length > 1) step(1); else { state.t = 0; render(); }
      schedulePlayerHide();
    });
    audio.addEventListener('error', function () {
      if (!audio.getAttribute('src')) return;
      state.playing = false; state.status = 'error';
      showToast('이 곡은 재생할 수 없어요. 다른 곡을 골라 보세요.');
      render();
      schedulePlayerHide();
    });
    audio.addEventListener('volumechange', syncVolume);
    // 재생바마다 볼륨(음소거 버튼 + 막대)을 넣음
    document.querySelectorAll('.mini-player').forEach(function (bar) {
      // 볼륨: 스피커 버튼만 보이고, 누르면 버튼 위쪽으로 세로 조절 막대가 열림
      var w = document.createElement('div'); w.className = 'vol';
      var b = document.createElement('button'); b.type = 'button'; b.className = 'vol-btn'; b.innerHTML = SPEAKER;
      var pop = document.createElement('div'); pop.className = 'vol-pop';
      var r = document.createElement('input'); r.type = 'range'; r.className = 'vol-range'; r.min = 0; r.max = 100; r.step = 1; r.setAttribute('aria-label', '볼륨');
      pop.appendChild(r); w.appendChild(b); w.appendChild(pop); bar.appendChild(w);
    });
    syncVolume();
  }

  /* ---------- 이벤트 ---------- */
  // 클릭: 회원가입 단계·칩·로고·좋아요·재생 버튼 처리
  document.addEventListener('click', function (e) {
    var colorOption = e.target.closest('.image-editor-color');
    if (colorOption && imageEditorState) {
      imageEditorState.hue = +colorOption.dataset.hue;
      imageEditorState.image = '';
      updateImageEditorPreview();
      return;
    }
    if (e.target.closest('.image-editor-upload')) { chooseEditorImage(); return; }
    if (e.target.closest('[data-image-editor-save]')) { saveImageEditor(); return; }
    if (e.target.closest('[data-image-editor-cancel]') || e.target.classList.contains('image-editor-backdrop')) {
      closeImageEditor();
      return;
    }
    var rx = e.target.closest('.recent-x');
    if (rx) { recent = recent.filter(function (x) { return x !== rx.dataset.term; }); saveRecent(); renderRecent(); return; }
    if (e.target.closest('[data-recent-clear]')) { e.preventDefault(); recent = []; try { localStorage.removeItem('ms-recent'); } catch (err) {} renderRecent(); return; }
    if (e.target.closest('[data-profile-genre-toggle]')) {
      profileGenresExpanded = !profileGenresExpanded;
      renderProfile();
      return;
    }
    var profileGenre = e.target.closest('[data-profile-genre]');
    if (profileGenre) { toggleProfileGenre(profileGenre.dataset.profileGenre); return; }
    if (e.target.closest('[data-profile-edit]')) { beginNicknameEdit(); return; }
    var profileAvatar = e.target.closest('.profile-avatar-upload');
    if (profileAvatar) { e.preventDefault(); openImageEditor('profile'); return; }
    var coverArt = e.target.closest('.playlist-cover-upload');
    if (coverArt) {
      e.preventDefault();
      e.stopPropagation();
      var index = +coverArt.dataset.playlistIndex;
      if (Number.isInteger(index) && userPlaylists[index]) openImageEditor('playlist', index);
      return;
    }
    var createPlaylist = e.target.closest('#NewPlaylist .btn-primary--half');
    if (createPlaylist) {
      e.preventDefault();
      var nameInput = document.querySelector('#NewPlaylist .modal input');
      var playlistName = nameInput ? nameInput.value.trim() : '';
      if (!playlistName) {
        if (nameInput) { nameInput.focus(); nameInput.setAttribute('aria-invalid', 'true'); }
        return;
      }
      var firstTrack = pendingNewPlaylistTrackId;
      userPlaylists.push({ name: playlistName, trackIds: firstTrack !== null ? [firstTrack] : [], colorHue: Math.floor(Math.random() * 360) });
      if (!saveUserPlaylists()) {
        userPlaylists.pop();
        showToast('플레이리스트를 저장하지 못했어요. 브라우저 저장 공간을 확인해 주세요.');
        return;
      }
      pendingNewPlaylistTrackId = null;
      renderUserPlaylists();
      if (firstTrack !== null) showToast('새 플레이리스트에 곡을 추가했어요.');
      location.hash = '#Library';
      return;
    }
    var pickerOption = e.target.closest('.playlist-picker-option');
    if (pickerOption) {
      var selectedPlaylist = userPlaylists[+pickerOption.dataset.playlistIndex];
      if (selectedPlaylist && playlistPickerTrackId !== null) {
        selectedPlaylist.trackIds = selectedPlaylist.trackIds || [];
        if (selectedPlaylist.trackIds.indexOf(playlistPickerTrackId) === -1) {
          selectedPlaylist.trackIds.push(playlistPickerTrackId);
          if (!saveUserPlaylists()) {
            selectedPlaylist.trackIds.pop();
            showToast('곡을 플레이리스트에 저장하지 못했어요. 브라우저 저장 공간을 확인해 주세요.');
          } else {
            renderUserPlaylists();
            renderPlaylistDetail();
            showToast('플레이리스트에 곡을 추가했어요.');
          }
        }
      }
      closePlaylistPicker();
      return;
    }
    // 팝업 안의 '새 플레이리스트 만들기' 링크: 화면이 바뀌기 전에 팝업을 닫아 만들기 화면과 겹치지 않게 함
    if (e.target.closest('.playlist-picker a[href]')) { pendingNewPlaylistTrackId = playlistPickerTrackId; closePlaylistPicker(); }
    if (e.target.closest('.playlist-picker-close') || e.target.classList.contains('playlist-picker-backdrop')) {
      closePlaylistPicker();
      return;
    }
    var addToPlaylist = e.target.closest('.add-to-playlist');
    if (addToPlaylist) {
      e.preventDefault();
      e.stopPropagation();
      var trackRow = addToPlaylist.closest('[data-id]');
      var trackId = trackRow ? +trackRow.dataset.id : (addToPlaylist.closest('#Playing .now-info') ? state.current : null);
      if (trackId !== null) showPlaylistPicker(trackId);
      return;
    }
    var rt = e.target.closest('.recent-term');
    if (rt) {
      state.query = rt.dataset.term;
      var gs2 = document.getElementById('globalSearch'); if (gs2) gs2.value = state.query;
      addRecent(state.query); syncSearch();
      if (SEARCH.test(cur())) renderAll(document.getElementById(cur())); else location.hash = '#Search';
      return;
    }
    var next = e.target.closest('#signupNext');
    if (next) {
      e.preventDefault();
      if (next.dataset.step === '1') { if (validateSignupFields()) setSignupStep(2); }
      else if (genreCount() >= 1) submitSignup();   // 장르를 1개 이상 골라야 시작
      return;
    }
    // 로그인 화면의 '로그인' 버튼: 이메일·비밀번호로 Firebase 로그인 (성공하면 데이터를 불러온 뒤 홈으로)
    var loginBtn = e.target.closest('[data-login-submit]');
    if (loginBtn) { e.preventDefault(); submitLogin(loginBtn); return; }
    if (e.target.closest('[data-logout]')) { e.preventDefault(); if (window.MusicAuth) window.MusicAuth.signOut(); return; }
    // 곡 목록에서 앨범 이미지를 눌러도 곡 제목을 누른 것과 같이 재생
    var rowArt = e.target.closest('[data-id] > [class^="track-art"]');
    if (rowArt) {
      var rowLink = rowArt.parentNode.querySelector('a.track-main');
      if (rowLink) { e.preventDefault(); rowLink.click(); return; }
    }
    var ad = e.target.closest('[data-artist]'); if (ad) state.artist = ad.dataset.artist;
    var gd = e.target.closest('[data-genre]'); if (gd) state.genre = gd.dataset.genre;
    var playlistCard = e.target.closest('.user-playlist-card');
    if (playlistCard) state.activePlaylistIndex = +playlistCard.dataset.playlistIndex;
    var a = e.target.closest('a');
    if (a) {
      var h = a.getAttribute('href');
      if (h === '#') { e.preventDefault(); return; }
      if (h === '#Playing') {
        var node = a.closest('[data-id]');
        var scr = document.getElementById(cur());
        if (node) { // 곡을 눌렀을 때만 재생 시작
          var box = node.closest('[data-list]');
          playSong(+node.dataset.id, Array.prototype.map.call(box.children, function (k) { return +k.dataset.id; }).filter(Boolean));
        } else if (a.hasAttribute('data-play-all') || a.hasAttribute('data-shuffle')) {
          var lb = scr && scr.querySelector('[data-list]');
          var ids = lb ? Array.prototype.map.call(lb.children, function (k) { return +k.dataset.id; }).filter(Boolean) : [];
          if (a.hasAttribute('data-shuffle')) {
            for (var i = ids.length - 1; i > 0; i--) {
              var j = Math.floor(Math.random() * (i + 1)), tmp = ids[i];
              ids[i] = ids[j]; ids[j] = tmp;
            }
          }
          if (ids.length) playSong(ids[0], ids, true); else e.preventDefault();
        } // 그 밖에(재생바 눌러 재생 화면 열기 등)는 재생 상태를 건드리지 않고 화면만 이동
      }
    }
    if (e.target.closest('.nick-roll')) { rollNickname(); return; }
    var chip = e.target.closest('.chip');
    if (chip) {
      var on = !chip.classList.contains('is-on');
      if (on && genreCount() >= GENRE_MAX) { // 한도 초과: 선택하지 않고 안내만 잠깐 강조
        var hint = chip.closest('.signup-step').querySelector('.hint');
        hint.classList.add('is-limit');
        setTimeout(function () { hint.classList.remove('is-limit'); }, 1200);
        return;
      }
      chip.classList.toggle('is-on', on);
      chip.setAttribute('aria-pressed', on);
      updateStart();
      return;
    }
    var bar = e.target.closest('[data-role=progress]');
    if (bar) { var rc = bar.getBoundingClientRect(); seekTo((e.clientX - rc.left) / rc.width); return; }
    var volBtn = e.target.closest('.vol-btn');
    if (volBtn) {   // 볼륨 버튼: 위쪽 조절 막대 열기·닫기
      var volBox = volBtn.closest('.vol'), wasOpen = volBox.classList.contains('is-open');
      document.querySelectorAll('.vol.is-open').forEach(function (v) { v.classList.remove('is-open'); });
      if (!wasOpen) volBox.classList.add('is-open');
      volBtn.setAttribute('aria-expanded', wasOpen ? 'false' : 'true');
      return;
    }
    if (!e.target.closest('.vol')) document.querySelectorAll('.vol.is-open').forEach(function (v) { v.classList.remove('is-open'); });
    if (e.target.closest('.side-toggle')) { setSidebar(!document.body.classList.contains('sidebar-collapsed')); return; }
    if (e.target.closest('#searchClear')) {
      state.query = ''; var gi = document.getElementById('globalSearch'); gi.value = ''; gi.focus(); syncSearch();
      if (SEARCH.test(cur())) location.hash = '#SearchHome';
      return;
    }
    if (e.target.closest('.brand-name')) { goHome(); return; } // 글자만 (로고 이미지는 제외)
    var b = e.target.closest('button');
    if (!b) return;
    var label = b.getAttribute('aria-label') || '';
    if (b.hasAttribute('data-lyrics-open')) {
      var lyricsDialog = document.querySelector('#Playing [data-role=lyricsDialog]');
      if (!b.disabled && lyricsDialog && !lyricsDialog.open) lyricsDialog.showModal();
      return;
    }
    if (/좋아요$/.test(label)) {
      e.preventDefault();
      var row = b.closest('[data-id]');
      var sg = row ? byId[+row.dataset.id] : (b.classList.contains('like-circle') ? song() : null);
      if (sg) {
        sg.liked = !sg.liked;
        if (!saveLikes()) {
          sg.liked = !sg.liked;
          showToast('좋아요를 저장하지 못했어요. 브라우저 저장 공간을 확인해 주세요.');
        }
        renderLists();
        render();
      }
      return;
    }
    if (label === '일시정지' || label === '재생') { togglePlay(); return; }
    if (label === '다음 곡') step(1);
    if (label === '이전 곡') step(-1);
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && document.querySelector('.image-editor-backdrop')) {
      closeImageEditor();
      return;
    }
    var nicknameInput = e.target.closest('[data-profile-name-input]');
    if (nicknameInput && e.key === 'Enter') {
      e.preventDefault();
      finishNicknameEdit(nicknameInput, false);
      return;
    }
    if (nicknameInput && e.key === 'Escape') {
      e.preventDefault();
      finishNicknameEdit(nicknameInput, true);
      return;
    }
    if ((e.key === 'Enter' || e.key === ' ') && e.target.closest('.profile-avatar-upload')) {
      e.preventDefault();
      openImageEditor('profile');
      return;
    }
    if ((e.key === 'Enter' || e.key === ' ') && e.target.closest('.playlist-cover-upload')) {
      e.preventDefault();
      var cover = e.target.closest('.playlist-cover-upload');
      var index = +cover.dataset.playlistIndex;
      if (Number.isInteger(index)) openImageEditor('playlist', index);
      return;
    }
    if (e.key === 'Escape') document.querySelectorAll('.vol.is-open').forEach(function (v) { v.classList.remove('is-open'); });
    if (e.key === 'Escape' && document.querySelector('.playlist-picker-backdrop')) {
      closePlaylistPicker();
      return;
    }
    // 로그인·회원가입 입력창에서 엔터: 그 화면의 기본 버튼(로그인 / 다음 / 시작하기)을 누른 것과 같음
    if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.closest('.auth-form')) {
      var main = e.target.closest('.auth-form').querySelector('.btn-primary');
      if (main) { e.preventDefault(); main.click(); }
      return;
    }
    // 검색창에서 엔터: 검색 결과 화면으로 이동
    if (e.key === 'Enter' && e.target.id === 'globalSearch') {
      e.preventDefault();
      if (state.query.trim() === '') return;
      addRecent(state.query);
      if (SEARCH.test(cur())) renderAll(document.getElementById(cur())); else location.hash = '#Search';
      return;
    }
    if ((e.key === 'Enter' || e.key === ' ') && e.target.classList && e.target.classList.contains('brand-name')) { e.preventDefault(); goHome(); }
  });

  document.addEventListener('focusout', function (e) {
    if (e.target.matches('[data-profile-name-input]')) finishNicknameEdit(e.target, false);
  });

  // 입력: 닉네임 수정 / 헤더 검색창(홈 등에서는 입력만, 엔터로 검색)
  document.addEventListener('input', function (e) {
    var i = e.target;
    if (i.id === 'nickname') { state.nickname = i.value.trim(); return; }
    if (i.classList.contains('vol-range')) { audio.muted = false; audio.volume = i.value / 100; try { localStorage.setItem('ms-volume', String(audio.volume)); } catch (err) {} return; }
    if (i.id !== 'globalSearch') return;
    i.dataset.typing = '1'; // 입력 중 표시: 화면 이동으로 포커스가 풀려도 route에서 되돌림
    var id = cur();
    state.query = i.value;
    syncSearch();
    if (state.query.trim() === '') {
      if (SEARCH.test(id)) { location.hash = '#SearchHome'; i.focus(); } // 주소 이동은 포커스를 풀어 버리므로 바로 되돌림
    }
    else if (SEARCH.test(id)) renderAll(document.getElementById(id)); // 검색 결과 화면에서는 입력하는 대로 갱신
    // 그 밖의 화면에서는 엔터를 눌러야 검색 결과로 이동 (아래 keydown)
  });

  window.addEventListener('hashchange', function () { closePlaylistPicker(); if (location.hash !== '#NewPlaylist') pendingNewPlaylistTrackId = null; route(); });
  window.addEventListener('resize', measureLogin);
  if (document.fonts) {
    if (document.fonts.ready) document.fonts.ready.then(measureLogin);
    document.fonts.addEventListener('loadingdone', measureLogin); // 글꼴이 늦게 로드돼도 높이를 다시 잼
  }

  /* ---------- 시작: 페이지(page/*.html)와 샘플 데이터 불러오기 ---------- */
  var PAGES = ['signup', 'home', 'playing', 'search', 'library', 'status', 'dialogs'];

  // 파일 불러오기(항상 최신 확인)
  function load(url, asJson) {
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(url + ' ' + r.status);
      return asJson ? r.json() : r.text();
    });
  }

  Promise.all([load('data/catalog.json', true), load('page/sidebar.html'), load('page/header.html'), load('data/genres.json', true)].concat(PAGES.map(function (n) { return load('page/' + n + '.html'); })))
    .then(function (res) {
      // Jamendo 곡 목록 (data/catalog.json: tools/build_catalog.py 가 CSV에서 만든 앱용 데이터)
      var cat = res[0];
      data.songs = cat.tracks.map(function (t) {
        return {
          id: t.id, title: t.name, artist: t.artist, album: t.album, duration: t.duration, audio: t.audio,
          image: t.image, albumImage: t.albumImage, genres: (t.genres && t.genres.length) ? t.genres : ['기타'], genre: (t.genres && t.genres[0]) || '기타',   // 장르 정보가 없는 곡은 '기타'
          lyrics: t.lyrics || '', license: t.license, share: t.share, listens: t.listens || 0, liked: false
        };
      });
      data.songs.forEach(function (s) { byId[s.id] = s; });
      cat.songMap.forEach(function (m) { (songToJamendo[m[0]] = songToJamendo[m[0]] || []).push(m[1]); }); // KKBox song_id → Jamendo id (전체 매핑 유지)
      genreList = res[3].genres;
      genreList.forEach(function (g) { if (g.name === '기타' && g.tags.indexOf('기타') < 0) g.tags.push('기타'); });
      // 곡마다 대표 장르 하나: 곡에 적힌 태그 순서에서 처음으로 장르 목록에 있는 태그의 장르 (장르 둘러보기·재생 화면 칩·곡 목록·장르 지도가 모두 이 값을 씀)
      data.songs.forEach(function (s) { s.primaryGenre = genreOf(s); s.genre = s.primaryGenre; });   // 장르가 없는 곡(태그 '기타')을 기타 장르에 포함
      document.getElementById('appHeader').innerHTML = res[2];
      document.getElementById('pages').innerHTML = res.slice(4).join('\n');
      renderGenres(genreList);
      renderRecent();
      buildSidebars(res[1]);
      renderGenreMap();
      document.querySelectorAll('.brand-name').forEach(function (b) { // '앙상블' 글자는 홈으로 가는 링크 역할
        b.setAttribute('role', 'link'); b.setAttribute('tabindex', '0'); b.setAttribute('title', '홈으로');
      });
      defaultCover = getComputedStyle(document.documentElement).getPropertyValue('--cover').trim();
      setupAudio();
      loadLikes();
      loadProfile();
      loadUserPlaylists();
      initSidebar();
      initUpnextToggle();
      setupLists();
      route();
    })
    .catch(function (err) {
      document.body.insertAdjacentHTML('afterbegin',
        '<p style="margin:0;padding:24px;color:#f4f4f8;font-family:sans-serif">화면 또는 곡 데이터를 불러오지 못했어요(' + String(err && err.message || err).replace(/</g, '&lt;') + '). web 폴더에서 "python3 -m http.server"로 실행한 뒤 열어 주세요.</p>');
    });

  // 추천 모델 연결 지점: 모델이 돌려준 KKBox song_id 목록(추천 순서)을 Jamendo 곡으로 바꿔 홈에 보여 줌.
  //   MusicApp.setModelRecommendations(['song_id', ...])  → { requested, linked }
  //   매핑이 없는 곡은 제외하고, 같은 Jamendo 곡이 겹치면 처음 순서만 남김. 연결된 곡이 하나도 없으면 인기곡 목록을 그대로 둠.
  function toTracks(songIds) {
    var seen = {}, out = [];
    (songIds || []).forEach(function (sid) {
      (songToJamendo[sid] || []).forEach(function (jid) { if (!seen[jid] && byId[jid]) { seen[jid] = 1; out.push(byId[jid]); } });
    });
    return out;
  }
  /* ---------- 로그인·가입 (Firebase 인증) ---------- */
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  function authMessage(err) {
    var code = (err && err.code) || '';
    var map = {
      'auth/invalid-credential': '이메일 또는 비밀번호가 맞지 않아요.', 'auth/wrong-password': '이메일 또는 비밀번호가 맞지 않아요.',
      'auth/user-not-found': '이메일 또는 비밀번호가 맞지 않아요.', 'auth/invalid-email': '이메일 형식이 올바르지 않아요.',
      'auth/email-already-in-use': '이미 가입된 이메일이에요. 로그인해 주세요.', 'auth/weak-password': '비밀번호는 8자 이상으로 입력해 주세요.',
      'auth/too-many-requests': '시도가 너무 많아요. 잠시 뒤에 다시 해 주세요.', 'auth/network-request-failed': '네트워크 연결을 확인해 주세요.',
      'auth/operation-not-allowed': '이 로그인 방식이 아직 켜져 있지 않아요.', 'auth/missing-email': '이메일을 입력해 주세요.', 'auth/unavailable': '로그인을 사용할 수 없어요. 잠시 뒤에 다시 해 주세요.'
    };
    return map[code] || '로그인에 실패했어요. 다시 시도해 주세요.';
  }
  function markError(input, on) { if (input) { input.classList.toggle('input--error', !!on); if (on) input.setAttribute('aria-invalid', 'true'); else input.removeAttribute('aria-invalid'); } }
  function signupFields() {
    var sec = document.getElementById('Login');
    return { email: sec.querySelector('input[type=email]'), pw: sec.querySelector('[data-pw]'), nick: document.getElementById('nickname') };   // 눈 아이콘으로 type 이 text 로 바뀔 수 있어 data-pw 로 찾음
  }
  function validateSignupFields() {
    var f = signupFields(), emailOk = EMAIL_RE.test(f.email.value.trim()), pwOk = f.pw.value.length >= 8, nickOk = !!f.nick.value.trim();
    markError(f.email, !emailOk); markError(f.pw, !pwOk); markError(f.nick, !nickOk);
    if (!emailOk) showToast('이메일 형식을 확인해 주세요.');
    else if (!pwOk) showToast('비밀번호는 8자 이상으로 입력해 주세요.');
    else if (!nickOk) showToast('닉네임을 입력해 주세요.');
    return emailOk && pwOk && nickOk;
  }
  function submitSignup() {
    if (signingUp) return;
    var f = signupFields();
    if (!window.MusicAuth) { showToast(authMessage({ code: 'auth/unavailable' })); return; }
    var genres = Array.prototype.map.call(document.querySelectorAll('#Login .chip.is-on'), function (c) { return c.textContent; }).slice(0, GENRE_MAX);
    signingUp = true; try { sessionStorage.setItem('ms-signing-up', '1'); } catch (e) {}
    window.MusicAuth.signUp(f.email.value.trim(), f.pw.value).then(function (cred) {
      state.authUser = { uid: cred.user.uid, email: cred.user.email, name: '' };
      profile.nickname = f.nick.value.trim() || randomNickname();
      profile.avatar = ''; profile.genres = genres;
      if (!registeredNicknames.some(function (n) { return nicknameKey(n) === nicknameKey(profile.nickname); })) registeredNicknames.push(profile.nickname);
      saveProfile(); recs.key = '';
      try { localStorage.setItem('ms-onboarded', '1'); } catch (e) {}   // 취향 선택(가입)을 마쳤다는 표시
      playedIds = {}; playHistory = []; recSnap = null; state.modelRecs = null; rebuildGenrePlays();   // 새 계정: 들은 곡 기록 없음
      try { localStorage.removeItem('ms-played-ids'); localStorage.removeItem('ms-play-history'); localStorage.removeItem('ms-recs'); } catch (e) {}
      renderProfile(); renderGenreMap();
      signingUp = false; try { sessionStorage.removeItem('ms-signing-up'); } catch (e) {}
      loadRecs(true);
      location.hash = '#Main';
    }).catch(function (err) {
      signingUp = false; try { sessionStorage.removeItem('ms-signing-up'); } catch (e) {}
      showToast(authMessage(err));
      var code = (err && err.code) || '';
      if (code === 'auth/email-already-in-use' || code === 'auth/invalid-email' || code === 'auth/weak-password') { markError(f.email, code !== 'auth/weak-password'); markError(f.pw, code === 'auth/weak-password'); setSignupStep(1); }
    });
  }
  function submitLogin(btn) {
    var form = btn.closest('.auth-form'), email = form.querySelector('input[type=email]'), pw = form.querySelector('[data-pw]');
    var emailOk = !!email.value.trim(), pwOk = !!pw.value;
    markError(email, !emailOk); markError(pw, !pwOk);
    if (!emailOk || !pwOk) { showToast('이메일과 비밀번호를 입력해 주세요.'); return; }
    if (!window.MusicAuth) { showToast(authMessage({ code: 'auth/unavailable' })); return; }
    btn.setAttribute('aria-disabled', 'true');
    window.MusicAuth.signIn(email.value.trim(), pw.value).then(function () {
      pw.value = '';   // 이후 화면 이동과 데이터 불러오기는 MusicApp.setAuth 가 처리
    }).catch(function (err) {
      markError(email, true); markError(pw, true); showToast(authMessage(err));
    }).then(function () { btn.removeAttribute('aria-disabled'); });
  }
  // 비밀번호 보이기/숨기기 (눈 아이콘)
  document.addEventListener('click', function (e) {
    var tg = e.target.closest && e.target.closest('[data-pw-toggle]'); if (!tg) return;
    var input = tg.parentNode.querySelector('[data-pw]'); if (!input) return;
    var show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    tg.classList.toggle('is-shown', show); tg.setAttribute('aria-pressed', show ? 'true' : 'false');
    tg.setAttribute('aria-label', show ? '비밀번호 숨기기' : '비밀번호 보기');
  });
  // 비밀번호 찾기: 이메일을 입력하면 재설정 링크를 메일로 보냄. 비밀번호는 안전상 어디서도 보여 줄 수 없고, 계정 존재 여부도 알려 주지 않음
  function closeForgot() { var b = document.querySelector('.forgot-backdrop'); if (b) b.remove(); }
  function openForgot() {
    closeForgot();
    var backdrop = document.getElementById('tplForgotPassword').content.firstElementChild.cloneNode(true);   // 마크업: page/dialogs.html
    var input = backdrop.querySelector('[data-forgot-email]'), result = backdrop.querySelector('[data-forgot-result]'), send = backdrop.querySelector('[data-forgot-send]');
    var typed = document.querySelector('#LoginEmail input[type=email]'); if (typed && typed.value.trim()) input.value = typed.value.trim();   // 로그인 화면에 입력한 이메일을 미리 채움
    function say(msg, isError) { result.hidden = false; result.textContent = msg; result.classList.toggle('is-error', !!isError); }
    function submit() {
      var email = input.value.trim();
      if (!EMAIL_RE.test(email)) { markError(input, true); say('이메일 형식을 확인해 주세요.', true); return; }
      markError(input, false);
      if (!window.MusicAuth) { say(authMessage({ code: 'auth/unavailable' }), true); return; }
      send.setAttribute('aria-disabled', 'true');
      window.MusicAuth.resetPassword(email).then(function () { return true; }, function (err) {
        var code = (err && err.code) || '';
        if (code === 'auth/user-not-found') return true;   // 가입 여부는 알려 주지 않음(같은 안내)
        say(authMessage(err), true); return false;
      }).then(function (ok) {
        send.removeAttribute('aria-disabled');
        if (ok) say('입력하신 이메일로 비밀번호 재설정 링크를 보냈어요. 가입된 이메일이라면 곧 도착해요. 메일함(스팸함 포함)을 확인해 주세요.', false);
      });
    }
    send.addEventListener('click', function (e) { e.preventDefault(); if (send.getAttribute('aria-disabled') !== 'true') submit(); });
    input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); send.click(); } });
    backdrop.addEventListener('click', function (e) { if (e.target === backdrop || e.target.closest('.forgot-close')) closeForgot(); });
    document.body.appendChild(backdrop);
    input.focus();
  }
  document.addEventListener('click', function (e) { if (e.target.closest && e.target.closest('[data-forgot-password]')) { e.preventDefault(); openForgot(); } });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeForgot(); });

  // js/firebase.js 가 로그인 상태를 알려 줌: user=null 이면 로그아웃 상태 → 로그인 화면
  function setAuth(user) {
    authPending = false;
    document.body.classList.remove('auth-pending');
    state.authUser = user ? { uid: user.uid, email: user.email || '', name: user.displayName || '' } : null;
    if (user && !signingUp && !profile.nickname) {   // 구글 등으로 처음 들어온 계정: 닉네임을 구글 이름(없으면 이메일 앞부분)으로
      var base = (user.displayName || (user.email || '').split('@')[0] || '').trim();
      profile.nickname = base || randomNickname();
      if (!registeredNicknames.some(function (n) { return nicknameKey(n) === nicknameKey(profile.nickname); })) registeredNicknames.push(profile.nickname);
      saveProfile();
    }
    renderProfile();
    route();
    if (user && !signingUp && localStorage.getItem('ms-onboarded') !== '1') showGenrePicker();   // 가입(취향 선택)을 안 마친 계정은 장르 선택 팝업
  }
  setTimeout(function () { if (authPending) setAuth(null); }, 8000);   // 로그인 상태를 끝내 확인하지 못해도 화면이 숨겨진 채로 남지 않게

  window.MusicApp = {
    showToast: showToast,   // js/firebase.js 의 로그인 결과 알림용
    setAuth: setAuth,       // js/firebase.js 가 로그인 상태를 알려 줌
    showGenrePicker: showGenrePicker,   // js/firebase.js 가 구글 첫 로그인 뒤 부름
    setModelRecommendations: function (songIds) {
      var out = toTracks(songIds);
      state.modelRecs = out.length ? out : null;
      renderLists();
      return { requested: (songIds || []).length, linked: out.length };
    }
  };

  /* ---------- 추천 서버 연결 ----------
     회원가입에서 고른 장르(최대 3개)마다 '그 장르를 많이 듣는 데모 사용자'가 있고, 서버가 그 사용자들의 추천(v11 모델 점수 순서)을 섞어 돌려줌.
     처음엔 기존 추천만 보여 주고, 서로 다른 3곡을 들으면 미리 계산해 둔 보정 추천으로 바꿈. */
  var API_BASE = (location.hostname === 'localhost' || location.hostname === '127.0.0.1') ? 'http://' + location.hostname + ':8010' : '';
  var recs = { key: '', base: null, adjusted: null, switched: false };
  var serverRecs = [];   // 서버(장르별 대리 사용자) 추천: 들은 곡이 적을 때 참고만 함. 곡을 들을수록 영향이 줄어듦

  /* ---------- 개인 추천 (이 사용자의 기록만 사용) ----------
     점수 = 장르 취향(들은 곡·좋아요·가입 때 고른 장르) + 아티스트 취향 + 인기도(작게) + 서버 추천 순위(들은 곡이 적을수록 크게)
     이미 들은 곡은 제외. 한 장르가 몰리지 않게 장르당 6곡까지, 마지막 2곡은 아직 안 들어 본 장르(새로운 발견). 같은 기록이면 항상 같은 결과. */
  function personalRecs() {
    var played = playedTracks(), liked = likedTracks(), playedSet = {};
    played.forEach(function (s) { playedSet[s.id] = 1; });
    var gw = {}, aw = {};
    function add(s, w) { gw[s.primaryGenre] = (gw[s.primaryGenre] || 0) + w; aw[s.artist] = (aw[s.artist] || 0) + w; }
    played.forEach(function (s) { add(s, 1); });
    liked.forEach(function (s) { add(s, 1.5); });                                   // 좋아요는 더 강한 신호
    (profile.genres || []).forEach(function (g) { gw[g] = (gw[g] || 0) + 1.5; });   // 가입 때 고른 장르: 처음 취향
    var gTotal = 0; Object.keys(gw).forEach(function (k) { gTotal += gw[k]; });
    var maxLog = 1; data.songs.forEach(function (s) { maxLog = Math.max(maxLog, Math.log1p(s.listens || 0)); });
    var prior = {}; serverRecs.forEach(function (t, i) { prior[t.id] = 1 - i / Math.max(1, serverRecs.length); });
    var coldW = 0.35 * Math.max(0, 1 - played.length / 12);
    var cand = data.songs.filter(function (s) { return !playedSet[s.id]; }).map(function (s) {
      var g = gTotal ? (gw[s.primaryGenre] || 0) / gTotal : 0;
      var a = Math.min(1, (aw[s.artist] || 0) / 3);
      var pop = Math.log1p(s.listens || 0) / maxLog;
      return { s: s, score: g + 0.5 * a + 0.15 * pop + coldW * (prior[s.id] || 0) };
    });
    cand.sort(function (x, y) { return (y.score - x.score) || (x.s.id - y.s.id); });
    var out = [], perGenre = {}, used = {};
    function take(c) { out.push(c.s); used[c.s.id] = 1; perGenre[c.s.primaryGenre] = (perGenre[c.s.primaryGenre] || 0) + 1; }
    for (var i = 0; i < cand.length && out.length < 8; i++) { if ((perGenre[cand[i].s.primaryGenre] || 0) < 6) take(cand[i]); }
    cand.filter(function (c) { return !used[c.s.id] && !gw[c.s.primaryGenre]; })                       // 새로운 발견: 아직 취향 신호가 없는 장르의 인기곡
      .sort(function (x, y) { return (y.s.listens - x.s.listens) || (x.s.id - y.s.id); })
      .slice(0, 10 - out.length).forEach(take);
    for (var j = 0; j < cand.length && out.length < 10; j++) { if (!used[cand[j].s.id]) take(cand[j]); }   // 모자라면 점수 순으로 채움
    return out;
  }
  // 추천 목록 갱신: 서로 다른 3곡부터, 이후 3곡 더 들을 때마다. fromPlay=true 면 갱신됐을 때 알림
  function refreshRecs(fromPlay) {
    var n = distinctPlays();
    if (n < 3) { if (recSnap) { recSnap = null; saveRecSnap(); } state.modelRecs = null; return; }
    var firstOrDue = !recSnap || !recSnap.ids.length || n >= recSnap.at + 3;
    if (firstOrDue) {
      var list = personalRecs();
      recSnap = { at: n, ids: list.map(function (t) { return t.id; }) };
      saveRecSnap();
      if (fromPlay) showToast('들은 곡을 반영해 추천이 새로 구성됐어요.');
    }
    state.modelRecs = recSnap.ids.map(function (id) { return byId[id]; }).filter(Boolean);
    renderLists();
    setRailSub(railSubDefault());
  }
  function hasPlayed() { return Object.keys(genrePlays).some(function (g) { return genrePlays[g] > 0; }); }
  function setRailSub(text) {
    var n = distinctPlays();
    setRole('railSub', n >= 3 ? (text || '') : n > 0 ? '서로 다른 3곡을 들으면 취향에 맞는 추천이 나타나요. (' + n + '/3)' : '좋아하는 곡을 들어보세요. 취향에 맞춰 추천해 드릴게요.');
  }
  function railSubDefault() {
    var k = recSnap ? distinctPlays() - recSnap.at : 0;
    if (!recSnap || k <= 0) return '방금 들은 곡을 반영한 추천이에요.';
    return '새로운 취향을 반영하려면 3곡을 더 들어주세요. (' + Math.min(k, 3) + '/3)';
  }
  function loadRecs(force) {
    var key = profile.genres.join(',');
    if (!force && key === recs.key) return;
    recs.key = key;
    recs.base = recs.adjusted = null; recs.switched = false;
    function fallback() { recs.key = ''; serverRecs = []; refreshRecs(false); }   // 서버 없이도 개인 추천은 이 사용자의 기록으로 계산
    if (!API_BASE) { serverRecs = []; refreshRecs(false); return; }
    fetch(API_BASE + '/api/recommend?genres=' + encodeURIComponent(key), { cache: 'no-cache' }).then(function (r) {
      if (r.status === 404) { recs.key = key; serverRecs = []; refreshRecs(false); return null; }
      if (!r.ok) throw new Error(r.status);
      return r.json();
    }).then(function (res) {
      if (!res || key !== profile.genres.join(',')) return;
      recs.base = res.base; recs.adjusted = res.adjusted;
      serverRecs = toTracks(res.adjusted);   // 장르 대리 사용자 추천(인기도 보정)은 처음 취향 참고용
      refreshRecs(false);
    }).catch(function () { fallback(); });
  }
  // 사이드바 '초기화': 들은 기록(장르 지도 포함)을 지우고 추천을 처음부터 다시 시작 (좋아요·플레이리스트는 그대로)
  function resetListening() {
    playedIds = {}; playHistory = [];
    try { localStorage.removeItem('ms-played-ids'); localStorage.removeItem('ms-play-history'); } catch (e) {}
    rebuildGenrePlays();
    recs.switched = false; recSnap = null; saveRecSnap(); state.modelRecs = null;
    renderGenreMap();
    renderLists();
    loadRecs(true);       // 서버의 처음 추천을 다시 받고 안내 문구도 처음 상태로
    setRailSub(railSubDefault());
    showToast('추천을 처음부터 다시 시작해요.');
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-reset-recs]');
    if (!btn) return;
    e.preventDefault(); e.stopPropagation();   // 감싼 '내 현황' 링크로 이동하지 않게
    if (window.confirm('들은 곡 기록을 지우고 추천을 처음부터 다시 시작할까요?')) resetListening();
  }, true);
  document.addEventListener('keydown', function (e) {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('[data-reset-recs]')) { e.preventDefault(); e.target.click(); }
  });
  // 재생 화면 하단 목록(다음 곡·추천곡) 접기/펴기. 선택은 브라우저에 기억
  function setUpnextCollapsed(collapsed, save) {
    document.querySelectorAll('#Playing .upnext').forEach(function (box) {
      box.classList.toggle('is-collapsed', collapsed);
      var head = box.querySelector('[data-upnext-toggle]');
      if (head) head.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    });
    if (save) { try { localStorage.setItem('ms-upnext-collapsed', collapsed ? '1' : '0'); } catch (e) {} }
  }
  function initUpnextToggle() {
    var saved = false;
    try { saved = localStorage.getItem('ms-upnext-collapsed') === '1'; } catch (e) {}
    setUpnextCollapsed(saved, false);
    document.addEventListener('click', function (e) {
      if (e.target.closest && e.target.closest('#Playing [data-upnext-toggle]')) setUpnextCollapsed(!document.querySelector('#Playing .upnext').classList.contains('is-collapsed'), true);
    });
    document.addEventListener('keydown', function (e) {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('#Playing [data-upnext-toggle]')) { e.preventDefault(); e.target.click(); }
    });
  }
  // 구글로 처음 로그인했을 때: 장르 선택 팝업(닫기 없음) → '시작하기'로 취향 저장 후 바로 홈
  function showGenrePicker() {
    if (!genreList.length) { setTimeout(showGenrePicker, 300); return; }   // 장르 목록을 불러오기 전이면 잠깐 뒤에
    if (document.querySelector('.genre-picker-backdrop')) return;
    var backdrop = document.getElementById('tplGenrePicker').content.firstElementChild.cloneNode(true);   // 마크업: page/dialogs.html
    var box = backdrop.querySelector('[data-picker-genres]'), start = backdrop.querySelector('[data-genre-start]');
    genreList.forEach(function (g) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'genre-picker-chip'; b.setAttribute('aria-pressed', 'false'); b.textContent = g.name;
      box.appendChild(b);
    });
    function picked() { return Array.prototype.map.call(box.querySelectorAll('.is-on'), function (c) { return c.textContent; }); }
    function sync() { start.setAttribute('aria-disabled', picked().length < 1 ? 'true' : 'false'); }
    box.addEventListener('click', function (e) {
      var chip = e.target.closest('.genre-picker-chip'); if (!chip) return;
      var on = !chip.classList.contains('is-on');
      if (on && picked().length >= GENRE_MAX) { showToast('장르는 최대 ' + GENRE_MAX + '개까지 고를 수 있어요.'); return; }
      chip.classList.toggle('is-on', on); chip.setAttribute('aria-pressed', on ? 'true' : 'false'); sync();
    });
    start.addEventListener('click', function (e) {
      var genres = picked();
      if (genres.length < 1) { e.preventDefault(); return; }
      profile.genres = genres.slice(0, GENRE_MAX);
      saveProfile(); recs.key = '';
      try { localStorage.setItem('ms-onboarded', '1'); } catch (err) {}
      renderGenreMap();
      backdrop.remove();
      loadRecs(true);
      // href="#Main" 으로 홈 이동
    });
    document.body.appendChild(backdrop);
  }
  // 곡 재생을 시작할 때 부름: 서로 다른 3곡을 들으면 보정 추천으로 교체
  function onPlayed(id) {
    refreshRecs(true);   // 서로 다른 3곡부터, 이후 3곡마다 이 사용자의 기록으로 추천을 새로 계산
    setRailSub(railSubDefault());
  }
})();
