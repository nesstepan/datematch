(async function () {
  const form = document.getElementById("profile-form"), btn = document.getElementById("submit-btn");
  const box = document.getElementById("interests"), PF = window.ProfileForm;
  PF.bindPhotoPreview(form);

  try {
    const { user } = await DM.api("/api/me/");
    for (const k of ["name", "age", "gender", "looking_for", "goal", "bio"]) form.elements[k].value = user[k] || (k === "goal" ? "unsure" : "");
    await PF.renderInterests(box, user.interests);
  } catch (e) { DM.toast(e.message, "error"); }
  PF.bindBioCounter(form);

  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    const errs = {};
    for (const k of ["name", "age", "gender", "looking_for", "bio"]) {
      const m = PF.V[k](form.elements[k].value); if (m) errs[k] = m;
    }
    const p = PF.photoCheck(form.elements.photo.files[0], false); if (p) errs.photo = p;
    DM.showErrors(form, errs, Object.keys(errs).length ? "Исправьте отмеченные поля" : "");
    if (Object.keys(errs).length) return;
    const fd = new FormData(form);
    box.getChosen().forEach(n => fd.append("interests", n));
    btn.disabled = true; btn.textContent = "Сохраняем…";
    try {
      const { user } = await DM.api("/api/me/", { method: "POST", form: fd });
      document.getElementById("photo-preview").src = user.photo_url;
      DM.toast("Профиль сохранён");
    } catch (e) {
      DM.showErrors(form, e.fields, Object.keys(e.fields).length ? "Исправьте отмеченные поля" : e.message);
    } finally { btn.disabled = false; btn.textContent = "Сохранить"; }
  });

  const del = document.getElementById("delete-form");
  del.addEventListener("submit", async ev => {
    ev.preventDefault();
    const password = document.getElementById("del-password").value;
    if (!password) { DM.showErrors(del, { password: "Введите пароль" }, ""); return; }
    if (!confirm("Удалить аккаунт навсегда? Это нельзя отменить.")) return;
    try {
      await DM.api("/api/me/", { method: "DELETE", json: { password } });
      location.href = "/";
    } catch (e) { DM.showErrors(del, e.fields, e.message); }
  });
})();
