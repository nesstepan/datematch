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
  return { card };
})();
