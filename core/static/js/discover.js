/* Лента: стопка карточек, перетаскивание/кнопки/стрелки, экран пары. */
(function () {
  const deck = document.getElementById("deck"), empty = document.getElementById("empty");
  const actions = document.getElementById("actions"), hint = document.getElementById("kbd-hint");
  const overlay = document.getElementById("match-overlay");
  const THRESHOLD = 100;
  const fbox = document.getElementById("filters"), fbtn = document.getElementById("filters-btn");
  const freset = document.getElementById("filters-reset"), fcount = document.getElementById("filters-count");
  const chosenBox = document.getElementById("f-interests"), goalBox = document.getElementById("f-goals");
  const GOALS = [["relationship", "Серьёзные отношения"], ["dating", "Свидания"], ["friends", "Дружба"], ["chat", "Общение"], ["unsure", "Пока не знаю"]];
  function renderGoals(selected) {
    const chosen = new Set(selected || []); goalBox.textContent = "";
    GOALS.forEach(([id, title]) => {
      const b = DM.el("button", "chip", title); b.type = "button"; b.setAttribute("aria-pressed", chosen.has(id));
      b.addEventListener("click", () => { chosen.has(id) ? chosen.delete(id) : chosen.add(id); b.setAttribute("aria-pressed", chosen.has(id)); });
      goalBox.appendChild(b);
    });
    goalBox.getChosen = () => [...chosen];
  }
  const vmodal = document.getElementById("video-modal"), vbody = document.getElementById("video-body");
  let filters = {};
  try { filters = JSON.parse(localStorage.getItem("dm-filters") || "{}") || {}; } catch (e) { filters = {}; }

  let queue = [], cards = [], seen = new Set(), exhausted = false, loading = false, busy = false;

  function playVideo(url) {
    vbody.textContent = "";
    const v = DM.el("video"); v.src = url; v.controls = true; v.autoplay = true; v.playsInline = true;
    vbody.appendChild(v); vmodal.hidden = false;
  }
  function closeVideo() { vmodal.hidden = true; vbody.textContent = ""; }
  document.getElementById("video-close").addEventListener("click", closeVideo);

  function safeUrl(u) { return /^https?:\/\//i.test(u) ? u : ""; }

  function buildCard(p) {
    const card = DM.el("article", "card");
    card._profile = p;
    if (p.accent) card.style.setProperty("--accent", p.accent);
    const frame = DM.el("div", "tarot-frame");

    /* 1. фото (текст его не закрывает) */
    const photo = DM.el("div", "card-photo");
    const img = DM.el("img", "cover"); img.src = p.photo_url; img.alt = "Фото: " + p.name; img.draggable = false;
    photo.append(img, DM.el("span", "tarot-num", DM.roman(p.age)));
    /* жест свайпа: мягкая подсветка края и маленький значок (без крупных надписей) */
    const like = DM.el("span", "fx like"), nope = DM.el("span", "fx nope");
    const lb = DM.el("span", "swipe-badge"); lb.appendChild(DM.icon("heart", "fill")); like.appendChild(lb);
    const nb = DM.el("span", "swipe-badge"); nb.appendChild(DM.icon("x")); nope.appendChild(nb);
    photo.append(like, nope);
    if (p.online) {
      const pr = DM.el("span", "presence-tag"); pr.appendChild(DM.el("span", "online-dot")); pr.appendChild(document.createTextNode("в сети")); photo.appendChild(pr);
    }
    frame.appendChild(photo);

    /* 2. имя — подпись карты */
    const title = DM.el("div", "tarot-title");
    title.append(DM.art("star"), DM.el("h2", "", p.name), DM.art("star"));
    frame.appendChild(title);

    /* 3. отдельный прямоугольник с описанием, тегами и кнопками */
    const body = DM.el("div", "card-body");
    if (p.status) body.appendChild(DM.el("p", "status", p.status));
    let bio = null, more = null;
    if (p.bio) {
      bio = DM.el("p", "bio", p.bio); body.appendChild(bio);
      more = DM.el("button", "link-btn more", "Читать полностью"); more.type = "button"; more.hidden = true;
      more.addEventListener("click", () => {
        const open = card.classList.toggle("expanded");
        more.textContent = open ? "Свернуть" : "Читать полностью"; more.setAttribute("aria-expanded", String(open));
      });
      body.appendChild(more);
    }
    const extras = DM.el("div", "extras");
    extras.appendChild(DM.el("span", "", DM.ageText(p.age)));
    if (p.goal_title) { const g = DM.el("span"); g.appendChild(DM.icon("target")); g.appendChild(document.createTextNode(p.goal_title)); extras.appendChild(g); }
    if (p.video_url) {
      const b = DM.el("button", "video"); b.type = "button"; b.appendChild(DM.icon("play", "fill")); b.appendChild(document.createTextNode("Видео"));
      b.addEventListener("click", () => playVideo(p.video_url)); extras.appendChild(b);
    }
    if (p.music_title) {
      const m = DM.el("button", "music"); m.type = "button"; m.setAttribute("aria-label", "Слушать: " + p.music_title);
      m.appendChild(DM.icon("music")); m.appendChild(document.createTextNode(p.music_title));
      m.addEventListener("click", () => DM.openPlayer(p.music_title, p.music_url)); extras.appendChild(m);
    }
    body.appendChild(extras);
    if (p.interests.length) {
      const tags = DM.el("div", "tags");
      p.interests.slice(0, 8).forEach(t => tags.appendChild(DM.el("span", "", t)));
      body.appendChild(tags);
    }
    frame.appendChild(body);
    card.appendChild(frame);
    card._like = like; card._nope = nope;
    card._fit = () => { if (bio && more) more.hidden = !(bio.scrollHeight > bio.clientHeight + 1 || card.classList.contains("expanded")); };
    return card;
  }

  function layout() {
    cards.forEach((c, i) => {
      c.style.zIndex = String(10 - i);
      if (i > 0) c.style.transform = "translateY(" + (i * 12) + "px) scale(" + (1 - i * 0.04) + ")";
      else if (!c.classList.contains("dragging")) c.style.transform = "";
    });
  }

  /* Свайп: слушаем всю область ленты (а не только фото), поэтому тянуть можно за любую часть карточки.
     Кнопки и ссылки внутри карточки по-прежнему нажимаются как обычно. */
  function attachDrag() {
    let startX = 0, dx = 0, active = false, moved = false, card = null;
    deck.addEventListener("pointerdown", e => {
      card = cards[0];
      if (!card || busy || !e.isPrimary || (e.pointerType === "mouse" && e.button !== 0)) return;
      if (e.target.closest("button, a, input, textarea, select")) return;
      if (card.classList.contains("expanded") && e.target.closest(".card-body")) return;  // раскрытый текст можно прокручивать
      active = true; moved = false; dx = 0; startX = e.clientX;
      try { deck.setPointerCapture(e.pointerId); } catch (err) { /* не критично */ }
    });
    deck.addEventListener("pointermove", e => {
      if (!active || !card) return;
      dx = e.clientX - startX;
      if (!moved && Math.abs(dx) < 6) return;   // лёгкое дрожание пальца не считаем свайпом
      moved = true; card.classList.add("dragging");
      card.style.transform = "translateX(" + dx + "px) rotate(" + dx / 22 + "deg)";
      card._like.style.opacity = Math.max(0, Math.min(1, dx / THRESHOLD));
      card._nope.style.opacity = Math.max(0, Math.min(1, -dx / THRESHOLD));
    });
    const end = () => {
      if (!active) return;
      active = false;
      if (!card) return;
      card.classList.remove("dragging");
      card._like.style.opacity = card._nope.style.opacity = 0;
      if (moved && Math.abs(dx) > THRESHOLD) decide(dx > 0); else card.style.transform = "";
      moved = false;
    };
    deck.addEventListener("pointerup", end);
    deck.addEventListener("pointercancel", end);
  }
  attachDrag();

  function render() {
    while (cards.length < 3 && queue.length) {
      const c = buildCard(queue.shift());
      cards.push(c); deck.appendChild(c); c._fit();
    }
    layout();
    const any = cards.length > 0;
    actions.hidden = hint.hidden = !any;
    empty.hidden = any || loading || !exhausted;
    if (queue.length < 3 && !exhausted && !loading) loadMore();
  }

  async function loadMore() {
    loading = true;
    try {
      const { profiles } = await DM.api("/api/feed/?limit=10" + filterQuery());
      const fresh = profiles.filter(p => !seen.has(p.uid));
      fresh.forEach(p => seen.add(p.uid));
      if (!fresh.length) exhausted = true;
      queue.push(...fresh);
    } catch (e) {
      DM.toast(e.message, "error"); exhausted = true;
    } finally { loading = false; deck.classList.remove("skeleton"); render(); }
  }

  async function decide(like) {
    if (busy || !cards.length) return;
    busy = true;
    const card = cards.shift(), p = card._profile;
    card.classList.remove("dragging");
    card.style.transform = "translateX(" + (like ? 140 : -140) + "%) rotate(" + (like ? 18 : -18) + "deg)";
    setTimeout(() => card.remove(), 260);
    render();
    try {
      const res = await DM.api("/api/swipes/", { method: "POST", json: { target_uid: p.uid, like } });
      if (res.matched) { showMatch(res); return; }
    } catch (e) {
      DM.toast("Не удалось сохранить выбор: " + e.message, "error");
      seen.delete(p.uid); // вернём анкету на верх ленты
      const rest = cards.map(c => c._profile);
      cards.forEach(c => c.remove()); cards = [];
      queue = [p, ...rest, ...queue];
      setTimeout(render, 280);
    }
    busy = false;
  }

  function showMatch(res) {
    document.getElementById("match-me").src = window.ME_PHOTO;
    document.getElementById("match-them").src = res.profile.photo_url;
    document.getElementById("match-text").textContent = "Вы и " + res.profile.name + " лайкнули друг друга";
    document.getElementById("match-chat").href = "/chat/" + res.match_id + "/";
    overlay.hidden = false;
    document.getElementById("match-chat").focus();
  }
  function closeMatch() { overlay.hidden = true; busy = false; }
  document.getElementById("match-close").addEventListener("click", closeMatch);

  document.getElementById("btn-like").addEventListener("click", () => decide(true));
  document.getElementById("btn-nope").addEventListener("click", () => decide(false));
  document.getElementById("reload").addEventListener("click", () => { exhausted = false; empty.hidden = true; loadMore(); });
  document.addEventListener("keydown", e => {
    if (!overlay.hidden) { if (e.key === "Escape") closeMatch(); return; }
    if (e.target.closest && e.target.closest("input, textarea, select") || !vmodal.hidden) return;
    if (e.key === "ArrowRight") decide(true);
    if (e.key === "ArrowLeft") decide(false);
  });

  /* ---------- фильтры ---------- */
  function filterQuery() {
    const q = [];
    if (filters.age_min) q.push("age_min=" + filters.age_min);
    if (filters.age_max) q.push("age_max=" + filters.age_max);
    if (filters.interests && filters.interests.length) q.push("interests=" + encodeURIComponent(filters.interests.join(",")));
    if (filters.goals && filters.goals.length) q.push("goals=" + encodeURIComponent(filters.goals.join(",")));
    if (filters.with_video) q.push("with_video=1");
    if (filters.with_music) q.push("with_music=1");
    return q.length ? "&" + q.join("&") : "";
  }
  function filterSummary() {
    const n = ["age_min", "age_max", "with_video", "with_music"].filter(k => filters[k]).length + ((filters.interests || []).length ? 1 : 0) + ((filters.goals || []).length ? 1 : 0);
    fcount.textContent = n ? "(" + n + ")" : ""; freset.hidden = !n;
  }
  function restart() {
    cards.forEach(c => c.remove()); cards = []; queue = []; seen = new Set(); exhausted = false; empty.hidden = true;
    deck.classList.add("skeleton"); loadMore();
  }
  fbtn.addEventListener("click", () => { fbox.hidden = !fbox.hidden; fbtn.setAttribute("aria-expanded", String(!fbox.hidden)); });
  function saveFilters() { try { localStorage.setItem("dm-filters", JSON.stringify(filters)); } catch (e) { /* ок */ } }
  fbox.addEventListener("submit", ev => {
    ev.preventDefault();
    const min = Number(document.getElementById("f-min").value) || 0, max = Number(document.getElementById("f-max").value) || 0;
    const err = (min && (min < 18 || min > 99)) || (max && (max < 18 || max > 99)) ? "Возраст — от 18 до 99"
      : (min && max && min > max) ? "Минимальный возраст больше максимального" : "";
    document.getElementById("f-error").textContent = err;
    if (err) return;
    filters = { age_min: min || 0, age_max: max || 0, interests: chosenBox.getChosen ? chosenBox.getChosen() : [], goals: goalBox.getChosen ? goalBox.getChosen() : [],
      with_video: document.getElementById("f-video").checked, with_music: document.getElementById("f-music").checked };
    saveFilters(); filterSummary(); fbox.hidden = true; fbtn.setAttribute("aria-expanded", "false"); restart();
  });
  freset.addEventListener("click", async () => {
    filters = {}; saveFilters(); filterSummary(); fillFilterForm(); restart();
  });
  async function fillFilterForm() {
    document.getElementById("f-min").value = filters.age_min || ""; document.getElementById("f-max").value = filters.age_max || "";
    renderGoals(filters.goals || []);
    document.getElementById("f-video").checked = !!filters.with_video; document.getElementById("f-music").checked = !!filters.with_music;
    try { await window.ProfileForm.renderInterests(chosenBox, filters.interests || []); } catch (e) { /* список подгрузится позже */ }
  }
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !vmodal.hidden) closeVideo(); });

  filterSummary(); fillFilterForm();
  deck.classList.add("skeleton");
  loadMore();

  /* подсказка для новичков: показываем один раз */
  (function () {
    const tip = document.getElementById("tip"); if (!tip) return;
    let seenTip = false; try { seenTip = localStorage.getItem("dm-tip") === "1"; } catch (e) { /* ок */ }
    tip.hidden = seenTip;
    document.getElementById("tip-close").addEventListener("click", () => {
      tip.hidden = true; try { localStorage.setItem("dm-tip", "1"); } catch (e) { /* ок */ }
    });
  })();
  window.addEventListener("resize", () => cards.forEach(c => c._fit && c._fit()));
})();
