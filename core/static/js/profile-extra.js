/* Редактирование профиля: видео анкеты, цвет карточки, статус, музыка. */
(async function () {
  const $ = id => document.getElementById(id);
  const video = $("my-video"), file = $("video-file"), rm = $("video-remove"), vErr = $("video-err");
  const form = $("style-form"), accent = $("accent");
  const PALETTE = [["#c1473f", "Алый"], ["#e0773a", "Апельсин"], ["#d9a21b", "Золото"], ["#8a9a3a", "Олива"], ["#2e9e6a", "Изумруд"], ["#1a9b9b", "Бирюза"],
    ["#1aa7c9", "Небо"], ["#3c6fd1", "Синий"], ["#5b4bd6", "Индиго"], ["#8e44ad", "Аметист"], ["#c2468f", "Малина"], ["#ff5c8a", "Розовый"],
    ["#8a5a44", "Какао"], ["#6b7280", "Графит"], ["#222222", "Чёрный"], ["#d9a0a5", "Пыльная роза"]];
  let hasAccent = false;

  function setVideo(url) {
    video.hidden = !url; rm.hidden = !url;
    if (url) video.src = url; else { video.removeAttribute("src"); video.load(); }
    $("video-pick-text").textContent = url ? "Заменить видео" : "Загрузить видео";
  }

  const swatchBtns = [];
  function markSwatch() { swatchBtns.forEach(([b, c]) => b.setAttribute("aria-pressed", String(hasAccent && accent.value.toLowerCase() === c))); }
  PALETTE.forEach(([c, name]) => {
    const b = DM.el("button", "swatch"); b.type = "button"; b.style.background = c; b.title = name; b.setAttribute("aria-label", "Цвет: " + name);
    b.addEventListener("click", () => { accent.value = c; hasAccent = true; markSwatch(); });
    $("swatches").appendChild(b); swatchBtns.push([b, c]);
  });
  accent.addEventListener("input", () => { hasAccent = true; markSwatch(); });
  $("accent-clear").addEventListener("click", () => { hasAccent = false; accent.value = "#c1473f"; markSwatch(); });

  try {
    const { user } = await DM.api("/api/me/");
    setVideo(user.video_url);
    hasAccent = !!user.accent; if (user.accent) accent.value = user.accent;
    $("status").value = user.status || ""; $("music_title").value = user.music_title || ""; $("music_url").value = user.music_url || "";
    markSwatch();
  } catch (e) { DM.toast(e.message, "error"); }

  file.addEventListener("change", async () => {
    const f = file.files[0]; file.value = ""; vErr.textContent = "";
    if (!f) return;
    if (!["video/mp4", "video/webm", "video/quicktime"].includes(f.type)) { vErr.textContent = "Нужен файл MP4, WEBM или MOV"; return; }
    if (f.size > 6 * 1024 * 1024) { vErr.textContent = "Видео больше 6 МБ — сожмите или обрежьте его"; return; }
    const fd = new FormData(); fd.append("video", f);
    $("video-pick-text").textContent = "Загружаем…";
    try {
      const { user } = await DM.api("/api/me/video/", { method: "POST", form: fd });
      setVideo(user.video_url); DM.toast("Видео добавлено");
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
      DM.showErrors(form, {}, ""); DM.toast("Оформление сохранено");
    } catch (e) { DM.showErrors(form, e.fields, Object.keys(e.fields).length ? "Исправьте отмеченные поля" : e.message); }
  });
})();
