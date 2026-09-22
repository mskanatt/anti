/*
 * Логика страницы устройства: согласие, микрофон, локальное распознавание речи (vosk-browser)
 * и отправка только факта срабатывания на сервер. Сырой звук никуда не отправляется и не
 * сохраняется — recognizer работает полностью в этой вкладке.
 *
 * Зависимость: /static/vendor/vosk.js (UMD-сборка vosk-browser) + файл модели в /static/models/.
 */

if (API.getRole() !== "device" || !API.getToken()) {
  window.location.href = "/";
}

const els = {
  consentScreen: document.getElementById("consent-screen"),
  mainScreen: document.getElementById("main-screen"),
  loadError: document.getElementById("load-error"),
  loadErrorText: document.getElementById("load-error-text"),
  banner: document.getElementById("listen-banner"),
  bannerText: document.getElementById("banner-text"),
  micOrb: document.getElementById("mic-orb"),
  statusLine: document.getElementById("status-line"),
  lastHeard: document.getElementById("last-heard"),
  toggleBtn: document.getElementById("toggle-btn"),
  infoLocation: document.getElementById("info-location"),
  deviceSub: document.getElementById("device-sub"),
  forgetBtn: document.getElementById("forget-btn"),
};

const CONSENT_KEY = "ab_consent_given";
const deviceId = localStorage.getItem("ab_device_id") || "";

let deviceConfig = null;   // { triggers, min_confidence, cooldown_seconds }
let audioCtx, micStream, processorNode, sourceNode;
let voskModel, recognizer;
let listening = false;
let heartbeatTimer;
let lastTriggerAt = {}; // локальный анти-спам между отправками, сервер дедуплицирует тоже

function showFatal(message) {
  els.consentScreen.style.display = "none";
  els.mainScreen.style.display = "none";
  els.loadError.style.display = "";
  els.loadErrorText.textContent = message;
}

function setBanner(active) {
  els.banner.style.display = "";
  els.banner.classList.toggle("off", !active);
  els.bannerText.textContent = active ? "Микрофон активен — идёт прослушивание" : "Микрофон выключен";
}

function setStatus(active) {
  els.statusLine.textContent = active ? "Слушаю…" : "Микрофон выключен";
  els.micOrb.classList.toggle("active", active);
  els.toggleBtn.textContent = active ? "Остановить прослушивание" : "Начать прослушивание";
  setBanner(active);
}

async function loadDeviceConfig() {
  deviceConfig = await API.get("/devices/config");
}

async function sendHeartbeat() {
  try {
    await API.post("/devices/heartbeat", { listening });
  } catch (err) {
    if (err.status === 401) {
      // Короткоживущий JWT истёк — обмениваем сохранённый токен устройства на новый.
      const deviceToken = localStorage.getItem("ab_device_token");
      if (deviceToken) {
        try {
          const data = await API.post("/auth/device-login", { device_token: deviceToken });
          API.setSession(data.access_token, "device");
        } catch (_) {
          stopListening();
          showFatal("Сессия устройства недействительна. Отвяжите и привяжите устройство заново.");
        }
      }
    }
  }
}

async function sendEvent(word) {
  const now = Date.now();
  const cooldownMs = (deviceConfig?.cooldown_seconds ?? 20) * 1000;
  if (lastTriggerAt[word] && now - lastTriggerAt[word] < cooldownMs) return;
  lastTriggerAt[word] = now;
  try {
    await API.post("/events", {
      device_id: deviceId || undefined,
      trigger_word: word,
      confidence: 0.75,
      timestamp: new Date().toISOString(),
    });
    els.lastHeard.textContent = `Обнаружено: «${word}» — ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    console.warn("Не удалось отправить событие:", err.message);
  }
}

function checkTriggers(text) {
  if (!deviceConfig || !text) return;
  const lower = text.toLowerCase();
  for (const t of deviceConfig.triggers) {
    if (lower.includes(t.phrase)) sendEvent(t.phrase);
  }
}

async function startListening() {
  if (listening) return;
  els.toggleBtn.disabled = true;
  try {
    if (!deviceConfig) await loadDeviceConfig();

    if (!window.Vosk) {
      throw new Error("Модуль распознавания речи не найден (static/vendor/vosk.js). См. static/vendor/README.md.");
    }
    if (!voskModel) {
      els.statusLine.textContent = "Загрузка модели распознавания…";
      voskModel = await window.Vosk.createModel("/static/models/vosk-model-small-ru.tar.gz");
    }
    recognizer = new voskModel.KaldiRecognizer(16000);
    recognizer.setWords(true);
    recognizer.on("result", (msg) => checkTriggers(msg.result && msg.result.text));
    recognizer.on("partialresult", () => {}); // партиалы игнорируем — реагируем только на финальный результат

    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
    });

    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    sourceNode = audioCtx.createMediaStreamSource(micStream);
    // ScriptProcessorNode устарел, но остаётся самым совместимым способом получить PCM-кадры
    // синхронно для vosk-browser без сборки AudioWorklet-бандла.
    processorNode = audioCtx.createScriptProcessor(4096, 1, 1);
    processorNode.onaudioprocess = (e) => {
      if (recognizer) recognizer.acceptWaveform(e.inputBuffer);
    };
    sourceNode.connect(processorNode);
    processorNode.connect(audioCtx.destination);

    listening = true;
    setStatus(true);
    await sendHeartbeat();
    heartbeatTimer = setInterval(sendHeartbeat, 20000);
  } catch (err) {
    console.error(err);
    els.statusLine.textContent = "Не удалось запустить микрофон";
    alert(err.name === "NotAllowedError"
      ? "Доступ к микрофону запрещён в браузере. Разрешите доступ в настройках сайта."
      : `Ошибка: ${err.message}`);
  } finally {
    els.toggleBtn.disabled = false;
  }
}

function stopListening() {
  listening = false;
  clearInterval(heartbeatTimer);
  sendHeartbeat();
  if (processorNode) { processorNode.disconnect(); processorNode.onaudioprocess = null; }
  if (sourceNode) sourceNode.disconnect();
  if (micStream) micStream.getTracks().forEach((t) => t.stop());
  if (audioCtx) audioCtx.close();
  recognizer = null;
  setStatus(false);
}

els.toggleBtn.addEventListener("click", () => (listening ? stopListening() : startListening()));

els.forgetBtn.addEventListener("click", () => {
  if (!confirm("Отвязать это устройство? Потребуется новый код привязки для повторного подключения.")) return;
  stopListening();
  localStorage.removeItem("ab_device_token");
  localStorage.removeItem("ab_device_id");
  API.clearSession();
  window.location.href = "/";
});

document.getElementById("consent-accept").addEventListener("click", () => {
  localStorage.setItem(CONSENT_KEY, "1");
  els.consentScreen.style.display = "none";
  els.mainScreen.style.display = "";
});
document.getElementById("consent-decline").addEventListener("click", () => {
  window.location.href = "/";
});

window.addEventListener("beforeunload", () => { if (listening) stopListening(); });

// Стартовая инициализация
(async function init() {
  try {
    await loadDeviceConfig();
    els.deviceSub.textContent = "Устройство подключено";
    els.infoLocation.textContent = localStorage.getItem("ab_device_location") || "—";
    setStatus(false);
    if (localStorage.getItem(CONSENT_KEY) === "1") {
      els.mainScreen.style.display = "";
    } else {
      els.consentScreen.style.display = "";
    }
  } catch (err) {
    if (err.status === 401) {
      API.clearSession();
      window.location.href = "/";
      return;
    }
    showFatal("Не удалось связаться с сервером: " + err.message);
  }
})();