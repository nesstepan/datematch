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
    [["Пользователи", s.users], ["Активные", s.active_users], ["Жалобы", s.reports_open || 0], ["Пары", s.matches], ["Свайпы", s.swipes], ["Интересы", s.interests]]
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

  /* Окно «Новый пароль»: администратор вводит пароль или создаёт случайный, а затем сообщает его пользователю. */
  function randomPassword() {
    const letters = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ", digits = "23456789", all = letters + digits;
    const pick = set => set[crypto.getRandomValues(new Uint32Array(1))[0] % set.length];
    const out = [pick(letters), pick(digits)];
    while (out.length < 12) out.push(pick(all));
    return out.sort(() => crypto.getRandomValues(new Uint8Array(1))[0] - 128).join("");
  }
  function passwordDialog(u) {
    const wrap = DM.el("div", "modal"); wrap.setAttribute("role", "dialog"); wrap.setAttribute("aria-modal", "true");
    const box = DM.el("form", "panel dialog"); box.noValidate = true;
    box.appendChild(DM.el("h2", "", "Новый пароль"));
    box.appendChild(DM.el("p", "muted", u.name + " (" + u.email + "). После смены пользователь сможет войти только с новым паролем, старые входы закроются."));
    const field = DM.el("div", "field"), lab = DM.el("label", "", "Пароль (от 8 символов, буквы и цифры)"); lab.htmlFor = "adm-pw";
    const input = DM.el("input"); input.id = "adm-pw"; input.type = "text"; input.autocomplete = "off"; input.maxLength = 128;
    const err = DM.el("p", "err"); err.setAttribute("role", "alert");
    field.append(lab, input, err);
    const gen = DM.el("button", "btn ghost sm", "Сгенерировать"); gen.type = "button";
    gen.addEventListener("click", () => { input.value = randomPassword(); input.focus(); input.select(); });
    const row = DM.el("div", "row"), save = DM.el("button", "btn", "Сохранить"), cancel = DM.el("button", "btn ghost", "Отмена");
    save.type = "submit"; cancel.type = "button"; row.append(save, cancel);
    box.append(field, DM.el("p", "", ""), gen, DM.el("p", "", ""), row);
    wrap.appendChild(box); document.body.appendChild(wrap); input.focus();
    const close = () => wrap.remove();
    cancel.addEventListener("click", close);
    wrap.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
    box.addEventListener("submit", async ev => {
      ev.preventDefault(); err.textContent = "";
      if (input.value.length < 8) { err.textContent = "Пароль должен быть не короче 8 символов"; return; }
      save.disabled = true;
      try {
        await DM.api("/api/admin/users/" + u.uid + "/password/", { method: "POST", json: { password: input.value } });
        close(); DM.toast("Пароль для «" + u.name + "» изменён. Сообщите его пользователю.");
      } catch (e) { err.textContent = (e.fields && e.fields.password) || e.message; save.disabled = false; }
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
      if (u.uid !== document.body.dataset.me) {  // свой пароль меняют в личном кабинете
        const pw = DM.el("button", "btn ghost", "Пароль"); pw.type = "button"; pw.title = "Задать новый пароль пользователю";
        pw.addEventListener("click", () => passwordDialog(u));
        btns.appendChild(pw);
      }
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

  /* жалобы пользователей */
  const repBox = document.getElementById("reports"), repEmpty = document.getElementById("reports-empty"), repCount = document.getElementById("reports-count");
  const CONTEXT = { profile: "анкета", chat: "чат", post: "пост" };
  async function loadReports() {
    const { reports } = await DM.api("/api/admin/reports/");
    repBox.textContent = ""; repEmpty.hidden = reports.length > 0; repCount.hidden = !reports.length; repCount.textContent = reports.length;
    reports.forEach(r => {
      const d = DM.el("div", "report"), head = DM.el("div", "head");
      head.appendChild(DM.el("strong", "", r.target.name));
      head.appendChild(DM.el("span", "badge off", r.reason_title));
      head.appendChild(DM.el("span", "muted small", "от " + r.from_name + " · " + (CONTEXT[r.context] || r.context) + " · " + DM.dateText(r.created_at)));
      d.appendChild(head);
      d.appendChild(DM.el("div", "muted small", r.target.email + (r.target.is_active ? "" : " · уже заблокирован")));
      if (r.details) d.appendChild(DM.el("p", "", r.details));
      const acts = DM.el("div", "acts");
      const view = DM.el("a", "btn ghost sm", "Открыть анкету"); view.href = "/u/" + r.target.uid + "/"; view.target = "_blank"; view.rel = "noopener";
      const dismiss = DM.el("button", "btn ghost sm", "Отклонить"); dismiss.type = "button";
      acts.append(view, dismiss);
      if (!r.target.is_admin) {
        const block = DM.el("button", "btn danger sm", "Заблокировать"); block.type = "button"; acts.appendChild(block);
        block.addEventListener("click", () => resolve(r, "block", "Пользователь заблокирован"));
      }
      dismiss.addEventListener("click", () => resolve(r, "dismiss", "Жалоба отклонена"));
      d.appendChild(acts); repBox.appendChild(d);
    });
  }
  function resolve(r, action, msg) {
    if (action === "block" && !confirm("Заблокировать «" + r.target.name + "»? Войти на сайт он больше не сможет.")) return;
    run(async () => { await DM.api("/api/admin/reports/" + r.id + "/", { method: "PATCH", json: { action } }); await Promise.all([loadReports(), loadStats(), loadUsers()]); }, msg);
  }
  loadReports().catch(e => DM.toast(e.message, "error"));
})();
