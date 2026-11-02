(function () {
  const form = document.getElementById("search-form"), list = document.getElementById("list"), empty = document.getElementById("empty");
  const err = document.getElementById("s-error");
  let token = 0;

  async function run() {
    err.textContent = "";
    const min = form.querySelector("#s-min").value, max = form.querySelector("#s-max").value;
    if ((min && (min < 18 || min > 99)) || (max && (max < 18 || max > 99))) { err.textContent = "Возраст — от 18 до 99"; return; }
    if (min && max && Number(min) > Number(max)) { err.textContent = "Минимальный возраст больше максимального"; return; }
    const q = [];
    const text = form.querySelector("#q").value.trim(), goal = form.querySelector("#s-goal").value;
    if (text) q.push("q=" + encodeURIComponent(text));
    if (min) q.push("age_min=" + min); if (max) q.push("age_max=" + max); if (goal) q.push("goal=" + goal);
    const mine = ++token;
    list.setAttribute("aria-busy", "true");
    try {
      const { profiles } = await DM.api("/api/search/" + (q.length ? "?" + q.join("&") : ""));
      if (mine !== token) return;  // пришёл устаревший ответ
      list.textContent = "";
      profiles.forEach(p => list.appendChild(DMPeople.card(p)));
      empty.hidden = profiles.length > 0;
    } catch (e) { err.textContent = e.message; }
    finally { list.removeAttribute("aria-busy"); }
  }
  form.addEventListener("submit", ev => { ev.preventDefault(); run(); });
  form.querySelector("#s-goal").addEventListener("change", run);
  let timer; form.querySelector("#q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 350); });
  run();
})();
