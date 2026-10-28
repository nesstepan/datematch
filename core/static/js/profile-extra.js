/* Профиль: видео анкеты, оформление, музыка, скрытие из поиска, достижения. */
(async function () {
  const $ = id => document.getElementById(id);
  const video = $("my-video"), file = $("video-file"), rm = $("video-remove"), vErr = $("video-err");
  const form = $("style-form"), accent = $("accent"), hidden = $("hidden");
  const PALETTE = ["#ff5c8a", "#4b3bff", "#14a36f", "#ff9f1c", "#00a6d6", "#c93a52", "#8e44ad", "#222222"];
  let hasAccent = false;

  function setVideo(url) {
    video.hidden = !url; rm.hidden = !url;
    if (url) video.src = url; else { video.removeAttribute("src"); video.load(); }
    $("video-pick-text").textContent = url ? "Заменить видео" : "Загрузить видео";
  }

  PALETTE.forEach(c => {
    const b = DM.el("button", "swatch"); b.type = "button"; b.style.background = c; b.setAttribute("aria-label", "Цвет " + c);
    b.addEventListener("click", () => { accent.value = c; hasAccent = true; });
    $("swatches").appendChild(b);
  });
  accent.addEventListener("input", () => { hasAccent = true; });
  $("accent-clear").addEventListener("click", () => { hasAccent = false; accent.value = "#ff5c8a"; });

  async function loadAchievements() {
    try {
      const { achievements } = await DM.api("/api/achievements/");
      const list = $("achv-list"); list.textContent = "";
      achievements.forEach(a => {
        const d = DM.el("div", "achv-item" + (a.earned ? "" : " off"));
        const ic = DM.el("span", "achv-ic"); ic.appendChild(DM.icon(a.icon));
        d.appendChild(ic); d.appendChild(DM.el("strong", "", a.title)); d.appendChild(DM.el("small", "", a.desc));
        list.appendChild(d);
      });
      $("achv-summary").textContent = "Получено: " + achievements.filter(a => a.earned).length + " из " + achievements.length;
    } catch (e) { DM.toast(e.message, "error"); }
  }

  try {
    const { user } = await DM.api("/api/me/");
    setVideo(user.video_url);
    hasAccent = !!user.accent; if (user.accent) accent.value = user.accent;
    $("status").value = user.status || ""; $("music_title").value = user.music_title || ""; $("music_url").value = user.music_url || "";
    hidden.checked = !!user.hidden;
  } catch (e) { DM.toast(e.message, "error"); }
  loadAchievements();

  file.addEventListener("change", async () => {
    const f = file.files[0]; file.value = ""; vErr.textContent = "";
    if (!f) return;
    if (!["video/mp4", "video/webm", "video/quicktime"].includes(f.type)) { vErr.textContent = "Нужен файл MP4, WEBM или MOV"; return; }
    if (f.size > 6 * 1024 * 1024) { vErr.textContent = "Видео больше 6 МБ — сожмите или обрежьте его"; return; }
    const fd = new FormData(); fd.append("video", f);
    $("video-pick-text").textContent = "Загружаем…";
    try {
      const { user } = await DM.api("/api/me/video/", { method: "POST", form: fd });
      setVideo(user.video_url); DM.toast("Видео добавлено"); loadAchievements();
    } catch (e) { vErr.textContent = (e.fields && e.fields.video) || e.message; setVideo(video.getAttribute("src") || ""); }
  });
  rm.addEventListener("click", async () => {
    if (!confirm("Удалить видео из анкеты?")) return;
    try { await DM.api("/api/me/video/", { method: "DELETE" }); setVideo(""); DM.toast("Видео удалено"); }
    catch (e) { vErr.textContent = e.message; }
  });

  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    const json = { accent: hasAccent ? accent.value : "", status: $("status").value, music_title: $("music_title").value, music_url: $("music_url").value };
    try {
      await DM.api("/api/me/settings/", { method: "POST", json });
      DM.showErrors(form, {}, ""); DM.toast("Оформление сохранено"); loadAchievements();
    } catch (e) { DM.showErrors(form, e.fields, Object.keys(e.fields).length ? "Исправьте отмеченные поля" : e.message); }
  });

  hidden.addEventListener("change", async () => {
    try {
      await DM.api("/api/me/settings/", { method: "POST", json: { hidden: hidden.checked } });
      DM.toast(hidden.checked ? "Вас не видно в поиске" : "Вы снова в поиске");
    } catch (e) { hidden.checked = !hidden.checked; DM.toast(e.message, "error"); }
  });
})();
