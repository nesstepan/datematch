/* Личный кабинет: приватность, чёрный список, удаление аккаунта. */
(function () {
  const $ = id => document.getElementById(id);
  const hidden = $("hidden"), hideOnline = $("hide-online");

  DM.api("/api/me/").then(({ user }) => { hidden.checked = !!user.hidden; hideOnline.checked = !!user.hide_online; })
    .catch(e => DM.toast(e.message, "error"));

  function bind(box, key, onText, offText) {
    box.addEventListener("change", async () => {
      try { await DM.api("/api/me/settings/", { method: "POST", json: { [key]: box.checked } }); DM.toast(box.checked ? onText : offText); }
      catch (e) { box.checked = !box.checked; DM.toast(e.message, "error"); }
    });
  }
  bind(hidden, "hidden", "Вас не видно в поиске и ленте", "Вы снова в поиске");
  bind(hideOnline, "hide_online", "Статус «в сети» скрыт", "Статус «в сети» снова виден");

  /* ---------- смена пароля ---------- */
  const pwForm = $("pw-form");
  $("pw-show").addEventListener("change", e => {
    ["pw-current", "pw-new", "pw-repeat"].forEach(id => { $(id).type = e.target.checked ? "text" : "password"; });
  });
  pwForm.addEventListener("submit", async ev => {
    ev.preventDefault();
    const current = $("pw-current").value, next = $("pw-new").value, again = $("pw-repeat").value;
    const errors = {};
    if (!current) errors.current_password = "Введите текущий пароль";
    if (next.length < 8) errors.new_password = "Пароль должен быть не короче 8 символов";
    else if (!/[A-Za-zА-Яа-яЁё]/.test(next) || !/\d/.test(next)) errors.new_password = "Пароль должен содержать и буквы, и цифры";
    if (!errors.new_password && next === current) errors.new_password = "Придумайте пароль, которого раньше не было";
    if (next !== again) errors.repeat = "Пароли не совпадают";
    DM.showErrors(pwForm, errors, "");
    if (Object.keys(errors).length) return;
    const btn = $("pw-submit"); btn.disabled = true;
    try {
      await DM.api("/api/me/password/", { method: "POST", json: { current_password: current, new_password: next } });
      pwForm.reset(); ["pw-current", "pw-new", "pw-repeat"].forEach(id => { $(id).type = "password"; });
      DM.showErrors(pwForm, {}, ""); DM.toast("Пароль изменён");
    } catch (e) { DM.showErrors(pwForm, e.fields, Object.keys(e.fields || {}).length ? "" : e.message); }
    finally { btn.disabled = false; }
  });

  const bl = $("blocked-list"), blEmpty = $("blocked-empty");
  function drawBlocked(items) {
    bl.textContent = ""; blEmpty.hidden = items.length > 0;
    items.forEach(b => {
      const row = DM.el("div", "blocked-item");
      const img = DM.el("img", "avatar"); img.src = b.photo_url; img.alt = ""; img.style.width = img.style.height = "40px";
      const un = DM.el("button", "btn ghost sm", "Разблокировать"); un.type = "button";
      un.addEventListener("click", async () => {
        un.disabled = true;
        try { drawBlocked((await DM.api("/api/blocks/" + b.uid + "/", { method: "DELETE" })).blocked); DM.toast("«" + b.name + "» убран из чёрного списка"); }
        catch (e) { DM.toast(e.message, "error"); un.disabled = false; }
      });
      row.append(img, DM.el("strong", "", b.name), un); bl.appendChild(row);
    });
  }
  DM.api("/api/blocks/").then(r => drawBlocked(r.blocked)).catch(e => DM.toast(e.message, "error"));

  const del = $("delete-form");
  del.addEventListener("submit", async ev => {
    ev.preventDefault();
    const password = $("del-password").value;
    if (!password) { DM.showErrors(del, { password: "Введите пароль" }, ""); return; }
    if (!confirm("Удалить аккаунт навсегда? Это нельзя отменить.")) return;
    try { await DM.api("/api/me/", { method: "DELETE", json: { password } }); location.href = "/"; }
    catch (e) { DM.showErrors(del, e.fields, e.message); }
  });
})();
