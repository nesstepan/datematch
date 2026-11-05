/* Мини-карты людей для страниц «Симпатии» и «Поиск». */
window.DMPeople = (function () {
  function card(p, actions) {
    const box = DM.el("div", "person");
    const a = DM.el("a", "tarot"); a.href = "/u/" + p.uid + "/";
    if (p.accent) a.style.setProperty("--accent", p.accent);
    a.setAttribute("aria-label", "Открыть страницу: " + p.name);
    const frame = DM.el("div", "tarot-frame");
    const img = DM.el("img"); img.src = p.photo_url; img.alt = ""; img.loading = "lazy";
    frame.append(img, DM.el("span", "tarot-num", DM.roman(p.age)));
    if (p.online) { const pr = DM.el("span", "presence-tag"); pr.append(DM.el("span", "online-dot"), document.createTextNode("в сети")); frame.appendChild(pr); }
    const title = DM.el("div", "tarot-title"); title.append(DM.art("star"), DM.el("h2", "", p.name), DM.art("star"));
    frame.appendChild(title); a.appendChild(frame); box.appendChild(a);
    const meta = [DM.ageText(p.age), p.goal_title].filter(Boolean).join(" · ");
    box.appendChild(DM.el("div", "person-meta", meta));
    if (actions) box.appendChild(actions);
    return box;
  }
  function postEl(p, opts) {
    opts = opts || {};
    const d = DM.el("article", "post");
    if (opts.author) {
      const head = DM.el("a", "post-author"); head.href = "/u/" + opts.author.uid + "/";
      const img = DM.el("img", "avatar"); img.src = opts.author.photo_url; img.alt = ""; img.loading = "lazy";
      const who = DM.el("span"); who.append(DM.el("strong", "", opts.author.mine ? "Вы" : opts.author.name), DM.el("time", "", DM.dateText(p.created_at)));
      head.append(img, who); d.appendChild(head);
    }
    if (p.text) d.appendChild(DM.el("p", "", p.text));
    if (p.image_url) { const i = DM.el("img", "post-img"); i.src = p.image_url; i.alt = "Фото к посту"; i.loading = "lazy"; d.appendChild(i); }
    if (!opts.author) d.appendChild(DM.el("time", "", DM.dateText(p.created_at)));
    if (opts.canDelete) {
      const del = DM.el("button", "link-btn danger del"); del.type = "button"; del.setAttribute("aria-label", "Удалить пост"); del.appendChild(DM.icon("trash"));
      del.addEventListener("click", async () => {
        if (!confirm("Удалить этот пост?")) return;
        try { await DM.api("/api/me/posts/" + p.id + "/", { method: "DELETE" }); d.remove(); if (opts.onDelete) opts.onDelete(); }
        catch (e) { DM.toast(e.message, "error"); }
      });
      d.appendChild(del);
    }
    return d;
  }

  /* Форма публикации поста. onPosted(post) вызывается после успешной публикации. */
  function composer(onPosted) {
    const form = DM.el("form", "panel composer-post form"); form.noValidate = true;
    const ta = DM.el("textarea"); ta.maxLength = 1000; ta.placeholder = "О чём хотите рассказать?"; ta.setAttribute("aria-label", "Текст поста");
    const file = DM.el("input"); file.type = "file"; file.accept = "image/jpeg,image/png,image/webp,image/gif"; file.hidden = true;
    const pick = DM.el("button", "btn ghost sm"); pick.type = "button"; pick.appendChild(DM.icon("image")); const pickText = document.createTextNode("Добавить фото"); pick.appendChild(pickText);
    pick.addEventListener("click", () => file.click());
    file.addEventListener("change", () => { pickText.nodeValue = file.files[0] ? "Фото: " + file.files[0].name.slice(0, 18) : "Добавить фото"; });
    const send = DM.el("button", "btn sm"); send.type = "submit"; send.appendChild(DM.icon("pen")); send.appendChild(document.createTextNode("Опубликовать"));
    const row = DM.el("div", "row"); row.append(pick, send);
    const err = DM.el("p", "err"); err.setAttribute("role", "alert");
    form.append(ta, file, row, err);
    form.addEventListener("submit", async ev => {
      ev.preventDefault(); err.textContent = "";
      const text = ta.value.trim(), f = file.files[0];
      if (!text && !f) { err.textContent = "Напишите что-нибудь или прикрепите фото"; return; }
      if (f && f.size > 5 * 1024 * 1024) { err.textContent = "Файл больше 5 МБ"; return; }
      const fd = new FormData(); fd.append("text", text); if (f) fd.append("photo", f);
      send.disabled = true;
      try {
        const { post } = await DM.api("/api/me/posts/", { method: "POST", form: fd });
        ta.value = ""; file.value = ""; pickText.nodeValue = "Добавить фото"; onPosted(post);
      } catch (e) { err.textContent = (e.fields && (e.fields.text || e.fields.photo)) || e.message; }
      finally { send.disabled = false; }
    });
    return form;
  }
  return { card, postEl, composer };
})();
