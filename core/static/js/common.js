/* Общие утилиты: запросы к API, уведомления, выход из аккаунта. */
(function () {
  const csrf = () => document.querySelector('meta[name="csrf-token"]').content;

  class ApiError extends Error {
    constructor(message, status, fields) { super(message); this.status = status; this.fields = fields || {}; }
  }

  async function api(url, opts = {}) {
    const init = { method: opts.method || "GET", headers: { "X-CSRFToken": csrf() }, credentials: "same-origin" };
    if (opts.json !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.json); }
    if (opts.form) init.body = opts.form;
    let res;
    try { res = await fetch(url, init); }
    catch (e) { throw new ApiError("Нет связи с сервером. Проверьте интернет и повторите.", 0); }
    let data = {};
    try { data = await res.json(); } catch (e) { /* не JSON */ }
    if (!res.ok) {
      if (res.status === 401 && !location.pathname.startsWith("/login")) { location.href = "/login/"; }
      const err = data.error || {};
      throw new ApiError(err.message || "Неожиданная ошибка (" + res.status + ")", res.status, err.fields);
    }
    return data;
  }

  /* Векторная иконка из спрайта (templates/icons.html): DM.icon("heart", "lg fill") */
  function icon(name, extra) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", ("ic " + (extra || "")).trim());
    svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
    const use = document.createElementNS(NS, "use"); use.setAttribute("href", "#" + name);
    svg.appendChild(use);
    return svg;
  }

  function toast(text, type) {
    const el = document.createElement("div");
    const bad = type === "error";
    el.className = "toast" + (bad ? " error" : "");
    el.appendChild(icon(bad ? "alert" : "circle-check"));
    el.appendChild(document.createTextNode(text));
    document.getElementById("toasts").appendChild(el);
    setTimeout(() => el.remove(), 4500);
  }

  /* Показ ошибок формы: подсвечиваем поля и пишем текст под ними. */
  function showErrors(form, fields, general) {
    form.querySelectorAll("[data-err]").forEach(p => {
      const msg = (fields || {})[p.dataset.err] || "";
      p.textContent = msg;
      const f = p.closest(".field"); if (f) f.classList.toggle("invalid", !!msg);
    });
    const g = form.querySelector(".form-err"); if (g) g.textContent = general || "";
    const first = form.querySelector(".field.invalid input, .field.invalid select, .field.invalid textarea");
    if (first) first.focus();
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  const first = location.pathname.split("/")[1];
  const here = document.body.dataset.nav || ({ chat: "matches", profile: "profile", settings: "profile" })[first] || first;
  document.querySelectorAll("[data-nav]").forEach(a => { if (a.dataset.nav === here) a.classList.add("active"); });
  const out = document.getElementById("logout-btn");
  if (out) out.addEventListener("click", async () => {
    try { await api("/api/auth/logout/", { method: "POST" }); } catch (e) { /* всё равно уходим */ }
    location.href = "/login/";
  });

  const themeBtn = document.getElementById("theme-btn");
  if (themeBtn) themeBtn.addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("dm-theme", next); } catch (e) { /* приватный режим */ }
  });

  window.DM = { api, ApiError, toast, showErrors, el, icon };
})();

