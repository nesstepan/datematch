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
