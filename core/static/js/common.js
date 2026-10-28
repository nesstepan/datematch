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

  const here = ({ chat: "matches" })[location.pathname.split("/")[1]] || location.pathname.split("/")[1];
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
