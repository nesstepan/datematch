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
    const d = DM.el("article", "post"); d.id = "post-" + p.id;
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
    const authorUid = p.uid || (opts.author && opts.author.uid);
    if (authorUid) d.appendChild(reactions(p, authorUid));
    return d;
  }

  /* Лайк и комментарии под постом. Комментарии подгружаются, когда их впервые открывают. */
  function reactions(p, authorUid) {
    const base = "/api/users/" + authorUid + "/posts/" + p.id;
    const wrap = DM.el("div", "post-reactions");
    const bar = DM.el("div", "post-actions");
    const like = DM.el("button", "react like"); like.type = "button";
    const talk = DM.el("button", "react talk"); talk.type = "button"; talk.setAttribute("aria-expanded", "false");
    const paintLike = () => {
      like.textContent = ""; like.appendChild(DM.icon("heart", p.liked ? "fill" : "")); like.appendChild(DM.el("span", "", String(p.likes || 0)));
      like.classList.toggle("on", !!p.liked); like.setAttribute("aria-pressed", String(!!p.liked));
      like.setAttribute("aria-label", (p.liked ? "Убрать лайк. " : "Поставить лайк. ") + "Сейчас: " + (p.likes || 0));
    };
    const paintTalk = () => {
      talk.textContent = ""; talk.appendChild(DM.icon("chat")); talk.appendChild(DM.el("span", "", String(p.comments || 0)));
      talk.setAttribute("aria-label", "Комментарии: " + (p.comments || 0));
    };
    paintLike(); paintTalk();
    like.addEventListener("click", async () => {
      like.disabled = true;
      try { const r = await DM.api(base + "/like/", { method: p.liked ? "DELETE" : "POST" }); p.liked = r.liked; p.likes = r.likes; paintLike(); }
      catch (e) { DM.toast(e.message, "error"); }
      finally { like.disabled = false; }
    });

    const box = DM.el("div", "comments"); box.hidden = true;
    const list = DM.el("div", "comment-list");
    const form = DM.el("form", "comment-form"); form.noValidate = true;
    const input = DM.el("input"); input.maxLength = 500; input.placeholder = "Написать комментарий…"; input.setAttribute("aria-label", "Ваш комментарий"); input.autocomplete = "off";
    const send = DM.el("button", "btn sm"); send.type = "submit"; send.setAttribute("aria-label", "Отправить комментарий"); send.appendChild(DM.icon("send"));
    form.append(input, send);
    const err = DM.el("p", "err"); err.setAttribute("role", "alert");
    box.append(list, form, err);

    function commentEl(c) {
      const row = DM.el("div", "comment");
      const who = c.author.uid ? DM.el("a", "comment-who") : DM.el("span", "comment-who"); if (c.author.uid) who.href = "/u/" + c.author.uid + "/";
      if (c.author.photo_url) { const im = DM.el("img", "avatar"); im.src = c.author.photo_url; im.alt = ""; im.loading = "lazy"; who.appendChild(im); }
      else who.appendChild(DM.el("span", "avatar avatar-empty"));
      const body = DM.el("div", "comment-body");
      const head = DM.el("div", "comment-head"); head.append(DM.el("strong", "", c.mine ? "Вы" : c.author.name), DM.el("time", "", DM.dateText(c.created_at)));
      body.append(head, DM.el("p", "", c.text));
      row.append(who, body);
      if (c.can_delete) {
        const del = DM.el("button", "link-btn danger del-comment"); del.type = "button"; del.setAttribute("aria-label", "Удалить комментарий"); del.appendChild(DM.icon("trash"));
        del.addEventListener("click", async () => {
          if (!confirm("Удалить комментарий?")) return;
          try { const r = await DM.api(base + "/comments/" + c.id + "/", { method: "DELETE" }); row.remove(); p.comments = r.comments; paintTalk(); empty(); }
          catch (e) { DM.toast(e.message, "error"); }
        });
        row.appendChild(del);
      }
      return row;
    }
    const empty = () => { const e = list.querySelector(".comment-empty"); if (!list.querySelector(".comment")) { if (!e) list.appendChild(DM.el("p", "muted small comment-empty", "Комментариев пока нет. Напишите первым.")); } else if (e) e.remove(); };

    let loaded = false;
    talk.addEventListener("click", async () => {
      box.hidden = !box.hidden; talk.setAttribute("aria-expanded", String(!box.hidden));
      if (box.hidden) return;
      input.focus();
      if (loaded) return;
      try {
        const { comments } = await DM.api(base + "/comments/");
        list.textContent = ""; comments.forEach(c => list.appendChild(commentEl(c))); loaded = true; empty();
      } catch (e) { DM.toast(e.message, "error"); }
    });
    form.addEventListener("submit", async ev => {
      ev.preventDefault(); err.textContent = "";
      const text = input.value.trim();
      if (!text) { err.textContent = "Напишите комментарий"; return; }
      send.disabled = true;
      try {
        const r = await DM.api(base + "/comments/", { method: "POST", json: { text } });
        input.value = ""; p.comments = r.comments; paintTalk();
        const e0 = list.querySelector(".comment-empty"); if (e0) e0.remove();
        list.appendChild(commentEl(r.comment)); loaded = true;
      } catch (e) { err.textContent = (e.fields && e.fields.text) || e.message; }
      finally { send.disabled = false; }
    });
    bar.append(like, talk); wrap.append(bar, box);
    return wrap;
  }

  /* Форма публикации поста. onPosted(post) вызывается после успешной публикации. */
  function composer(onPosted) {
    const form = DM.el("form", "panel composer-post form"); form.noValidate = true;
    const ta = DM.el("textarea"); ta.maxLength = 1000; ta.placeholder = "О чём хотите рассказать?"; ta.setAttribute("aria-label", "Текст поста");
    const file = DM.el("input"); file.type = "file"; file.accept = "image/jpeg,image/png,image/webp,image/gif"; file.hidden = true;
    const pick = DM.el("button", "btn ghost sm"); pick.type = "button"; pick.appendChild(DM.icon("image")); const pickText = document.createTextNode("Добавить фото"); pick.appendChild(pickText);
    pick.addEventListener("click", () => file.click());
    DM.attachCrop(file, { aspects: ["4:5", "1:1", "16:9", "3:4"], title: "Фото для поста", allowOriginal: true, name: "post" });  // до других обработчиков
    file.addEventListener("change", () => { pickText.nodeValue = file.files[0] ? "Фото выбрано (нажмите, чтобы заменить)" : "Добавить фото"; });
    file.addEventListener("dm:cleared", () => { pickText.nodeValue = "Добавить фото"; });
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
