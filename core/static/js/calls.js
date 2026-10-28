/* Аудио- и видеозвонки в паре (WebRTC). Сигналы (offer/answer/candidate/hangup) передаются через API и
   опрашиваются раз в 1,5 с только во время звонка. Для связи через разные сети нужен TURN-сервер (см. docs/06). */
(function () {
  const root = document.querySelector(".chat");
  if (!root) return;
  const mid = root.dataset.match, base = "/api/matches/" + mid + "/signals/";
  const $ = id => document.getElementById(id);
  const ui = { box: $("call"), remote: $("remote-video"), local: $("local-video"), who: $("call-who"), state: $("call-state"),
    mute: $("call-mute"), cam: $("call-cam"), end: $("call-end"), accept: $("call-accept") };
  const DEFAULT_ICE = { iceServers: [{ urls: "stun:stun.l.google.com:19302" }] };
  async function iceConfig() {  // TURN (если настроен на сервере) нужен, когда собеседники в разных сетях за NAT
    try { return { iceServers: (await DM.api("/api/ice/")).iceServers }; } catch (e) { return DEFAULT_ICE; }
  }

  let pc = null, stream = null, poller = null, ringTimer = null, since = 0, role = "";
  let seen = new Set(), queue = [], pending = [], remoteSet = false, ready = false, active = false, connected = false;

  const send = (kind, payload) => DM.api(base, { method: "POST", json: { kind, payload: payload || {} } });
  const say = t => { ui.state.textContent = t; };

  async function getMedia(video) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.RTCPeerConnection) {
      DM.toast("Звонки не поддерживаются этим браузером или нужен защищённый адрес (https)", "error"); return null;
    }
    try { return await navigator.mediaDevices.getUserMedia({ audio: true, video: video ? { facingMode: "user" } : false }); }
    catch (e) { DM.toast(video ? "Нет доступа к камере или микрофону" : "Нет доступа к микрофону", "error"); return null; }
  }

  function open(text, video) {
    active = true; connected = false; ready = false; remoteSet = false; seen = new Set(); queue = []; pending = []; since = 0;
    ui.who.textContent = root.dataset.other; say(text);
    ui.local.srcObject = stream; ui.local.hidden = !video; ui.cam.hidden = !video;
    ui.accept.hidden = true; ui.box.hidden = false;
  }

  function makePc(cfg) {
    pc = new RTCPeerConnection(cfg);
    stream.getTracks().forEach(t => pc.addTrack(t, stream));
    pc.onicecandidate = e => {
      if (!e.candidate) return;
      const c = e.candidate.toJSON();
      if (ready) send("candidate", c).catch(() => {}); else pending.push(c);
    };
    pc.ontrack = e => { ui.remote.srcObject = e.streams[0]; };
    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "connected") { connected = true; clearTimeout(ringTimer); say("Разговор идёт"); }
      else if (pc.connectionState === "disconnected") say("Связь прервана…");
      else if (pc.connectionState === "failed") end(true, "Не удалось соединиться. Возможно, нужен TURN-сервер");
    };
  }

  async function releaseCandidates() {  // кандидаты уходят только после offer/answer, иначе offer сотрёт их на сервере
    ready = true;
    for (const c of pending.splice(0)) await send("candidate", c).catch(() => {});
  }
  async function addCandidate(c) {
    if (!pc || !remoteSet) { queue.push(c); return; }
    try { await pc.addIceCandidate(c); } catch (e) { /* устаревший кандидат */ }
  }
  async function markRemoteSet() {
    remoteSet = true;
    for (const c of queue.splice(0)) await addCandidate(c);
  }

  async function handle(s) {
    let p = {}; try { p = JSON.parse(s.payload || "{}"); } catch (e) { /* пусто */ }
    if (s.kind === "answer" && role === "caller" && pc && !remoteSet) { await pc.setRemoteDescription(p.sdp); await markRemoteSet(); }
    else if (s.kind === "candidate") await addCandidate(p);
    else if (s.kind === "hangup") end(false, "Собеседник завершил звонок");
    else if (s.kind === "decline") end(false, "Звонок отклонён");
  }

  function startPolling() {
    clearInterval(poller);
    poller = setInterval(async () => {
      if (!active) return;
      try {
        const { signals } = await DM.api(base + "?since=" + Math.max(0, since - 0.5));
        for (const s of signals) {
          if (seen.has(s.id)) continue;
          seen.add(s.id); since = Math.max(since, s.created_at);
          await handle(s);
        }
      } catch (e) { if (e.status === 404) end(false, "Пара больше не существует"); }
    }, 1500);
  }

  async function start(video) {
    if (active) return;
    const s = await getMedia(video); if (!s) return;
    stream = s; role = "caller"; open("Звоним…", video); makePc(await iceConfig());
    try {
      const offer = await pc.createOffer(); await pc.setLocalDescription(offer);
      await send("offer", { sdp: { type: offer.type, sdp: offer.sdp }, video: !!video });
      await releaseCandidates();
    } catch (e) { end(false, e.message || "Не удалось начать звонок"); return; }
    ringTimer = setTimeout(() => { if (!connected) end(true, "Нет ответа"); }, 45000);
    startPolling();
  }

  async function accept() {
    if (active) return;
    let offer = null, all = [];
    try { all = (await DM.api(base + "?since=0")).signals; } catch (e) { DM.toast(e.message, "error"); return; }
    for (const s of all) if (s.kind === "offer") offer = s;
    if (!offer || all.some(s => (s.kind === "hangup" || s.kind === "decline") && s.created_at > offer.created_at)) {
      ui.box.hidden = true; DM.toast("Звонок уже завершён"); return;
    }
    const p = JSON.parse(offer.payload), video = !!p.video;
    const s = await getMedia(video);
    if (!s) { send("decline").catch(() => {}); ui.box.hidden = true; return; }
    stream = s; role = "callee"; open("Соединяем…", video); makePc(await iceConfig()); seen.add(offer.id);
    try {
      await pc.setRemoteDescription(p.sdp); await markRemoteSet();
      const ans = await pc.createAnswer(); await pc.setLocalDescription(ans);
      await send("answer", { sdp: { type: ans.type, sdp: ans.sdp } });
      await releaseCandidates();
    } catch (e) { end(true, "Не удалось принять звонок"); return; }
    startPolling();
  }

  function end(notify, text) {
    if (!active && !pc) { ui.box.hidden = true; return; }
    if (notify) send("hangup").catch(() => {});
    clearInterval(poller); clearTimeout(ringTimer);
    if (pc) { pc.close(); pc = null; }
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    ui.remote.srcObject = ui.local.srcObject = null;
    active = false; ui.box.hidden = true;
    if (text) DM.toast(text);
  }

  ui.end.addEventListener("click", () => {
    if (active) return end(true, "Звонок завершён");
    send("decline").catch(() => {}); ui.box.hidden = true;  // отклонили, пока звонок ещё не принят
  });
  ui.accept.addEventListener("click", accept);
  ui.mute.addEventListener("click", () => {
    if (!stream) return;
    const t = stream.getAudioTracks()[0]; if (!t) return;
    t.enabled = !t.enabled; ui.mute.classList.toggle("off", !t.enabled);
  });
  ui.cam.addEventListener("click", () => {
    const t = stream && stream.getVideoTracks()[0]; if (!t) return;
    t.enabled = !t.enabled; ui.cam.classList.toggle("off", !t.enabled);
  });
  $("call-audio").addEventListener("click", () => start(false));
  $("call-video").addEventListener("click", () => start(true));
  window.addEventListener("beforeunload", () => { if (active) navigator.sendBeacon && end(true); });

  window.DMCall = { start, accept };
  // пришли по кнопке «Принять» с другой страницы: нужен ещё один клик, чтобы браузер разрешил звук и камеру
  if (new URLSearchParams(location.search).get("accept") === "1") {
    history.replaceState(null, "", location.pathname);
    ui.who.textContent = root.dataset.other; say("Входящий звонок");
    ui.accept.hidden = false; ui.cam.hidden = true; ui.local.hidden = true; ui.box.hidden = false;
  }
})();
