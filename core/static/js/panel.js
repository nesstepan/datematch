(function () {
  const statsBox = document.getElementById("stats"), rows = document.getElementById("user-rows");
  const list = document.getElementById("interest-list"), filter = document.getElementById("user-filter");
  const iform = document.getElementById("interest-form"), iname = document.getElementById("interest-name");
  const ierr = document.getElementById("interest-error");
  let users = [];

  const run = async (fn, okMsg) => {
    try { await fn(); if (okMsg) DM.toast(okMsg); } catch (e) { DM.toast(e.message, "error"); }
  };

  async function loadStats() {
    const s = await DM.api("/api/admin/stats/");
    statsBox.textContent = "";
    [["Пользователи", s.users], ["Активные", s.active_users], ["Пары", s.matches], ["Свайпы", s.swipes], ["Интересы", s.interests]]
      .forEach(([label, n]) => {
        const d = DM.el("div", "stat"); d.appendChild(DM.el("b", "", String(n))); d.appendChild(DM.el("span", "muted", label));
        statsBox.appendChild(d);
      });
  }

  async function loadInterests() {
    const { interests } = await DM.api("/api/interests/");
    list.textContent = "";
    interests.forEach(i => {
      const chip = DM.el("button", "chip", i.name); chip.type = "button";
      chip.title = "Удалить интерес «" + i.name + "»";
      const xs = DM.el("span", "x"); xs.appendChild(DM.icon("x")); chip.appendChild(xs);
      chip.addEventListener("click", () => {
        if (!confirm("Удалить интерес «" + i.name + "»? У пользователей он останется в анкете.")) return;
        run(async () => { await DM.api("/api/admin/interests/" + i.id + "/", { method: "DELETE" }); await Promise.all([loadInterests(), loadStats()]); }, "Интерес удалён");
      });
      list.appendChild(chip);
    });
  }

  function drawUsers() {
    const q = filter.value.trim().toLowerCase();
    rows.textContent = "";
    users.filter(u => !q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)).forEach(u => {
      const tr = document.createElement("tr");
      tr.appendChild(DM.el("td", "", u.name + (u.is_admin ? " (админ)" : "")));
      tr.appendChild(DM.el("td", "", u.email));
      tr.appendChild(DM.el("td", "", String(u.age)));
      const st = DM.el("td"); st.appendChild(DM.el("span", "badge" + (u.is_active ? "" : " off"), u.is_active ? "активен" : "заблокирован"));
      tr.appendChild(st);
      const act = DM.el("td"), btns = DM.el("div", "btns");
      if (!u.is_admin) {
        const block = DM.el("button", "btn ghost", u.is_active ? "Заблокировать" : "Разблокировать"); block.type = "button";
        block.addEventListener("click", () => run(async () => {
          await DM.api("/api/admin/users/" + u.uid + "/", { method: "PATCH", json: { is_active: !u.is_active } });
          await Promise.all([loadUsers(), loadStats()]);
        }, u.is_active ? "Пользователь заблокирован" : "Пользователь разблокирован"));
        const del = DM.el("button", "btn danger", "Удалить"); del.type = "button";
        del.addEventListener("click", () => {
          if (!confirm("Удалить " + u.name + " вместе с фото, парами и перепиской?")) return;
          run(async () => { await DM.api("/api/admin/users/" + u.uid + "/", { method: "DELETE" }); await Promise.all([loadUsers(), loadStats()]); }, "Пользователь удалён");
        });
        btns.append(block, del);
      }
      act.appendChild(btns); tr.appendChild(act); rows.appendChild(tr);
    });
    if (!rows.children.length) { const tr = document.createElement("tr"), td = DM.el("td", "muted", "Никого не нашли"); td.colSpan = 5; tr.appendChild(td); rows.appendChild(tr); }
  }

  async function loadUsers() { users = (await DM.api("/api/admin/users/")).users; drawUsers(); }

  iform.addEventListener("submit", async ev => {
    ev.preventDefault(); ierr.textContent = "";
    const name = iname.value.trim();
    if (name.length < 2) { ierr.textContent = "Название интереса — от 2 до 30 символов"; return; }
    try {
      await DM.api("/api/admin/interests/", { method: "POST", json: { name } });
      iname.value = ""; await Promise.all([loadInterests(), loadStats()]); DM.toast("Интерес добавлен");
    } catch (e) { ierr.textContent = (e.fields && e.fields.name) || e.message; }
  });
  filter.addEventListener("input", drawUsers);

  Promise.all([loadStats(), loadInterests(), loadUsers()]).catch(e => DM.toast(e.message, "error"));
})();