/* ---- общие помощники для новых страниц ---- */
(function () {
  const { api, toast, el } = window.DM;
  const ART_VB = { cupid: "-14 0 254 250", sun: "-100 -100 200 200", cloud: "0 0 200 100", rose: "0 0 100 130", mark: "0 0 48 48", star: "0 0 24 24" };
  const NS = "http://www.w3.org/2000/svg";
  function art(name, extra) {  // нарисованная иллюстрация из спрайта art.html
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", ("art art-" + name + " " + (extra || "")).trim()); svg.setAttribute("viewBox", ART_VB[name]);
    svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
    const use = document.createElementNS(NS, "use"); use.setAttribute("href", "#art-" + name); svg.appendChild(use);
    return svg;
  }
  function roman(n) {  // 27 -> XXVII (римская цифра на карте Таро)
    const map = [[1000, "M"], [900, "CM"], [500, "D"], [400, "CD"], [100, "C"], [90, "XC"], [50, "L"], [40, "XL"], [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
    let out = ""; n = Math.max(1, Math.min(3999, n | 0));
    for (const [v, r] of map) while (n >= v) { out += r; n -= v; }
    return out;
  }
  function ageText(n) {
    const a = n % 10, b = n % 100;
    return n + (a === 1 && b !== 11 ? " год" : a >= 2 && a <= 4 && (b < 12 || b > 14) ? " года" : " лет");
  }
  function lastSeen(online, ts) {
    if (online) return "в сети";
    if (!ts) return "";
    const s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 3600) return "был(а) " + Math.max(1, Math.round(s / 60)) + " мин назад";
    if (s < 86400) return "был(а) " + Math.round(s / 3600) + " ч назад";
    if (s < 86400 * 30) return "был(а) " + Math.round(s / 86400) + " дн. назад";
    return "был(а) давно";
  }
  function dateText(ts) {
    return new Date(ts * 1000).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
  }
  const REASONS = [["spam", "Спам или реклама"], ["fake", "Фейковая анкета"], ["abuse", "Оскорбления или угрозы"],
    ["inappropriate", "Неприемлемый контент"], ["underage", "Похоже, нет 18 лет"], ["other", "Другое"]];

  /* Окно жалобы. Возвращает Promise<{sent, blocked}>. */
  function reportDialog(uid, name, context) {
    return new Promise(resolve => {
      const back = el("div", "modal"), box = el("form", "dialog");
      box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true"); box.noValidate = true;
      box.appendChild(el("h2", "", "Пожаловаться на " + name));
      const list = el("div", "radio-list");
      REASONS.forEach(([id, title], i) => {
        const l = el("label"), r = el("input"); r.type = "radio"; r.name = "reason"; r.value = id; if (i === 0) r.checked = true;
        l.append(r, document.createTextNode(title)); list.appendChild(l);
      });
      const details = el("textarea"); details.rows = 3; details.maxLength = 500; details.placeholder = "Что произошло? (необязательно)";
      const blockLbl = el("label", "check"), blockBox = el("input"); blockBox.type = "checkbox"; blockBox.checked = true;
      blockLbl.append(blockBox, document.createTextNode("Добавить в чёрный список"));
      const err = el("p", "err");
      const cancel = el("button", "btn ghost", "Отмена"); cancel.type = "button";
      const send = el("button", "btn", "Отправить"); send.type = "submit";
      const row = el("div", "row"); row.append(cancel, send);
      box.append(list, details, blockLbl, err, row); back.appendChild(box); document.body.appendChild(back);
      const close = result => { back.remove(); document.removeEventListener("keydown", onKey); resolve(result); };
      const onKey = e => { if (e.key === "Escape") close({ sent: false }); };
      document.addEventListener("keydown", onKey);
      back.addEventListener("click", e => { if (e.target === back) close({ sent: false }); });
      cancel.addEventListener("click", () => close({ sent: false }));
      box.addEventListener("submit", async ev => {
        ev.preventDefault(); send.disabled = true; err.textContent = "";
        try {
          await api("/api/reports/", { method: "POST", json: { uid, reason: box.elements.reason.value, details: details.value, context, block: blockBox.checked } });
          toast(blockBox.checked ? "Жалоба отправлена, человек в чёрном списке" : "Жалоба отправлена администратору");
          close({ sent: true, blocked: blockBox.checked });
        } catch (e) { err.textContent = e.message; send.disabled = false; }
      });
      send.focus();
    });
  }

  async function blockUser(uid, name) {
    if (!confirm("Добавить «" + name + "» в чёрный список? Пара и переписка с этим человеком удалятся.")) return false;
    try { await api("/api/blocks/", { method: "POST", json: { uid } }); toast("«" + name + "» в чёрном списке"); return true; }
    catch (e) { toast(e.message, "error"); return false; }
  }
  Object.assign(window.DM, { art, roman, ageText, lastSeen, dateText, reportDialog, blockUser });
})();

/* ---- встроенный плеер для любимой песни ---- */
(function () {
  const { el, icon } = window.DM;

  /* Строим адрес плеера САМИ из разобранной ссылки и только для известных сервисов: чужой адрес в iframe не попадает. */
  function embedFor(raw) {
    let u;
    try { u = new URL(raw); } catch (e) { return null; }
    if (!/^https?:$/.test(u.protocol)) return null;
    const host = u.hostname.replace(/^(www|m)\./, "");
    let m;
    if (/^music\.yandex\.(ru|com|by|kz|uz)$/.test(host) && (m = u.pathname.match(/^\/album\/(\d+)\/track\/(\d+)/)))
      return { kind: "iframe", src: "https://music.yandex.ru/iframe/#track/" + m[2] + "/" + m[1], height: 120, title: "Яндекс Музыка" };
    if (host === "youtu.be" && (m = u.pathname.match(/^\/([\w-]{11})/)))
      return { kind: "iframe", src: "https://www.youtube-nocookie.com/embed/" + m[1], height: 240, title: "YouTube" };
    if ((host === "youtube.com" || host === "music.youtube.com") && /^[\w-]{11}$/.test(u.searchParams.get("v") || ""))
      return { kind: "iframe", src: "https://www.youtube-nocookie.com/embed/" + u.searchParams.get("v"), height: 240, title: "YouTube" };
    if (host === "open.spotify.com" && (m = u.pathname.match(/^\/(?:intl-[a-z]+\/)?(track|album|playlist|episode)\/([A-Za-z0-9]{22})/)))
      return { kind: "iframe", src: "https://open.spotify.com/embed/" + m[1] + "/" + m[2], height: m[1] === "track" || m[1] === "episode" ? 152 : 352, title: "Spotify" };
    if (host === "soundcloud.com" && u.pathname.length > 1)
      return { kind: "iframe", src: "https://w.soundcloud.com/player/?auto_play=false&url=" + encodeURIComponent(u.href), height: 166, title: "SoundCloud" };
    if (/\.(mp3|ogg|oga|wav|m4a|aac)$/i.test(u.pathname)) return { kind: "audio", src: u.href, title: "Аудиофайл" };
    return null;
  }

  function openPlayer(title, url) {
    const embed = url ? embedFor(url) : null;
    const back = el("div", "modal"), box = el("div", "dialog player");
    box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true"); box.setAttribute("aria-label", "Плеер: " + title);
    const h = el("h2"); h.appendChild(icon("music")); h.appendChild(document.createTextNode(" " + title)); box.appendChild(h);
    if (embed && embed.kind === "iframe") {
      const f = el("iframe"); f.src = embed.src; f.height = embed.height; f.title = title + " (" + embed.title + ")"; f.loading = "lazy";
      f.setAttribute("allow", "autoplay; encrypted-media; clipboard-write"); f.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      f.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups allow-presentation"); f.className = "player-frame"; box.appendChild(f);
      box.appendChild(el("p", "hint", "Если плеер пустой или играет только отрывок, откройте трек на сайте сервиса."));
    } else if (embed && embed.kind === "audio") {
      const a = el("audio"); a.src = embed.src; a.controls = true; a.autoplay = true; a.preload = "none"; a.className = "player-audio"; box.appendChild(a);
    } else {
      box.appendChild(el("p", "muted", url ? "Для этой ссылки встроенный плеер недоступен." : "Ссылка на трек не указана."));
    }
    const row = el("div", "row");
    if (url && /^https?:\/\//i.test(url)) {
      const open = el("a", "btn ghost sm", "Открыть на сайте"); open.href = url; open.target = "_blank"; open.rel = "noopener noreferrer nofollow"; row.appendChild(open);
    }
    const close = el("button", "btn sm", "Закрыть"); close.type = "button"; row.appendChild(close);
    box.appendChild(row); back.appendChild(box); document.body.appendChild(back);
    const stop = () => { back.remove(); document.removeEventListener("keydown", onKey); };
    const onKey = e => { if (e.key === "Escape") stop(); };
    document.addEventListener("keydown", onKey);
    back.addEventListener("click", e => { if (e.target === back) stop(); });
    close.addEventListener("click", stop); close.focus();
  }
  Object.assign(window.DM, { embedFor, openPlayer });
})();
