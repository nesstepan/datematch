/* Страница пользователя: анкета, посты, действия (лайк, написать, пожаловаться, в чёрный список). */
(function () {
  const root = document.getElementById("user-root"), body = document.getElementById("user-body"), missing = document.getElementById("user-missing");
  const uid = root.dataset.uid, isMe = root.dataset.me === "1";
  const vmodal = document.getElementById("video-modal"), vbody = document.getElementById("video-body");
  document.getElementById("video-close").addEventListener("click", () => { vmodal.hidden = true; vbody.textContent = ""; });
  const safeUrl = u => (/^https?:\/\//i.test(u) ? u : "");

  function fact(icon, text) { const s = DM.el("span"); s.appendChild(DM.icon(icon)); s.appendChild(document.createTextNode(text)); return s; }

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
      const b = DM.el("button", "link-btn"); b.type = "button"; b.setAttribute("aria-label", "Слушать: " + p.music_title);
      b.appendChild(DM.icon("music")); b.appendChild(document.createTextNode(p.music_title));
      b.addEventListener("click", () => DM.openPlayer(p.music_title, p.music_url)); facts.appendChild(b);
    }
    side.appendChild(facts);
    if (p.bio) side.appendChild(DM.el("p", "", p.bio));
    if (p.interests.length) { const c = DM.el("div", "chips"); p.interests.forEach(t => c.appendChild(DM.el("span", "chip", t))); side.appendChild(c); }
    if (p.badges && p.badges.length) {
      const b = DM.el("div", "facts"); p.badges.forEach(x => b.appendChild(fact(x.icon, x.title))); side.appendChild(b);
    }

    const actions = DM.el("div", "profile-actions");
    if (isMe) {
      const edit = DM.el("a", "btn sm"); edit.href = "/profile/"; edit.appendChild(DM.icon("pen")); edit.appendChild(document.createTextNode("Редактировать профиль"));
      const set = DM.el("a", "btn ghost sm"); set.href = "/settings/"; set.appendChild(DM.icon("sliders")); set.appendChild(document.createTextNode("Настройки"));
      actions.append(edit, set); showAchievements();
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
    if (isMe) wall.appendChild(DMPeople.composer(post => { const e = posts.querySelector(".muted"); if (e) e.remove(); posts.prepend(DMPeople.postEl(post, { canDelete: true })); }));
    wall.appendChild(posts);
    data.posts.forEach(x => posts.appendChild(DMPeople.postEl(x, { canDelete: isMe })));
    if (!data.posts.length) posts.appendChild(DM.el("p", "muted", isMe ? "Пока пусто. Напишите первый пост, чтобы вас можно было узнать лучше." : "Пока нет постов."));
    body.appendChild(wall);
  }

  async function showAchievements() {
    const box = document.getElementById("achievements"), list = document.getElementById("achv-list");
    try {
      const { achievements } = await DM.api("/api/achievements/");
      list.textContent = "";
      achievements.forEach(a => {
        const d = DM.el("div", "achv-item" + (a.earned ? "" : " off")), ic = DM.el("span", "achv-ic"); ic.appendChild(DM.icon(a.icon));
        d.append(ic, DM.el("strong", "", a.title), DM.el("small", "", a.desc)); list.appendChild(d);
      });
      document.getElementById("achv-summary").textContent = "Получено: " + achievements.filter(a => a.earned).length + " из " + achievements.length;
      box.hidden = false;
    } catch (e) { /* достижения не критичны */ }
  }

  async function load() {
    try { render(await DM.api("/api/users/" + uid + "/")); }
    catch (e) { body.hidden = true; if (e.status === 404) missing.hidden = false; else DM.toast(e.message, "error"); }
  }
  load();
})();
