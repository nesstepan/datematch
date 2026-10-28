/* Клиентская валидация, зеркалирует правила сервера (core/validators.py). Сервер всё равно перепроверяет. */
(function () {
  const V = {
    email: v => !v.trim() ? "Укажите email" : !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(v.trim()) ? "Некорректный email, пример: name@example.com" : "",
    password: v => !v ? "Введите пароль" : v.length < 8 ? "Пароль должен быть не короче 8 символов"
      : !(/[^\W\d_]/u.test(v) && /\d/.test(v)) ? "Пароль должен содержать и буквы, и цифры" : "",
    name: v => { v = v.trim(); return v.length < 2 || v.length > 50 ? "Имя — от 2 до 50 символов"
      : !/^[\p{L}\p{N}_\s'.\-]+$/u.test(v) ? "В имени допустимы только буквы, пробелы, дефис и точка" : ""; },
    age: v => { const n = Number(v); return !v || !Number.isInteger(n) ? "Укажите возраст числом"
      : n < 18 || n > 99 ? "Сервис только для совершеннолетних: возраст от 18 до 99" : ""; },
    gender: v => v ? "" : "Выберите пол",
    looking_for: v => v ? "" : "Укажите, кого вы ищете",
    bio: v => v.length > 500 ? "О себе — не больше 500 символов" : "",
  };

  function photoCheck(file, required) {
    if (!file) return required ? "Загрузите фото профиля" : "";
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) return "Нужен файл JPG, PNG или WEBP";
    if (file.size > 5 * 1024 * 1024) return "Файл больше 5 МБ — выберите фото поменьше";
    return "";
  }

  /* Чипы интересов. selected — массив уже выбранных названий. */
  async function renderInterests(box, selected) {
    const { interests } = await DM.api("/api/interests/");
    const chosen = new Set(selected || []);
    box.textContent = "";
    interests.forEach(i => {
      const b = DM.el("button", "chip", i.name);
      b.type = "button"; b.setAttribute("aria-pressed", chosen.has(i.name));
      b.addEventListener("click", () => {
        if (!chosen.has(i.name) && chosen.size >= 8) { DM.toast("Можно выбрать не больше 8 интересов", "error"); return; }
        chosen.has(i.name) ? chosen.delete(i.name) : chosen.add(i.name);
        b.setAttribute("aria-pressed", chosen.has(i.name));
      });
      box.appendChild(b);
    });
    box.getChosen = () => [...chosen];
  }

  function bindBioCounter(form) {
    const bio = form.querySelector("#bio"), cnt = form.querySelector("#bio-count");
    const upd = () => { cnt.textContent = bio.value.length; };
    bio.addEventListener("input", upd); upd();
  }

  function bindPhotoPreview(form, onChange) {
    const input = form.querySelector("#photo"), img = form.querySelector("#photo-preview");
    input.addEventListener("change", () => {
      const f = input.files[0];
      if (f && !photoCheck(f, true)) { img.src = URL.createObjectURL(f); img.hidden = false; const ph = form.querySelector("#photo-ph"); if (ph) ph.hidden = true; }
      if (onChange) onChange();
    });
  }

  window.ProfileForm = { V, photoCheck, renderInterests, bindBioCounter, bindPhotoPreview };
})();
