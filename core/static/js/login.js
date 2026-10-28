(function () {
  const form = document.getElementById("login-form");
  const btn = document.getElementById("submit-btn");
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const email = form.elements.email.value.trim(), password = form.elements.password.value;
    const errs = {};
    if (!email) errs.email = "Введите email";
    if (!password) errs.password = "Введите пароль";
    DM.showErrors(form, errs, "");
    if (Object.keys(errs).length) return;
    btn.disabled = true;
    try {
      await DM.api("/api/auth/login/", { method: "POST", json: { email, password } });
      location.href = "/discover/";
    } catch (e) {
      DM.showErrors(form, e.fields, e.message);
      btn.disabled = false;
    }
  });
})();
