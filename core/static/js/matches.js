(async function () {
  const list = document.getElementById("list"), empty = document.getElementById("empty");
  try {
    const { matches } = await DM.api("/api/matches/");
    if (!matches.length) { empty.hidden = false; return; }
    matches.forEach(m => {
      const a = DM.el("a", "match-item"); a.href = "/chat/" + m.id + "/";
      const img = DM.el("img", "avatar"); img.src = m.other.photo_url; img.alt = "";
      const meta = DM.el("div", "meta");
      meta.appendChild(DM.el("strong", "", m.other.name + ", " + m.other.age));
      meta.appendChild(DM.el("span", "last", m.last_message || "Напишите первым"));
      const go = DM.el("span", "go"); go.appendChild(DM.icon("chat")); a.append(img, meta, go); list.appendChild(a);
    });
  } catch (e) {
    list.appendChild(DM.el("p", "err", e.message));
  }
})();
