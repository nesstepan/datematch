/* Уведомления (лайки, пары, сообщения, звонки, достижения): опрос раз в 8 секунд, пока вкладка открыта. */
(function () {
  const btn = document.getElementById("bell-btn"), panel = document.getElementById("bell-panel");
  const dot = document.getElementById("bell-dot"), list = document.getElementById("bell-list");
  const allow = document.getElementById("bell-allow");
  const inbox = document.getElementById("incoming");
  const chatMatch = (location.pathname.match(/^\/chat\/([^/]+)\//) || [])[1] || "";
  const known = new Set(); let first = true, incoming = null;

  function link(n) {
    if (n.type === "like") return "/likes/";
    if (n.type === "achievement") return "/profile/#achievements";
    if ((n.type === "post_like" || n.type === "comment") && n.data && n.data.author_uid) return "/u/" + n.data.author_uid + "/#post-" + n.data.post_id;
    return n.match_id ? "/chat/" + n.match_id + "/" : "/matches/";
  }
  const ICONS = { like: "heart", match: "hearts", message: "chat", call: "phone", achievement: "trophy", post_like: "heart", comment: "chat" };

  function render(items) {
    list.textContent = "";
    if (!items.length) list.appendChild(DM.el("p", "muted small center", "Новых уведомлений нет. Здесь появятся лайки, пары и сообщения."));
    items.forEach(n => {
      const a = DM.el("a", "notif"); a.href = link(n);
      if (n.photo_url) { const i = DM.el("img"); i.src = n.photo_url; i.alt = ""; a.appendChild(i); }
      else { const ic = DM.el("div", "ico t-" + n.type); ic.appendChild(DM.icon(ICONS[n.type] || "bell")); a.appendChild(ic); }
      a.appendChild(DM.el("span", "", n.text));
      a.addEventListener("click", () => markRead({ ids: [n.id] }));
      list.appendChild(a);
    });
    dot.hidden = !items.length; dot.textContent = items.length > 9 ? "9+" : items.length;
    const likes = items.filter(n => n.type === "like").length, ld = document.getElementById("likes-dot");
    if (ld) { ld.hidden = !likes; ld.textContent = likes > 9 ? "9+" : likes; }
  }

  function markRead(body) {
    return DM.api("/api/notifications/read/", { method: "POST", json: body }).catch(() => {});
  }

  function showIncoming(n) {
    incoming = n;
    document.getElementById("incoming-photo").src = n.photo_url || "";
    document.getElementById("incoming-name").textContent = n.from_name;
    document.getElementById("incoming-kind").textContent = n.data && n.data.video ? "Видеозвонок" : "Аудиозвонок";
    inbox.hidden = false;
  }
  function hideIncoming() { inbox.hidden = true; incoming = null; }

  if (inbox) {
    document.getElementById("incoming-accept").addEventListener("click", () => {
      const mid = incoming && incoming.match_id; hideIncoming();
      if (!mid) return;
      if (mid === chatMatch && window.DMCall) window.DMCall.accept(); else location.href = "/chat/" + mid + "/?accept=1";
    });
    document.getElementById("incoming-decline").addEventListener("click", async () => {
      const mid = incoming && incoming.match_id; hideIncoming();
      if (!mid) return;
      try { await DM.api("/api/matches/" + mid + "/signals/", { method: "POST", json: { kind: "decline", payload: {} } }); } catch (e) { /* ок */ }
    });
  }

  function browserNotify(n) {
    if (!document.hidden || !("Notification" in window) || Notification.permission !== "granted") return;
    try { const x = new Notification("DateMatch", { body: n.text, icon: n.photo_url || undefined, tag: n.id });
      x.onclick = () => { window.focus(); location.href = link(n); }; } catch (e) { /* не поддерживается */ }
  }

  async function poll() {
    if (document.hidden) return;
    let data;
    try { data = await DM.api("/api/notifications/"); } catch (e) { return; }
    let items = data.notifications;
    // в открытом чате сообщения собеседника считаются прочитанными сразу
    const here = items.filter(n => n.type === "message" && chatMatch && n.match_id === chatMatch);
    if (here.length) { markRead({ match_id: chatMatch, types: ["message"] }); items = items.filter(n => !here.includes(n)); }
    items.forEach(n => {
      if (known.has(n.id)) return;
      known.add(n.id);
      const fresh = Date.now() / 1000 - n.created_at < 60;
      if (n.type === "call") { if (fresh && !(incoming && incoming.id === n.id)) showIncoming(n); return; }
      if (!first) { DM.toast(n.text); browserNotify(n); }
    });
    if (incoming && !items.some(n => n.id === incoming.id)) hideIncoming();
    first = false; render(items);
  }

  btn.addEventListener("click", () => {
    panel.hidden = !panel.hidden; btn.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden && "Notification" in window && Notification.permission === "default") allow.hidden = false;
  });
  document.addEventListener("click", e => { if (!panel.hidden && !e.target.closest(".bell-wrap")) { panel.hidden = true; btn.setAttribute("aria-expanded", "false"); } });
  document.getElementById("bell-clear").addEventListener("click", async () => {
    await markRead({ all: true }); render([]); known.clear();
  });
  allow.addEventListener("click", async () => {
    try { await Notification.requestPermission(); } catch (e) { /* ок */ }
    allow.hidden = true;
  });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
  poll(); setInterval(poll, 8000);
})();
