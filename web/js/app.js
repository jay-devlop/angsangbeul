(function () {
  var PLAY_ICON = '<path d="M7 4.5v15l13-7.5z"/>';
  var PAUSE_ICON = '<path d="M6 5h4v14H6zM14 5h4v14h-4z"/>';
  var SEARCH = /^Search(Songs|Artists|Genres)?$/;

  var data = { songs: [] };
  var userPlaylists = [];
  var profile = { nickname: '발라드 리스너', avatar: '', avatarHue: 280, genres: ['발라드', 'R&B', '인디'] };
  var profileGenresExpanded = false;
  var registeredNicknames = [];
  var genreList = [];            // data/genres.json (가입 칩·검색 장르 타일)
  var songToJamendo = {};        // KKBox song_id → [Jamendo 곡 id]  (추천 모델 연결용)
  // 처음에는 곡을 고르지 않은 상태: 정지, 재생바 숨김
  var state = { current: null, ctx: null, fullQueue: false, t: 0, dur: 0, playing: false, status: 'idle', query: '', started: false, artist: '', genre: '', modelRecs: null, activePlaylistIndex: 0 };
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
    if (!registeredNicknames.some(function (name) { return nicknameKey(name) === nicknameKey(profile.nickname); })) {
      registeredNicknames.push(profile.nickname);
    }
    if (!saveProfile()) showToast('계정 정보를 저장하지 못했어요. 저장 공간을 확인해 주세요.');
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
    document.querySelectorAll('#Profile .profile-avatar-upload').forEach(function (avatar) {
      avatar.style.backgroundImage = profile.avatar ? 'url("' + profile.avatar + '")' : '';
      avatar.style.backgroundSize = profile.avatar ? 'cover' : '';
      avatar.style.backgroundPosition = profile.avatar ? 'center' : '';
      if (!profile.avatar) avatar.style.background = 'linear-gradient(145deg, hsl(' + profile.avatarHue + ' 58% 42%), hsl(' + ((profile.avatarHue + 36) % 360) + ' 52% 24%))';
    });
    document.querySelectorAll('.avatar-btn').forEach(function (avatar) {
      avatar.textContent = Array.from(profile.nickname)[0] || '';
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
    var backdrop = document.createElement('div');
    backdrop.className = 'image-editor-backdrop';
    var dialog = document.createElement('div');
    dialog.className = 'image-editor';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'imageEditorTitle');
    var title = document.createElement('h2');
    title.className = 'image-editor-title';
    title.id = 'imageEditorTitle';
    title.textContent = '이미지 편집';
    var preview = document.createElement('div');
    preview.className = 'image-editor-preview';
    preview.setAttribute('aria-hidden', 'true');
    var colorLabel = document.createElement('div');
    colorLabel.className = 'image-editor-label';
    colorLabel.textContent = '색상 선택';
    var colors = document.createElement('div');
    colors.className = 'image-editor-colors';
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
    var colorRow = document.createElement('div');
    colorRow.className = 'image-editor-option-row';
    colorRow.appendChild(colorLabel);
    colorRow.appendChild(colors);
    var uploadRow = document.createElement('div');
    uploadRow.className = 'image-editor-option-row';
    var uploadLabel = document.createElement('div');
    uploadLabel.className = 'image-editor-label';
    uploadLabel.textContent = '사진 업로드';
    var upload = document.createElement('button');
    upload.type = 'button';
    upload.className = 'image-editor-upload';
    upload.setAttribute('aria-label', '사진 업로드');
    upload.title = '사진 업로드';
    var uploadIcon = document.createElement('img');
    uploadIcon.src = 'icon/upload.png';
    uploadIcon.alt = '';
    upload.appendChild(uploadIcon);
    uploadRow.appendChild(uploadLabel);
    uploadRow.appendChild(upload);
    var actions = document.createElement('div');
    actions.className = 'image-editor-actions';
    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.className = 'btn-secondary';
    cancel.dataset.imageEditorCancel = '';
    cancel.textContent = '취소';
    var save = document.createElement('button');
    save.type = 'button';
    save.className = 'btn-primary--half';
    save.dataset.imageEditorSave = '';
    save.textContent = '저장';
    actions.appendChild(cancel);
    actions.appendChild(save);
    dialog.appendChild(title);
    dialog.appendChild(preview);
    dialog.appendChild(colorRow);
    dialog.appendChild(uploadRow);
    dialog.appendChild(actions);
    backdrop.appendChild(dialog);
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
  function closePlaylistPicker() {
    var picker = document.querySelector('.playlist-picker-backdrop');
    if (picker) picker.remove();
    playlistPickerTrackId = null;
  }
  function showPlaylistPicker(trackId) {
    closePlaylistPicker();
    playlistPickerTrackId = trackId;
    var backdrop = document.createElement('div'); backdrop.className = 'playlist-picker-backdrop';
    var dialog = document.createElement('div'); dialog.className = 'playlist-picker'; dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true'); dialog.setAttribute('aria-labelledby', 'playlistPickerTitle');
    var heading = document.createElement('h2'); heading.id = 'playlistPickerTitle'; heading.className = 'section-title'; heading.textContent = '플레이리스트에 추가';
    var close = document.createElement('button'); close.type = 'button'; close.className = 'playlist-picker-close'; close.setAttribute('aria-label', '닫기'); close.textContent = '×';
    dialog.appendChild(heading); dialog.appendChild(close);
    if (!userPlaylists.length) {
      var empty = document.createElement('p'); empty.className = 'caption'; empty.textContent = '먼저 플레이리스트를 만들어 주세요.';
      var create = document.createElement('a'); create.href = '#NewPlaylist'; create.className = 'btn-primary'; create.textContent = '새 플레이리스트 만들기';
      dialog.appendChild(empty); dialog.appendChild(create);
    } else {
      var options = document.createElement('div'); options.className = 'playlist-picker-options';
      userPlaylists.forEach(function (playlist, index) {
        var option = document.createElement('button'); option.type = 'button'; option.className = 'playlist-picker-option'; option.dataset.playlistIndex = index;
        var name = document.createElement('span'); name.textContent = playlist.name;
        var count = document.createElement('span'); count.className = 'caption'; count.textContent = (playlist.trackIds || []).length + '곡';
        option.appendChild(name); option.appendChild(count); options.appendChild(option);
      });
      dialog.appendChild(options);
    }
    backdrop.appendChild(dialog); document.body.appendChild(backdrop);
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
    var def = genreDef(name), tags = def ? (def.tags || []) : [norm(name)];
    return topTracks().filter(function (s) { return s.genres.some(function (g) { return tags.indexOf(g) > -1; }); });
  }
  function likedTracks() { return topTracks().filter(function (s) { return s.liked; }); }
  // 지금 곡 다음에 재생될 곡 n개
  function nextTracks(n) {
    var ids = state.ctx && state.ctx.length ? state.ctx : topTracks().map(function (s) { return s.id; });
    var i = ids.indexOf(state.current), out = [];
    if (state.fullQueue) return ids.slice(i + 1).map(function (id) { return byId[id]; }).filter(Boolean);
    for (var k = 1; k <= Math.min(n, ids.length - 1); k++) out.push(byId[ids[(i + k + ids.length) % ids.length]]);
    return out.filter(Boolean);
  }

  /* ---------- 이미지: image → album_image → 기본 이미지 ---------- */
  var imgOk = {}; // 주소 → 불러오기 성공 여부
  function pickImage(s, cb) {
    var urls = [s.image, s.albumImage].filter(isHttp);
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
    if (!s) return;
    pickImage(s, function (u) { if (u && state.current === s.id) root.style.setProperty('--cover', cssUrl(u)); });
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
      case 'rail-Main': return state.modelRecs || [];
      case 'HomeBallad': return topTracks().slice(0, 100);
      case 'upnext': return nextTracks(4);
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
    setLabel(d[0], s.genre);
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
  // 진행 막대·시간·재생 버튼·곡 정보 등 상태 반영
  function render() {
    var sec = document.getElementById(cur()); if (!sec) return;
    var D = dur(), s = song();
    document.body.classList.toggle('paused', !state.playing);
    document.body.classList.toggle('player-off', !state.started); // 곡을 고르기 전에는 재생바를 숨김
    document.body.classList.toggle('player-excluded', /^(Status|Profile)$/.test(sec.id));
    document.body.classList.toggle('no-header', /^(Login|LoginEmail|LoginError|SignupDone)$/.test(sec.id));
    var pct = Math.min(100, state.t / D * 100).toFixed(1) + '%';
    sec.querySelectorAll('[data-role=progress]').forEach(function (p) { p.firstElementChild.style.width = pct; });
    sec.querySelectorAll('[data-role=cur]').forEach(function (e) { e.textContent = mmss(state.t); });
    sec.querySelectorAll('[data-role=tot]').forEach(function (e) { e.textContent = s ? mmss(D) : '0:00'; });
    sec.querySelectorAll('[data-role=curTot]').forEach(function (e) { e.textContent = mmss(state.t) + ' / ' + (s ? mmss(D) : '0:00'); });
    sec.querySelectorAll('.disc-time').forEach(function (e) { // LP 아래 시간 표시: "현재 / 전체"
      setLabel(e, mmss(state.t) + ' / ');
      var tot = e.querySelector('span'); if (tot) tot.textContent = s ? mmss(D) : '0:00';
    });
    sec.querySelectorAll('[data-role=npTitle]').forEach(function (e) { e.textContent = s ? s.title : '재생할 곡을 골라 주세요'; });
    sec.querySelectorAll('[data-role=npArtist]').forEach(function (e) { e.textContent = statusText(s); });
    sec.querySelectorAll('[data-role=npArtistLine]').forEach(function (e) { e.textContent = s ? [s.artist, s.genre].filter(Boolean).join(' · ') : ''; });
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
      function row(label, value) {
        if (!value) return;
        var r = document.createElement('div'); r.className = 'credit-row';
        var l = document.createElement('span'); l.className = 'credit-label'; l.textContent = label;
        var v = document.createElement('span'); v.textContent = value;
        r.appendChild(l); r.appendChild(v); box.appendChild(r);
      }
      row('아티스트', s.artist);
      row('앨범', s.album);
      row('장르', s.genres.join(', '));
      var links = document.createElement('div'); links.className = 'credit-links';
      [['곡 출처 페이지', s.share], ['라이선스 보기', s.license]].forEach(function (x) {
        if (!isHttp(x[1])) return;
        var a = document.createElement('a'); a.className = 'credit-link'; a.href = x[1]; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = x[0];
        links.appendChild(a);
      });
      if (links.children.length) box.appendChild(links);
      if (s.lyrics) {
        var d = document.createElement('details'); d.className = 'credit-lyrics';
        var sm = document.createElement('summary'); sm.textContent = '가사';
        var pre = document.createElement('pre'); pre.textContent = s.lyrics; // 글자 그대로 표시(HTML로 실행되지 않음)
        d.appendChild(sm); d.appendChild(pre); box.appendChild(d);
      }
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
    btn.setAttribute('href', n === 1 ? '#' : '#LoginEmail');
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

  // '뮤직스트림' 글자: 새로고침처럼 처음 상태의 홈으로 (로그인 화면에서는 로그인 화면으로)
  function goHome() {
    var home = /^(Login|LoginEmail|LoginError|SignupDone)$/.test(cur()) ? '#LoginEmail' : '#Main';
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
    if (id === 'SearchHome') { state.query = ''; var gs = document.getElementById('globalSearch'); if (gs && gs.value !== '') gs.value = ''; } // 검색 메인은 빈 검색창으로
    syncSearch();
    if (id === 'Login' && nickInput() && !nickInput().value.trim()) rollNickname();
    if (id === 'SignupDone' && state.nickname) {
      el.querySelectorAll('div').forEach(function (d) {
        if (!d.children.length && /님, 반가워요$/.test(d.textContent)) d.textContent = state.nickname + '님, 반가워요';
      });
    }
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
  function playSong(id, ctx, fullQueue) {
    var s = byId[id]; if (!s) return;
    keepPlayerVisible();
    state.current = id; state.t = 0; state.dur = 0; state.started = true; state.status = 'loading'; state.playing = true;
    if (ctx) state.ctx = ctx;
    state.fullQueue = !!fullQueue;
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
    document.querySelectorAll('.vol-btn').forEach(function (b) { b.setAttribute('aria-label', audio.muted || audio.volume === 0 ? '음소거 해제' : '음소거'); });
  }
  function setupAudio() {
    audio = document.getElementById('audio');
    audio.preload = 'none';
    var vol = 0.8;
    try { var v = localStorage.getItem('ms-volume'); if (v !== null) vol = Math.max(0, Math.min(1, +v)); } catch (e) {}
    audio.volume = vol;
    audio.addEventListener('playing', function () { keepPlayerVisible(); state.playing = true; state.status = 'playing'; render(); });
    audio.addEventListener('pause', function () { if (!audio.ended) { state.playing = false; render(); schedulePlayerHide(); } });
    audio.addEventListener('waiting', function () { state.status = 'loading'; render(); });
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
      var w = document.createElement('div'); w.className = 'vol';
      var b = document.createElement('button'); b.type = 'button'; b.className = 'vol-btn'; b.innerHTML = SPEAKER;
      var r = document.createElement('input'); r.type = 'range'; r.className = 'vol-range'; r.min = 0; r.max = 100; r.step = 1; r.setAttribute('aria-label', '볼륨');
      w.appendChild(b); w.appendChild(r); bar.appendChild(w);
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
      userPlaylists.push({ name: playlistName, trackIds: [], colorHue: Math.floor(Math.random() * 360) });
      if (!saveUserPlaylists()) {
        userPlaylists.pop();
        showToast('플레이리스트를 저장하지 못했어요. 브라우저 저장 공간을 확인해 주세요.');
        return;
      }
      renderUserPlaylists();
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
    if (e.target.closest('.playlist-picker-close') || e.target.classList.contains('playlist-picker-backdrop')) {
      closePlaylistPicker();
      return;
    }
    var addToPlaylist = e.target.closest('.add-to-playlist');
    if (addToPlaylist) {
      e.preventDefault();
      e.stopPropagation();
      var trackRow = addToPlaylist.closest('[data-id]');
      if (trackRow) showPlaylistPicker(+trackRow.dataset.id);
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
      if (next.dataset.step === '1') { e.preventDefault(); setSignupStep(2); }
      else if (genreCount() < 1) e.preventDefault(); // 장르를 1개 이상 골라야 시작
      return; // 2단계의 '시작하기'는 링크(#LoginEmail)대로 로그인 화면으로 이동
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
    if (e.target.closest('.vol-btn')) { audio.muted = !audio.muted; if (!audio.muted && audio.volume === 0) audio.volume = 0.5; return; }
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
    if (/좋아요$/.test(label)) {
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

  window.addEventListener('hashchange', route);
  window.addEventListener('resize', measureLogin);
  if (document.fonts) {
    if (document.fonts.ready) document.fonts.ready.then(measureLogin);
    document.fonts.addEventListener('loadingdone', measureLogin); // 글꼴이 늦게 로드돼도 높이를 다시 잼
  }

  /* ---------- 시작: 페이지(page/*.html)와 샘플 데이터 불러오기 ---------- */
  var PAGES = ['signup', 'home', 'search', 'library', 'status'];

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
          image: t.image, albumImage: t.albumImage, genres: t.genres || [], genre: (t.genres && t.genres[0]) || '',
          lyrics: t.lyrics || '', license: t.license, share: t.share, listens: t.listens || 0, liked: false
        };
      });
      data.songs.forEach(function (s) { byId[s.id] = s; });
      cat.songMap.forEach(function (m) { (songToJamendo[m[0]] = songToJamendo[m[0]] || []).push(m[1]); }); // KKBox song_id → Jamendo id (전체 매핑 유지)
      genreList = res[3].genres;
      document.getElementById('appHeader').innerHTML = res[2];
      document.getElementById('pages').innerHTML = res.slice(4).join('\n');
      renderGenres(genreList);
      renderRecent();
      buildSidebars(res[1]);
      document.querySelectorAll('.brand-name').forEach(function (b) { // '뮤직스트림' 글자는 홈으로 가는 링크 역할
        b.setAttribute('role', 'link'); b.setAttribute('tabindex', '0'); b.setAttribute('title', '홈으로');
      });
      defaultCover = getComputedStyle(document.documentElement).getPropertyValue('--cover').trim();
      setupAudio();
      loadLikes();
      loadProfile();
      loadUserPlaylists();
      initSidebar();
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
  window.MusicApp = {
    setModelRecommendations: function (songIds) {
      var seen = {}, out = [];
      (songIds || []).forEach(function (sid) {
        (songToJamendo[sid] || []).forEach(function (jid) { if (!seen[jid] && byId[jid]) { seen[jid] = 1; out.push(byId[jid]); } });
      });
      state.modelRecs = out.length ? out : null;
      setRole('railTitle', out.length ? '추천' : '추천 음악');
      setRole('railSub', out.length ? '' : '3곡을 들으면 취향에 맞는 음악을 추천해 드려요.');
      renderLists();
      return { requested: (songIds || []).length, linked: out.length };
    }
  };
})();
