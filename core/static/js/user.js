/* Страница пользователя: анкета, посты, действия (лайк, написать, пожаловаться, в чёрный список). */
(function () {
  const root = document.getElementById("user-root"), body = document.getElementById("user-body"), missing = document.getElementById("user-missing");
  const uid = root.dataset.uid, isMe = root.dataset.me === "1";
  const vmodal = document.getElementById("video-modal"), vbody = document.getElementById("video-body");
  document.getElementById("video-close").addEventListener("click", () => { vmodal.hidden = true; vbody.textContent = ""; });
  const safeUrl = u => (/^https?:\/\//i.test(u) ? u : "");

  function fact(icon, text) { const s = DM.el("span"); s.appendChild(DM.icon(icon)); s.appendChild(document.createTextNode(text)); return s; }

  function postEl(p, canDelete) {
    const d = DM.el("article", "post");
    if (p.text) d.appendChild(DM.el("p", "", p.text));
    if (p.image_url) { const i = DM.el("img"); i.src = p.image_url; i.alt = "Фото к посту"; i.loading = "lazy"; d.appendChild(i); }
    d.appendChild(DM.el("time", "", DM.dateText(p.created_at)));
    if (canDelete) {
      const del = DM.el("button", "link-btn danger del"); del.type = "button"; del.setAttribute("aria-label", "Удалить пост"); del.appendChild(DM.icon("trash"));
      del.addEventListener("click", async () => {
        if (!confirm("Удалить этот пост?")) return;
        try { await DM.api("/api/me/posts/" + p.id + "/", { method: "DELETE" }); d.remove(); }
        catch (e) { DM.toast(e.message, "error"); }
      });
      d.appendChild(del);
    }
    return d;
  }

  function render(data) {
    const p = data.profile, rel = data.relation;
    body.textContent = "";
    const hero = DM.el("div", "profile-hero");

    const tarot = DM.el("div", "tarot"); if (p.accent) tarot.style.setProperty("--accent", p.accent);
    const frame = DM.el("div", "tarot-frame");
    const img = DM.el("img"); img.src = p.photo_url; img.alt = "Фото: " + p.name;
    frame.append(img, DM.el("span", "tarot-num", DM.roman(p.age)));
    const title = DM.el("div", "tarot-title"); title.append(DM.art("star"), DM.el("h2", "", p.name), DM.art("star"));
    frame.appendChild(title); tarot.appendChild(frame); hero.appendChild(tarot);

    const side = DM.el("div");
    const h1 = DM.el("h1"); h1.appendChild(document.createTextNode(p.name + ", ")); const em = DM.el("em", "", DM.ageText(p.age)); h1.appendChild(em);
    side.appendChild(h1);
    if (p.status) side.appendChild(DM.el("p", "status-line", p.status));
    const facts = DM.el("div", "facts");
    const seen = DM.lastSeen(p.online, p.last_seen);
    if (seen) { const s = DM.el("span"); s.appendChild(DM.el("span", "online-dot" + (p.online ? "" : " off"))); s.appendChild(document.createTextNode(seen)); facts.appendChild(s); }
    if (p.goal_title) facts.appendChild(fact("target", p.goal_title));
    if (p.music_title) {
      const href = safeUrl(p.music_url);
      if (href) { const a = DM.el("a"); a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer nofollow"; a.appendChild(DM.icon("music")); a.appendChild(document.createTextNode(" " + p.music_title)); facts.appendChild(a); }
      else facts.appendChild(fact("music", p.music_title));
    }
    side.appendChild(facts);
    if (p.bio) side.appendChild(DM.el("p", "", p.bio));
    if (p.interests.length) { const c = DM.el("div", "chips"); p.interests.forEach(t => c.appendChild(DM.el("span", "chip", t))); side.appendChild(c); }
    if (p.badges && p.badges.length) {
      const b = DM.el("div", "facts"); p.badges.forEach(x => b.appendChild(fact(x.icon, x.title))); side.appendChild(b);
    }

    const actions = DM.el("div", "profile-actions");
    if (isMe) {
      const edit = DM.el("a", "btn ghost sm"); edit.href = "/profile/"; edit.appendChild(DM.icon("pen")); edit.appendChild(document.createTextNode("Редактировать анкету"));
      actions.appendChild(edit);
    } else {
      if (p.video_url) {
        const v = DM.el("button", "btn ghost sm"); v.type = "button"; v.appendChild(DM.icon("play", "fill")); v.appendChild(document.createTextNode("Смотреть видео"));
        v.addEventListener("click", () => { vbody.textContent = ""; const el = DM.el("video"); el.src = p.video_url; el.controls = true; el.autoplay = true; el.playsInline = true; vbody.appendChild(el); vmodal.hidden = false; });
        actions.appendChild(v);
      }
      if (rel.matched) {
        const w = DM.el("a", "btn sm"); w.href = "/chat/" + rel.match_id + "/"; w.appendChild(DM.icon("chat")); w.appendChild(document.createTextNode("Написать")); actions.appendChild(w);
      } else if (!rel.i_liked) {
        const like = DM.el("button", "btn sm"); like.type = "button"; like.appendChild(DM.icon("heart", "fill")); like.appendChild(document.createTextNode(rel.liked_me ? "Ответить лайком" : "Нравится"));
        like.addEventListener("click", async () => {
          like.disabled = true;
          try {
            const res = await DM.api("/api/swipes/", { method: "POST", json: { target_uid: uid, like: true } });
            if (res.matched) { DM.toast("Это пара!"); load(); } else { DM.toast("Лайк отправлен"); like.remove(); }
          } catch (e) { DM.toast(e.message, "error"); like.disabled = false; }
        });
        actions.appendChild(like);
      } else actions.appendChild(DM.el("span", "muted small", "Вы уже поставили лайк"));
      const rep = DM.el("button", "link-btn"); rep.type = "button"; rep.appendChild(DM.icon("flag")); rep.appendChild(document.createTextNode("Пожаловаться"));
      rep.addEventListener("click", async () => { const r = await DM.reportDialog(uid, p.name, "profile"); if (r.blocked) location.href = "/search/"; });
      const blk = DM.el("button", "link-btn danger"); blk.type = "button"; blk.appendChild(DM.icon("ban")); blk.appendChild(document.createTextNode("В чёрный список"));
      blk.addEventListener("click", async () => { if (await DM.blockUser(uid, p.name)) location.href = "/search/"; });
      actions.append(rep, blk);
    }
    side.appendChild(actions);
    hero.appendChild(side); body.appendChild(hero);

    const wall = DM.el("section"); wall.appendChild(DM.el("h2", "", isMe ? "Мои посты" : "Посты"));
    const posts = DM.el("div", "posts");
    if (isMe) wall.appendChild(composer(posts));
    wall.appendChild(posts);
    data.posts.forEach(x => posts.appendChild(postEl(x, isMe)));
    if (!data.posts.length) posts.appendChild(DM.el("p", "muted", isMe ? "Пока пусто. Напишите первый пост, чтобы вас можно было узнать лучше." : "Пока нет постов."));
    body.appendChild(wall);
  }

  function composer(posts) {
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
        const empty = posts.querySelector(".muted"); if (empty) empty.remove();
        posts.prepend(postEl(post, true)); ta.value = ""; file.value = ""; pickText.nodeValue = "Добавить фото";
      } catch (e) { err.textContent = (e.fields && (e.fields.text || e.fields.photo)) || e.message; }
      finally { send.disabled = false; }
    });
    return form;
  }

  async function load() {
    try { render(await DM.api("/api/users/" + uid + "/")); }
    catch (e) { body.hidden = true; if (e.status === 404) missing.hidden = false; else DM.toast(e.message, "error"); }
  }
  load();
})();
