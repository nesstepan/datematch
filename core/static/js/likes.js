(async function () {
  const list = document.getElementById("list"), empty = document.getElementById("empty");
  function check() { empty.hidden = list.children.length > 0; }

  function actionsFor(p, box) {
    const row = DM.el("div", "person-actions");
    const pass = DM.el("button", "round"); pass.type = "button"; pass.setAttribute("aria-label", "Пропустить: " + p.name); pass.title = "Пропустить"; pass.appendChild(DM.icon("x"));
    const like = DM.el("button", "round like"); like.type = "button"; like.setAttribute("aria-label", "Нравится: " + p.name); like.title = "Нравится"; like.appendChild(DM.icon("heart", "fill"));
    async function answer(v) {
      pass.disabled = like.disabled = true;
      try {
        const res = await DM.api("/api/swipes/", { method: "POST", json: { target_uid: p.uid, like: v } });
        if (v && res.matched) {
          DM.toast("Это пара! Теперь можно написать: " + p.name);
          const go = DM.el("a", "btn sm", "Написать"); go.href = "/chat/" + res.match_id + "/";
          row.textContent = ""; row.appendChild(go); return;
        }
        box.remove(); check();
      } catch (e) { DM.toast(e.message, "error"); pass.disabled = like.disabled = false; }
    }
    pass.addEventListener("click", () => answer(false)); like.addEventListener("click", () => answer(true));
    row.append(pass, like); return row;
  }

  try {
    const { profiles } = await DM.api("/api/likes/");
    profiles.forEach(p => { const box = DMPeople.card(p); box.appendChild(actionsFor(p, box)); list.appendChild(box); });
    check();
  } catch (e) { DM.toast(e.message, "error"); }
})();
