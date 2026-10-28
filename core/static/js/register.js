(function () {
  const form = document.getElementById("reg-form");
  const box = document.getElementById("interests");
  const btn = document.getElementById("submit-btn");
  const PF = window.ProfileForm;

  PF.renderInterests(box, []).catch(e => DM.toast(e.message, "error"));
  PF.bindBioCounter(form);
  PF.bindPhotoPreview(form);

  function validate() {
    const g = n => form.elements[n].value;
    const errs = {};
    for (const k of ["email", "password", "name", "age", "gender", "looking_for", "bio"]) {
      const m = PF.V[k](g(k)); if (m) errs[k] = m;
    }
    if (g("password") !== document.getElementById("password2").value) errs.password2 = "Пароли не совпадают";
    const p = PF.photoCheck(form.elements.photo.files[0], true); if (p) errs.photo = p;
    return errs;
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const errs = validate();
    DM.showErrors(form, errs, Object.keys(errs).length ? "Исправьте отмеченные поля" : "");
    if (Object.keys(errs).length) return;
    const fd = new FormData(form);
    (box.getChosen ? box.getChosen() : []).forEach(n => fd.append("interests", n));
    btn.disabled = true; btn.textContent = "Создаём анкету…";
    try {
      await DM.api("/api/auth/register/", { method: "POST", form: fd });
      location.href = "/discover/";
    } catch (e) {
      DM.showErrors(form, e.fields, Object.keys(e.fields).length ? "Исправьте отмеченные поля" : e.message);
      btn.disabled = false; btn.textContent = "Зарегистрироваться";
    }
  });
})();
