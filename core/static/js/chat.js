(function () {
  const root = document.querySelector(".chat"), mid = root.dataset.match;
  const $ = id => document.getElementById(id);
  const box = $("messages"), form = $("send-form"), input = $("text"), btn = $("send-btn");
  const seen = new Set(), els = new Map(); let last = 0, failing = false, gone = false, busy = false;
  const base = "/api/matches/" + mid + "/messages/";
  const MB = 1024 * 1024;

  const placeholder = DM.el("p", "muted center", "Пока тихо. Напишите первым.");
  box.appendChild(placeholder);

  /* ---------- отрисовка ---------- */
  function fmtDur(s) { return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }

  function openViewer(node) {
    const body = $("viewer-body"); body.textContent = ""; body.appendChild(node); $("viewer").hidden = false;
  }
  $("viewer-close").addEventListener("click", () => { $("viewer").hidden = true; $("viewer-body").textContent = ""; });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("viewer").hidden) $("viewer-close").click(); });

  function fill(d, m) {
    d.textContent = "";
    d.className = "msg " + (m.mine ? "mine" : "theirs");
    if (m.deleted) {
      d.classList.add("gone"); d.textContent = "Сообщение удалено"; return;
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
      const del = DM.el("button", "del-btn"); del.type = "button"; del.title = "Удалить сообщение"; del.setAttribute("aria-label", "Удалить сообщение"); del.appendChild(DM.icon("trash"));
      del.addEventListener("click", () => removeMessage(m.id));
      meta.appendChild(del);
    }
    d.appendChild(meta);
  }

  function add(m) {
    if (seen.has(m.id)) return;
    seen.add(m.id); placeholder.remove();
    const d = DM.el("div"); fill(d, m); els.set(m.id, d); d._m = m; box.appendChild(d);
    last = Math.max(last, m.created_at);
  }
  function markGone(id) {
    const d = els.get(id); if (!d || (d._m && d._m.deleted)) return;
    d._m = { ...d._m, deleted: true }; fill(d, d._m);
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
      const { messages, deleted } = await DM.api(base + (last ? "?since=" + last : ""));
      const stick = initial || nearBottom();
      messages.forEach(add);
      (deleted || []).forEach(markGone);
      if (stick && messages.length) toBottom();
      failing = false;
    } catch (e) {
      if (e.status === 404) return closed();
      if (!failing) DM.toast("Нет связи, пробуем переподключиться…", "error");
      failing = true;
    }
  }

  /* ---------- отправка ---------- */
  async function post(opts, okText) {
    if (busy) return; busy = true; btn.disabled = true;
    try {
      const { message } = await DM.api(base, { method: "POST", ...opts });
      add(message); toBottom(); if (okText) DM.toast(okText);
      return true;
    } catch (e) {
      if (e.status === 404 && e.message.includes("Пара")) closed(); else DM.toast("Не отправлено: " + e.message, "error");
    } finally { busy = false; if (!gone) { btn.disabled = false; input.focus(); } }
  }

  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    if (text.length > 1000) { DM.toast("Сообщение длиннее 1000 символов", "error"); return; }
    if (await post({ json: { text } })) input.value = "";
  });

  /* фото, GIF, видео */
  const fileInput = $("file");
  $("attach-btn").addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const f = fileInput.files[0]; fileInput.value = "";
    if (!f) return;
    const isGif = f.type === "image/gif", isVid = f.type.startsWith("video/"), isImg = f.type.startsWith("image/");
    const limit = isGif ? 3 * MB : isVid ? 6 * MB : 5 * MB;
    if (!isImg && !isVid) { DM.toast("Нужно фото, GIF или видео", "error"); return; }
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

  $("unmatch").addEventListener("click", async () => {
    if (!confirm("Разорвать пару? Переписка удалится у вас обоих.")) return;
    try { await DM.api("/api/matches/" + mid + "/", { method: "DELETE" }); location.href = "/matches/"; }
    catch (e) { DM.toast(e.message, "error"); }
  });

  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(false); });
  poll(true);
  setInterval(() => poll(false), 3000);
})();
