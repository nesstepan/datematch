/* Обрезка и масштаб фото перед загрузкой (профиль, регистрация, посты).
   Как это работает, по-простому: человек выбирает файл, мы открываем окошко с рамкой. Фото можно двигать пальцем или мышью,
   увеличивать ползунком, колёсиком или щипком, поворачивать. Кнопка «Готово» вырезает то, что внутри рамки, и подменяет
   выбранный файл вырезанным. Дальше форма отправляет уже готовую картинку, как будто человек выбрал её сам. */
(function () {
  const { el, icon } = window.DM;
  const ASPECTS = { "4:5": { label: "4:5", r: 4 / 5 }, "1:1": { label: "1:1", r: 1 }, "3:4": { label: "3:4", r: 3 / 4 }, "16:9": { label: "16:9", r: 16 / 9 } };
  const MAX_SRC = 2600, MAX_OUT = 1600;

  function loadImage(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file), img = new Image();
      img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("Не удалось открыть картинку")); };
      img.src = url;
    });
  }

  /* Открывает окно обрезки. Возвращает Promise: Blob (JPEG) | "original" (оставить как есть) | null (отмена). */
  function open(file, opts) {
    opts = opts || {};
    const names = opts.aspects || ["4:5"], list = names.map(n => ASPECTS[n]).filter(Boolean);
    return new Promise(async resolve => {
      let img;
      try { img = await loadImage(file); } catch (e) { DM.toast(e.message, "error"); resolve(null); return; }

      let src = document.createElement("canvas"), rot = 0, ratio = list[0].r, z = 1, cx = 0, cy = 0, s0 = 1, W = 0, H = 0;
      function buildSource() {   // картинка в нужном повороте (и не больше MAX_SRC по длинной стороне)
        const k = Math.min(1, MAX_SRC / Math.max(img.naturalWidth, img.naturalHeight));
        const w = Math.round(img.naturalWidth * k), h = Math.round(img.naturalHeight * k), turn = rot % 180 !== 0;
        src.width = turn ? h : w; src.height = turn ? w : h;
        const c = src.getContext("2d"); c.save(); c.translate(src.width / 2, src.height / 2); c.rotate(rot * Math.PI / 180);
        c.drawImage(img, -w / 2, -h / 2, w, h); c.restore();
      }

      const wrap = el("div", "modal crop-modal"); wrap.setAttribute("role", "dialog"); wrap.setAttribute("aria-modal", "true"); wrap.setAttribute("aria-label", opts.title || "Обрезка фото");
      const box = el("div", "panel crop-box");
      box.appendChild(el("h2", "", opts.title || "Обрезка фото"));
      box.appendChild(el("p", "muted small", "Двигайте фото, чтобы выбрать главное, и увеличивайте ползунком. В карточке будет видно только то, что внутри рамки."));
      const stage = el("div", "crop-stage"); stage.tabIndex = 0; stage.setAttribute("aria-label", "Область обрезки. Стрелки двигают фото, плюс и минус меняют масштаб.");
      const canvas = el("canvas"); const grid = el("div", "crop-grid"); stage.append(canvas, grid);
      const ctx = canvas.getContext("2d");

      const controls = el("div", "crop-controls");
      const zoomWrap = el("label", "crop-zoom"); zoomWrap.appendChild(el("span", "", "Масштаб"));
      const range = el("input"); range.type = "range"; range.min = "1"; range.max = "4"; range.step = "0.01"; range.value = "1"; range.setAttribute("aria-label", "Масштаб");
      zoomWrap.appendChild(range);
      const rotBtn = el("button", "btn ghost sm"); rotBtn.type = "button"; rotBtn.appendChild(icon("refresh")); rotBtn.appendChild(document.createTextNode("Повернуть"));
      controls.append(zoomWrap, rotBtn);
      let ratioBar = null;
      if (list.length > 1) {
        ratioBar = el("div", "crop-ratios"); ratioBar.setAttribute("role", "group"); ratioBar.setAttribute("aria-label", "Пропорции");
        list.forEach((a, i) => {
          const b = el("button", "chip", a.label); b.type = "button"; b.setAttribute("aria-pressed", String(i === 0));
          b.addEventListener("click", () => { ratio = a.r; ratioBar.querySelectorAll(".chip").forEach(x => x.setAttribute("aria-pressed", String(x === b))); layout(true); });
          ratioBar.appendChild(b);
        });
      }
      const actions = el("div", "row");
      const ok = el("button", "btn"); ok.type = "button"; ok.appendChild(icon("check")); ok.appendChild(document.createTextNode("Готово"));
      const cancel = el("button", "btn ghost"); cancel.type = "button"; cancel.textContent = "Отмена";
      actions.append(ok, cancel);
      if (opts.allowOriginal) { const orig = el("button", "link-btn", "Без обрезки"); orig.type = "button"; orig.addEventListener("click", () => done("original")); actions.appendChild(orig); }
      box.append(stage, controls); if (ratioBar) box.appendChild(ratioBar); box.appendChild(actions);
      wrap.appendChild(box); document.body.appendChild(wrap);
      document.body.classList.add("no-scroll");

      function done(result) { document.body.classList.remove("no-scroll"); wrap.remove(); document.removeEventListener("keydown", onKey, true); resolve(result); }

      function clampCenter() {
        const s = s0 * z, hw = W / (2 * s), hh = H / (2 * s);
        cx = Math.min(Math.max(cx, hw), src.width - hw); cy = Math.min(Math.max(cy, hh), src.height - hh);
      }
      function draw() {
        clampCenter(); const s = s0 * z;
        ctx.clearRect(0, 0, W, H);
        ctx.drawImage(src, cx - W / (2 * s), cy - H / (2 * s), W / s, H / s, 0, 0, W, H);
      }
      function layout(keepCenter) {   // размер рамки зависит от пропорций и размера окна
        const maxW = Math.min(380, window.innerWidth - 64), maxH = Math.max(220, window.innerHeight * 0.5);
        W = Math.min(maxW, maxH * ratio); H = W / ratio;
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); canvas.style.width = W + "px"; canvas.style.height = H + "px";
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        s0 = Math.max(W / src.width, H / src.height);
        if (!keepCenter) { cx = src.width / 2; cy = src.height / 2; z = 1; range.value = "1"; }
        draw();
      }

      /* перетаскивание и щипок */
      const pts = new Map(); let lastDist = 0;
      stage.addEventListener("pointerdown", e => { stage.setPointerCapture(e.pointerId); pts.set(e.pointerId, { x: e.clientX, y: e.clientY }); lastDist = 0; });
      stage.addEventListener("pointermove", e => {
        const p = pts.get(e.pointerId); if (!p) return;
        const dx = e.clientX - p.x, dy = e.clientY - p.y; p.x = e.clientX; p.y = e.clientY;
        if (pts.size === 1) { const s = s0 * z; cx -= dx / s; cy -= dy / s; }
        else if (pts.size === 2) {
          const [a, b] = [...pts.values()], d = Math.hypot(a.x - b.x, a.y - b.y);
          if (lastDist) { z = Math.min(4, Math.max(1, z * d / lastDist)); range.value = String(z); }
          lastDist = d;
        }
        draw();
      });
      const up = e => { pts.delete(e.pointerId); lastDist = 0; };
      stage.addEventListener("pointerup", up); stage.addEventListener("pointercancel", up);
      stage.addEventListener("wheel", e => { e.preventDefault(); z = Math.min(4, Math.max(1, z * (e.deltaY < 0 ? 1.08 : 1 / 1.08))); range.value = String(z); draw(); }, { passive: false });
      range.addEventListener("input", () => { z = parseFloat(range.value); draw(); });
      rotBtn.addEventListener("click", () => { rot = (rot + 90) % 360; buildSource(); layout(false); });
      function onKey(e) {
        if (e.key === "Escape") { e.stopPropagation(); done(null); return; }
        if (!wrap.contains(document.activeElement)) return;
        const step = 12 / (s0 * z);
        if (e.key === "ArrowLeft") cx -= step; else if (e.key === "ArrowRight") cx += step; else if (e.key === "ArrowUp") cy -= step; else if (e.key === "ArrowDown") cy += step;
        else if (e.key === "+" || e.key === "=") z = Math.min(4, z * 1.1); else if (e.key === "-") z = Math.max(1, z / 1.1); else return;
        e.preventDefault(); range.value = String(z); draw();
      }
      document.addEventListener("keydown", onKey, true);
      window.addEventListener("resize", () => layout(true));

      ok.addEventListener("click", () => {
        clampCenter(); const s = s0 * z, rw = W / s, rh = H / s;
        const outW = Math.round(Math.min(MAX_OUT, rw)), outH = Math.round(outW / ratio);
        const out = document.createElement("canvas"); out.width = outW; out.height = outH;
        out.getContext("2d").drawImage(src, cx - rw / 2, cy - rh / 2, rw, rh, 0, 0, outW, outH);
        out.toBlob(b => b ? done(b) : (DM.toast("Не удалось подготовить фото", "error"), done(null)), "image/jpeg", 0.9);
      });
      cancel.addEventListener("click", () => done(null));
      wrap.addEventListener("pointerdown", e => { if (e.target === wrap) done(null); });

      buildSource(); layout(false); ok.focus();
    });
  }

  /* Подключает обрезку к полю выбора файла. Вызывать ДО того, как другие обработчики повесят свой «change». */
  function attach(input, opts) {
    opts = opts || {};
    input.addEventListener("change", async e => {
      if (input._dmCropped) return;                       // это наше собственное повторное событие
      const f = input.files && input.files[0];
      if (!f || f.type === "image/gif" || !f.type.startsWith("image/")) return;   // GIF не режем: пропала бы анимация
      e.stopImmediatePropagation();
      const res = await open(f, opts);
      if (res === null) { input.value = ""; input.dispatchEvent(new CustomEvent("dm:cleared")); return; }
      if (res !== "original") {
        const nf = new File([res], (opts.name || "photo") + ".jpg", { type: "image/jpeg" });
        const dt = new DataTransfer(); dt.items.add(nf); input.files = dt.files;
      }
      input._dmCropped = true; input.dispatchEvent(new Event("change", { bubbles: true })); input._dmCropped = false;
    });
  }

  function autoAttach() {
    document.querySelectorAll("input[type=file][data-crop]").forEach(i => attach(i, { aspects: i.dataset.crop.split(","), title: i.dataset.cropTitle }));
  }
  Object.assign(window.DM, { crop: open, attachCrop: attach });
  autoAttach();   // сразу: поля выбора файла уже есть на странице, а чужие обработчики «change» ещё не повешены
})();
