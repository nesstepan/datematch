(function () {
  const root = document.querySelector(".chat"), mid = root.dataset.match;
  const $ = id => document.getElementById(id);
  const box = $("messages"), form = $("send-form"), input = $("text"), btn = $("send-btn");
  const seen = new Set(), els = new Map(); let last = 0, failing = false, gone = false, busy = false;
  let receipts = { read_at: 0, delivered_at: 0 }, idle = 0, typingEl = null, lastTyping = 0;
  const base = "/api/matches/" + mid + "/messages/";
  const MB = 1024 * 1024, VIDEO_MAX = 15 * MB;
  const deletedIds = new Set();            // id удалённых сообщений (чтобы цитаты на них не показывали текст)
  let replyTo = null;                      // сообщение, на которое сейчас отвечаем
  const RX = { heart: ["heart", "Сердце"], like: ["thumb", "Класс"], fire: ["flame", "Огонь"], laugh: ["laugh", "Смешно"], sad: ["sad", "Грустно"], wow: ["wow", "Ого"] };
  const KIND = { image: "Фото", gif: "GIF", video: "Видео", voice: "Голосовое сообщение", gift: "Подарок" };

  const placeholder = DM.el("p", "muted center", "Пока тихо. Напишите первым.");
  box.appendChild(placeholder);

  /* ---------- отрисовка ---------- */
  function fmtDur(s) { return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }

  function openViewer(node) {
    const body = $("viewer-body"); body.textContent = ""; body.appendChild(node); $("viewer").hidden = false;
  }
  $("viewer-close").addEventListener("click", () => { $("viewer").hidden = true; $("viewer-body").textContent = ""; });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("viewer").hidden) $("viewer-close").click(); });

  /* Цитата: кто и что процитирован. Нажатие прокручивает чат к исходному сообщению. */
  function quoteEl(r) {
    const gone = r.deleted || deletedIds.has(r.id);
    const q = DM.el("button", "quote" + (gone ? " gone" : "")); q.type = "button";
    q.setAttribute("aria-label", "Перейти к сообщению, на которое это ответ");
    q.appendChild(DM.el("strong", "", r.mine ? "Вы" : root.dataset.other));
    q.appendChild(DM.el("span", "", gone ? "Сообщение удалено" : (r.text || KIND[r.type] || "Сообщение")));
    q.addEventListener("click", () => jumpTo(r.id));
    return q;
  }
  function jumpTo(id) {
    const d = els.get(id);
    if (!d) { DM.toast("Это сообщение выше. Прокрутите историю вверх."); return; }
    d.scrollIntoView({ block: "center", behavior: "smooth" });
    d.classList.add("flash"); setTimeout(() => d.classList.remove("flash"), 1700);
  }

  function fill(d, m) {
    d.textContent = "";
    d.className = "msg " + (m.mine ? "mine" : "theirs");
    if (m.deleted) {
      d.classList.add("gone"); d.textContent = "Сообщение удалено"; return;
    }
    if (m.reply_to) d.appendChild(quoteEl(m.reply_to));
    if (m.id) {   // кнопка для компьютера: появляется при наведении, доступна и с клавиатуры
      const rb = DM.el("button", "reply-btn"); rb.type = "button"; rb.title = "Ответить"; rb.setAttribute("aria-label", "Ответить на сообщение");
      rb.appendChild(DM.icon("reply")); rb.addEventListener("click", () => setReply(m)); d.appendChild(rb);
      const xb = DM.el("button", "reply-btn react-btn"); xb.type = "button"; xb.title = "Реакция"; xb.setAttribute("aria-label", "Поставить реакцию");
      xb.appendChild(DM.icon("smile")); xb.addEventListener("click", e => { const r = xb.getBoundingClientRect(); openMenu(d, r.left, r.bottom + 4); }); d.appendChild(xb);
    }
    if (m.type === "gift" && m.gift) {
      d.classList.add("gift");
      const gi = DM.el("div", "gift-ic"); gi.appendChild(DM.icon(m.gift.icon)); d.appendChild(gi);
      d.appendChild(DM.el("small", "", (m.mine ? "Вы подарили: " : "Вам подарили: ") + m.gift.title));
    } else if (m.type === "image" || m.type === "gif") {
      const img = DM.el("img", "att"); img.src = m.media_url; img.loading = "lazy"; img.alt = m.type === "gif" ? "GIF" : "Фото";
      img.addEventListener("click", () => { const big = DM.el("img"); big.src = m.media_url; big.alt = img.alt; openViewer(big); });
      d.appendChild(img);
    } else if (m.type === "video") {
      const v = DM.el("video", "att"); v.src = m.media_url; v.controls = true; v.preload = "metadata"; v.playsInline = true;
      d.appendChild(v);
    } else if (m.type === "voice") {
      const a = DM.el("audio"); a.src = m.media_url; a.controls = true; a.preload = "metadata";
      d.appendChild(a);
      if (m.duration) { const vd = DM.el("small", "vdur"); vd.appendChild(DM.icon("mic")); vd.appendChild(document.createTextNode(fmtDur(m.duration))); d.appendChild(vd); }
    }
    if (m.text) d.appendChild(DM.el("div", "", m.text));
    const meta = DM.el("time", "", new Date(m.created_at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    if (m.mine) {
      meta.appendChild(DM.el("span", "ticks"));
      const del = DM.el("button", "del-btn"); del.type = "button"; del.title = "Удалить сообщение"; del.setAttribute("aria-label", "Удалить сообщение"); del.appendChild(DM.icon("trash"));
      del.addEventListener("click", () => removeMessage(m.id));
      meta.appendChild(del);
    }
    d.appendChild(meta);
    renderReactions(d, m.reactions);
  }

  /* ---------- реакции ---------- */
  function renderReactions(d, list) {
    if (d._m && d._m.deleted) return;
    if (d._m) d._m.reactions = list || [];
    let row = d.querySelector(".reactions");
    if (!row) { row = DM.el("div", "reactions"); const t = d.querySelector("time"); d.insertBefore(row, t || null); }
    row.textContent = "";
    (list || []).forEach(r => {
      const b = DM.el("button", "rx" + (r.mine ? " mine" : "")); b.type = "button"; b.dataset.kind = r.kind;
      b.setAttribute("aria-label", RX[r.kind][1] + (r.count > 1 ? ", " + r.count : "") + (r.mine ? ". Нажмите, чтобы убрать" : ""));
      b.appendChild(DM.icon(RX[r.kind][0], r.kind === "heart" || r.kind === "fire" ? "fill" : ""));
      if (r.count > 1) b.appendChild(document.createTextNode(String(r.count)));
      b.addEventListener("click", () => react(d._m, r.mine ? null : r.kind));
      row.appendChild(b);
    });
  }
  async function react(m, kind) {
    if (!m || !m.id) return;
    try {
      const r = kind ? await DM.api(base + m.id + "/reaction/", { method: "POST", json: { kind } }) : await DM.api(base + m.id + "/reaction/", { method: "DELETE" });
      const d = els.get(m.id); if (d) renderReactions(d, r.reactions);
    } catch (e) { DM.toast(e.message, "error"); }
  }
  function applyReactions(map) {   // реакции собеседника на любые сообщения приходят с каждым опросом
    els.forEach((d, id) => {
      const now = (map && map[id]) || [];
      const before = (d._m && d._m.reactions) || [];
      if (JSON.stringify(now) !== JSON.stringify(before)) renderReactions(d, now);
    });
  }

  const STATUS = { sent: "Отправлено", delivered: "Доставлено", read: "Прочитано" };
  function statusOf(m) { return m.created_at <= receipts.read_at ? "read" : m.created_at <= receipts.delivered_at ? "delivered" : "sent"; }
  function updateTicks() {
    els.forEach(d => {
      if (!d._m || !d._m.mine || d._m.deleted) return;
      const t = d.querySelector(".ticks"); if (!t) return;
      const st = statusOf(d._m); if (t.dataset.st === st) return;
      t.dataset.st = st; t.className = "ticks" + (st === "read" ? " read" : ""); t.title = STATUS[st]; t.setAttribute("aria-label", STATUS[st]);
      t.textContent = ""; t.appendChild(DM.icon(st === "sent" ? "check" : "check-check"));
    });
  }
  function showTyping(on) {
    if (on && !typingEl) {
      typingEl = DM.el("div", "typing"); const dots = DM.el("span", "typing-dots"); dots.append(DM.el("i"), DM.el("i"), DM.el("i"));
      typingEl.append(dots, document.createTextNode(root.dataset.other + " печатает…"));
      const stick = nearBottom(); box.appendChild(typingEl); if (stick) toBottom();
    } else if (!on && typingEl) { typingEl.remove(); typingEl = null; }
  }
  const presenceEl = $("chat-presence"), presenceDefault = presenceEl ? presenceEl.textContent : "";
  function showPresence(o) {
    if (!presenceEl || !o) return;
    const t = DM.lastSeen(o.online, o.last_seen);
    presenceEl.textContent = ""; 
    if (t) { presenceEl.appendChild(DM.el("span", "online-dot" + (o.online ? "" : " off"))); presenceEl.appendChild(document.createTextNode(" " + t)); }
    else presenceEl.textContent = presenceDefault;
  }

  function add(m) {
    if (seen.has(m.id)) return;
    seen.add(m.id); placeholder.remove();
    const d = DM.el("div"); fill(d, m); els.set(m.id, d); d._m = m;
    if (typingEl) box.insertBefore(d, typingEl); else box.appendChild(d);
    updateTicks();
    last = Math.max(last, m.created_at);
  }
  function markGone(id) {
    deletedIds.add(id);
    if (replyTo && replyTo.id === id) clearReply();
    els.forEach(o => {   // сообщения, цитирующие удалённое, перестают показывать его текст
      if (o._m && o._m.reply_to && o._m.reply_to.id === id && !o._m.deleted) { o._m = { ...o._m, reply_to: { ...o._m.reply_to, deleted: true, text: "" } }; fill(o, o._m); }
    });
    const d = els.get(id); if (!d || (d._m && d._m.deleted)) return;
    d._m = { ...d._m, deleted: true }; fill(d, d._m); updateTicks();
  }
  const nearBottom = () => box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  const toBottom = () => { box.scrollTop = box.scrollHeight; };

  async function removeMessage(id) {
    if (!confirm("Удалить сообщение? Оно исчезнет у вас обоих.")) return;
    try { await DM.api(base + id + "/", { method: "DELETE" }); markGone(id); }
    catch (e) { if (e.status === 404 && e.message.includes("Пара")) closed(); else DM.toast(e.message, "error"); }
  }

  function closed() {
    gone = true; input.disabled = btn.disabled = true;
    DM.toast("Пара больше не существует", "error");
    setTimeout(() => { location.href = "/matches/"; }, 1500);
  }

  /* ---------- опрос ---------- */
  async function poll(initial) {
    if (gone || document.hidden) return;
    try {
      const data = await DM.api(base + (last ? "?since=" + last : ""));
      const { messages, deleted } = data;
      const stick = initial || nearBottom();
      if (data.receipts) receipts = data.receipts;
      messages.forEach(add);
      (deleted || []).forEach(markGone);
      applyReactions(data.reactions);
      updateTicks(); showTyping(!!data.typing); showPresence(data.other);
      if (stick && messages.length) toBottom();
      idle = (messages.length || (deleted || []).length || data.typing) ? 0 : idle + 1;
      failing = false;
    } catch (e) {
      if (e.status === 404) return closed();
      if (!failing) DM.toast("Нет связи, пробуем переподключиться…", "error");
      failing = true;
    }
  }

  /* ---------- отправка ---------- */
  function takeReply() { const r = replyTo; clearReply(); return r ? r.id : null; }
  async function post(opts, okText) {
    if (busy) return; busy = true; btn.disabled = true;
    const replyId = takeReply();
    if (replyId) { if (opts.form) opts.form.append("reply_to", replyId); else if (opts.json) opts.json = { ...opts.json, reply_to: replyId }; }
    try {
      const { message } = await DM.api(base, { method: "POST", ...opts });
      add(message); toBottom(); if (okText) DM.toast(okText);
      return true;
    } catch (e) {
      if (e.status === 404 && e.message.includes("Пара")) closed(); else DM.toast("Не отправлено: " + e.message, "error");
    } finally { busy = false; if (!gone) { btn.disabled = false; input.focus(); } }
  }

  input.addEventListener("input", () => {
    idle = 0;
    if (!input.value.trim() || Date.now() - lastTyping < 3000) return;
    lastTyping = Date.now();
    DM.api("/api/matches/" + mid + "/typing/", { method: "POST" }).catch(() => { /* не критично */ });
  });

  /* Текст появляется в чате мгновенно (серым, «отправляется…»), а на сервер уходит в фоне. Если связи нет,
     сообщение не пропадает: рядом появляются кнопки «Повторить» и «Убрать». Порядок отправки сохраняется. */
  let queue = Promise.resolve();
  function sendText(text) {
    const reply = replyTo; clearReply();
    const tmp = DM.el("div", "msg mine pending");
    if (reply) tmp.appendChild(quoteEl({ id: reply.id, mine: reply.mine, text: reply.text, type: reply.type }));
    tmp.appendChild(DM.el("div", "", text));
    tmp.appendChild(DM.el("time", "", "отправляется…"));
    placeholder.remove();
    if (typingEl) box.insertBefore(tmp, typingEl); else box.appendChild(tmp);
    toBottom(); idle = 0;
    const job = async () => {
      tmp.className = "msg mine pending"; tmp.querySelector(".retry")?.remove();
      try {
        const { message } = await DM.api(base, { method: "POST", json: reply ? { text, reply_to: reply.id } : { text } });
        if (seen.has(message.id)) { tmp.remove(); return; }       // опрос уже успел принести это сообщение
        seen.add(message.id); fill(tmp, message); els.set(message.id, tmp); tmp._m = message;
        last = Math.max(last, message.created_at); updateTicks();
      } catch (e) {
        if (e.status === 404 && (e.message || "").includes("Пара")) { tmp.remove(); return closed(); }
        tmp.className = "msg mine failed";
        const r = DM.el("div", "retry", "Не отправлено. "); const again = DM.el("button", "link-btn", "Повторить"), drop = DM.el("button", "link-btn", "Убрать");
        again.type = drop.type = "button";
        again.addEventListener("click", () => { queue = queue.then(job); });
        drop.addEventListener("click", () => tmp.remove());
        r.append(again, drop); tmp.appendChild(r);
      }
    };
    queue = queue.then(job);
  }

  form.addEventListener("submit", ev => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    if (text.length > 1000) { DM.toast("Сообщение длиннее 1000 символов", "error"); return; }
    input.value = ""; input.focus(); lastTyping = 0;
    sendText(text);
  });

  /* фото, GIF, видео */
  const fileInput = $("file");
  $("attach-btn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    let f = fileInput.files[0]; fileInput.value = "";
    if (!f) return;
    const isGif = f.type === "image/gif", isVid = f.type.startsWith("video/"), isImg = f.type.startsWith("image/");
    if (!isImg && !isVid) { DM.toast("Нужно фото, GIF или видео", "error"); return; }
    if (isVid && f.size > VIDEO_MAX) {
      if (!confirm("Видео больше " + VIDEO_MAX / MB + " МБ. Сжать его автоматически? Это займёт примерно столько же времени, сколько длится ролик.")) return;
      try { f = await compressVideo(f); } catch (e) { DM.toast(e.message, "error"); return; }
      if (!f) return;
      if (f.size > VIDEO_MAX) { DM.toast("Даже после сжатия видео больше " + VIDEO_MAX / MB + " МБ. Выберите ролик покороче.", "error"); return; }
    }
    const limit = isGif ? 3 * MB : isVid ? VIDEO_MAX : 5 * MB;
    if (f.size > limit) { DM.toast("Файл больше " + (limit / MB) + " МБ — выберите поменьше", "error"); return; }
    const fd = new FormData(); fd.append("file", f);
    if (input.value.trim()) fd.append("text", input.value.trim());
    DM.toast("Отправляем…");
    if (await post({ form: fd })) input.value = "";
  });

  /* голосовые */
  let rec = null, recStream = null, chunks = [], t0 = 0, tick = null, send = true;
  const mic = $("mic-btn");
  function stopRec(sendIt) { send = sendIt; if (rec && rec.state !== "inactive") rec.stop(); }
  async function startRec() {
    if (!navigator.mediaDevices || !window.MediaRecorder) { DM.toast("Браузер не поддерживает запись голоса", "error"); return; }
    try { recStream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { DM.toast("Нет доступа к микрофону", "error"); return; }
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"].find(t => MediaRecorder.isTypeSupported(t));
    rec = new MediaRecorder(recStream, mime ? { mimeType: mime } : undefined); chunks = []; send = true;
    rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = async () => {
      clearInterval(tick); recStream.getTracks().forEach(t => t.stop());
      form.classList.remove("recording");
      const dur = Math.round((Date.now() - t0) / 1000), blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
      rec = null;
      if (!send) return;
      if (dur < 1 || !blob.size) { DM.toast("Слишком короткое сообщение", "error"); return; }
      if (blob.size > 2 * MB) { DM.toast("Голосовое больше 2 МБ — запишите покороче", "error"); return; }
      const ext = blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
      const fd = new FormData(); fd.append("file", blob, "voice." + ext); fd.append("kind", "voice"); fd.append("duration", dur);
      await post({ form: fd });
    };
    t0 = Date.now(); rec.start(); form.classList.add("recording");
    tick = setInterval(() => {
      const s = Math.round((Date.now() - t0) / 1000); $("rec-time").textContent = fmtDur(s);
      if (s >= 120) stopRec(true);
    }, 500);
  }
  mic.addEventListener("click", () => { if (rec) stopRec(true); else startRec(); });
  $("rec-cancel").addEventListener("click", () => stopRec(false));

  /* подарки */
  const panel = $("gift-panel"); let giftsLoaded = false;
  $("gift-btn").addEventListener("click", async () => {
    panel.hidden = !panel.hidden;
    if (panel.hidden || giftsLoaded) return;
    try {
      const { gifts } = await DM.api("/api/gifts/");
      gifts.forEach(g => {
        const b = DM.el("button"); b.type = "button"; b.appendChild(DM.icon(g.icon)); b.appendChild(document.createTextNode(g.title));
        b.addEventListener("click", async () => { panel.hidden = true; await post({ json: { gift: g.id } }); });
        panel.appendChild(b);
      });
      giftsLoaded = true;
    } catch (e) { DM.toast(e.message, "error"); panel.hidden = true; }
  });


  /* ---------- ответы на сообщения ---------- */
  const rbar = $("reply-bar"), rbName = $("rb-name"), rbText = $("rb-text");
  function setReply(m) {
    if (!m || !m.id || m.deleted) return;
    const text = m.text || (m.gift ? "Подарок: " + m.gift.title : KIND[m.type]) || "Сообщение";
    replyTo = { id: m.id, mine: !!m.mine, text: text.slice(0, 140), type: m.type };
    rbName.textContent = "Ответ " + (m.mine ? "себе" : root.dataset.other); rbText.textContent = replyTo.text;
    rbar.hidden = false; input.focus();
  }
  function clearReply() { replyTo = null; rbar.hidden = true; }
  $("rb-close").addEventListener("click", () => { clearReply(); input.focus(); });
  input.addEventListener("keydown", e => { if (e.key === "Escape" && replyTo) { clearReply(); e.stopPropagation(); } });

  /* Меню по правой кнопке мыши (на телефоне то же самое открывается долгим нажатием). */
  let menu = null;
  function closeMenu() { if (menu) { menu.remove(); menu = null; } }
  function openMenu(d, x, y) {
    closeMenu();
    const m = d._m; if (!m || !m.id || m.deleted) return;
    menu = DM.el("div", "msg-menu"); menu.setAttribute("role", "menu");
    const mine = ((m.reactions || []).find(r => r.mine) || {}).kind;
    const rowEl = DM.el("div", "react-row"); rowEl.setAttribute("role", "group"); rowEl.setAttribute("aria-label", "Реакция");
    Object.keys(RX).forEach(k => {
      const b = DM.el("button", mine === k ? "on" : ""); b.type = "button"; b.title = RX[k][1]; b.setAttribute("aria-label", RX[k][1]);
      b.appendChild(DM.icon(RX[k][0], k === "heart" || k === "fire" ? "fill" : ""));
      b.addEventListener("click", () => { closeMenu(); react(m, mine === k ? null : k); });
      rowEl.appendChild(b);
    });
    menu.appendChild(rowEl);
    const item = (icon, label, fn, danger) => {
      const b = DM.el("button", danger ? "danger" : ""); b.type = "button"; b.setAttribute("role", "menuitem");
      b.appendChild(DM.icon(icon)); b.appendChild(document.createTextNode(label));
      b.addEventListener("click", () => { closeMenu(); fn(); }); menu.appendChild(b);
    };
    item("reply", "Ответить", () => setReply(m));
    if (m.text && navigator.clipboard) item("copy", "Копировать текст", () => navigator.clipboard.writeText(m.text).then(() => DM.toast("Скопировано")).catch(() => {}));
    if (m.mine) item("trash", "Удалить", () => removeMessage(m.id), true);
    document.body.appendChild(menu);
    const r = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + "px";
    menu.style.top = Math.max(8, Math.min(y, innerHeight - r.height - 8)) + "px";
    (menu.querySelector(".react-row + button") || menu.querySelector("button")).focus();
  }
  box.addEventListener("contextmenu", e => {
    const d = e.target.closest(".msg"); if (!d || !d._m || d._m.deleted || !d._m.id) return;
    if (e.target.closest("a, input, audio")) return;
    e.preventDefault(); openMenu(d, e.clientX, e.clientY);
  });
  document.addEventListener("pointerdown", e => { if (menu && !menu.contains(e.target)) closeMenu(); }, true);
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeMenu(); });
  box.addEventListener("scroll", closeMenu, { passive: true });

  /* Свайп вправо по сообщению (на сенсорном экране): ответить. Тянем сообщение, при ~60 px отпускаем. */
  (function swipeToReply() {
    let d = null, x0 = 0, y0 = 0, dx = 0, active = false, armed = false;
    const REACH = 64;
    box.addEventListener("pointerdown", e => {
      if (e.pointerType === "mouse" || !e.isPrimary) return;
      const el = e.target.closest(".msg"); if (!el || !el._m || el._m.deleted || !el._m.id || e.target.closest("button, a, audio, video, input")) return;
      d = el; x0 = e.clientX; y0 = e.clientY; dx = 0; active = true; armed = false;
    });
    box.addEventListener("pointermove", e => {
      if (!active || !d) return;
      const mx = e.clientX - x0, my = e.clientY - y0;
      if (!armed) {   // жест начинаем, только если палец ведёт вправо заметно сильнее, чем вниз-вверх
        if (Math.abs(my) > 14 && Math.abs(my) > Math.abs(mx)) { active = false; return; }
        if (mx > 12 && mx > Math.abs(my) * 1.4) { armed = true; d.classList.add("swiping"); try { box.setPointerCapture(e.pointerId); } catch (err) { /* ок */ } }
        else return;
      }
      dx = Math.max(0, Math.min(mx, 96));
      d.style.transform = "translateX(" + dx + "px)"; d.style.setProperty("--sw", Math.min(1, dx / REACH));
    });
    const end = () => {
      if (!active) return; active = false;
      if (d) {
        const go = armed && dx >= REACH, m = d._m;
        d.classList.remove("swiping"); d.style.transform = ""; d.style.removeProperty("--sw");
        if (go) { if (navigator.vibrate) navigator.vibrate(12); setReply(m); }
      }
      d = null; armed = false;
    };
    box.addEventListener("pointerup", end); box.addEventListener("pointercancel", end);
  })();

  /* ---------- видео в чате ---------- */
  function pickVideoMime() {
    return ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4"].find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
  }
  function videoModal(title) {
    const wrap = DM.el("div", "modal vid-modal"); wrap.setAttribute("role", "dialog"); wrap.setAttribute("aria-modal", "true"); wrap.setAttribute("aria-label", title);
    const boxEl = DM.el("div", "panel vid-box"); boxEl.appendChild(DM.el("h2", "", title)); wrap.appendChild(boxEl);
    document.body.classList.add("no-scroll"); document.body.appendChild(wrap);
    return { wrap, box: boxEl, close() { document.body.classList.remove("no-scroll"); wrap.remove(); } };
  }

  /* Запись видеосообщения прямо в чате: до 45 секунд (чтобы файл остался небольшим). */
  async function recordVideoMessage() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) { DM.toast("Этот браузер не умеет записывать видео. Выберите файл через скрепку.", "error"); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 720 } }, audio: true }); }
    catch (e) { DM.toast("Нет доступа к камере или микрофону", "error"); return; }
    const M = videoModal("Видеосообщение");
    const view = DM.el("video", "vid-view"); view.autoplay = true; view.muted = true; view.playsInline = true; view.srcObject = stream;
    const time = DM.el("p", "vid-time", "0:00 / 0:45");
    const bar = DM.el("div", "row");
    const rec = DM.el("button", "btn"), cancel = DM.el("button", "btn ghost", "Отмена"); rec.type = cancel.type = "button";
    DM.setIcon(rec, "video", "Начать запись"); bar.append(rec, cancel); M.box.append(view, time, bar);
    let mr = null, chunks = [], t0 = 0, tick = null, blob = null, url = "";
    const MAX = 45;
    const stopTracks = () => stream.getTracks().forEach(t => t.stop());
    const finish = () => { clearInterval(tick); stopTracks(); if (url) URL.revokeObjectURL(url); M.close(); };
    cancel.addEventListener("click", () => { if (mr && mr.state === "recording") { mr.onstop = null; mr.stop(); } finish(); });
    M.wrap.addEventListener("keydown", e => { if (e.key === "Escape") cancel.click(); });
    function review() {
      stopTracks(); view.srcObject = null; view.muted = false; view.controls = true; url = URL.createObjectURL(blob); view.src = url; view.autoplay = false;
      time.textContent = "Проверьте запись и отправьте";
      bar.textContent = "";
      const send = DM.el("button", "btn"), again = DM.el("button", "btn ghost", "Переснять"), drop = DM.el("button", "link-btn", "Отмена"); send.type = again.type = drop.type = "button";
      DM.setIcon(send, "send", "Отправить"); bar.append(send, again, drop);
      drop.addEventListener("click", finish);
      again.addEventListener("click", () => { finish(); recordVideoMessage(); });
      send.addEventListener("click", async () => {
        if (blob.size > VIDEO_MAX) { DM.toast("Запись получилась больше " + VIDEO_MAX / MB + " МБ. Запишите покороче.", "error"); return; }
        const ext = blob.type.includes("mp4") ? "mp4" : "webm", fd = new FormData(); fd.append("file", new File([blob], "video." + ext, { type: blob.type }));
        finish(); DM.toast("Отправляем видео…"); await post({ form: fd });
      });
    }
    rec.addEventListener("click", () => {
      if (mr && mr.state === "recording") { mr.stop(); return; }
      const mime = pickVideoMime(); chunks = [];
      try { mr = new MediaRecorder(stream, mime ? { mimeType: mime, videoBitsPerSecond: 1000000, audioBitsPerSecond: 64000 } : undefined); }
      catch (e) { DM.toast("Не удалось начать запись", "error"); return; }
      mr.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      mr.onstop = () => { clearInterval(tick); blob = new Blob(chunks, { type: mr.mimeType || mime || "video/webm" }); if (!blob.size) { DM.toast("Запись пустая", "error"); finish(); return; } review(); };
      mr.start(500); t0 = Date.now(); DM.setIcon(rec, "stop", "Остановить"); rec.classList.add("rec-on");
      tick = setInterval(() => {
        const s = Math.round((Date.now() - t0) / 1000); time.textContent = fmtDur(s) + " / " + fmtDur(MAX);
        if (s >= MAX) mr.stop();
      }, 250);
    });
    rec.focus();
  }
  $("vid-btn").addEventListener("click", recordVideoMessage);

  /* Если выбранное видео больше лимита, пробуем сжать его прямо в браузере: воспроизводим его на холсте и пишем заново
     с меньшим битрейтом. Это занимает столько же времени, сколько длится ролик. */
  async function compressVideo(file) {
    if (!window.MediaRecorder || !HTMLCanvasElement.prototype.captureStream) throw new Error("Браузер не умеет сжимать видео. Выберите ролик поменьше.");
    const url = URL.createObjectURL(file), v = document.createElement("video");
    v.src = url; v.playsInline = true; v.preload = "auto";
    await new Promise((res, rej) => { v.onloadedmetadata = res; v.onerror = () => rej(new Error("Не удалось прочитать это видео. Возможно, браузер не поддерживает его формат.")); });
    const dur = v.duration;
    if (!isFinite(dur) || dur > 180) { URL.revokeObjectURL(url); throw new Error("Видео длиннее 3 минут. Обрежьте его."); }
    const k = Math.min(1, 960 / Math.max(v.videoWidth, v.videoHeight)), w = Math.round(v.videoWidth * k / 2) * 2, h = Math.round(v.videoHeight * k / 2) * 2;
    const canvas = document.createElement("canvas"); canvas.width = w; canvas.height = h; const ctx = canvas.getContext("2d");
    const out = canvas.captureStream(30); let ac = null;
    try { ac = new (window.AudioContext || window.webkitAudioContext)(); const src = ac.createMediaElementSource(v), dest = ac.createMediaStreamDestination(); src.connect(dest); dest.stream.getAudioTracks().forEach(t => out.addTrack(t)); await ac.resume(); } catch (e) { ac = null; }
    const target = VIDEO_MAX * 0.72, bps = Math.max(250000, Math.min(2500000, Math.floor(target * 8 / dur - 64000)));
    const mime = pickVideoMime(), mr = new MediaRecorder(out, mime ? { mimeType: mime, videoBitsPerSecond: bps, audioBitsPerSecond: 64000 } : { videoBitsPerSecond: bps });
    const parts = []; mr.ondataavailable = e => { if (e.data.size) parts.push(e.data); };
    const M = videoModal("Сжимаем видео"); const prog = DM.el("progress"); prog.max = 100; prog.value = 0;
    const note = DM.el("p", "muted small", "Не закрывайте и не сворачивайте вкладку: видео пересохраняется в реальном времени."); const stop = DM.el("button", "btn ghost", "Отмена"); stop.type = "button";
    M.box.append(prog, note, stop);
    let cancelled = false; stop.addEventListener("click", () => { cancelled = true; v.pause(); try { mr.stop(); } catch (e) { /* ок */ } });
    const finished = new Promise(res => { mr.onstop = res; });
    mr.start(500); await v.play();
    const draw = () => { ctx.drawImage(v, 0, 0, w, h); prog.value = Math.min(100, Math.round(v.currentTime / dur * 100)); if (!v.ended && !cancelled) requestAnimationFrame(draw); };
    draw(); await new Promise(res => { v.onended = res; const t = setInterval(() => { if (cancelled) { clearInterval(t); res(); } }, 300); });
    if (mr.state !== "inactive") mr.stop();
    await finished; M.close(); URL.revokeObjectURL(url); if (ac) ac.close().catch(() => {});
    if (cancelled) return null;
    const blob = new Blob(parts, { type: mr.mimeType || mime || "video/webm" });
    return new File([blob], "video." + (blob.type.includes("mp4") ? "mp4" : "webm"), { type: blob.type });
  }

  /* меню «Ещё»: жалоба, чёрный список, разрыв пары */
  const menuBtn = $("menu-btn"), pop = $("menu-pop"), otherUid = root.dataset.otherUid, otherName = root.dataset.other;
  menuBtn.addEventListener("click", ev => { ev.stopPropagation(); pop.hidden = !pop.hidden; menuBtn.setAttribute("aria-expanded", String(!pop.hidden)); });
  document.addEventListener("click", ev => { if (!pop.hidden && !pop.contains(ev.target)) { pop.hidden = true; menuBtn.setAttribute("aria-expanded", "false"); } });
  $("chat-report").addEventListener("click", async () => {
    pop.hidden = true; const r = await DM.reportDialog(otherUid, otherName, "chat"); if (r.blocked) location.href = "/matches/";
  });
  $("chat-block").addEventListener("click", async () => { pop.hidden = true; if (await DM.blockUser(otherUid, otherName)) location.href = "/matches/"; });

  $("unmatch").addEventListener("click", async () => {
    if (!confirm("Разорвать пару? Переписка удалится у вас обоих.")) return;
    try { await DM.api("/api/matches/" + mid + "/", { method: "DELETE" }); location.href = "/matches/"; }
    catch (e) { DM.toast(e.message, "error"); }
  });

  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(false); });
  poll(true);
  (async function loop() {  // реже опрашиваем, когда в чате давно тихо (экономим квоту базы)
    await new Promise(r => setTimeout(r, idle <= 12 ? 1500 : idle <= 40 ? 3000 : 8000));
    await poll(false); loop();
  })();
})();
