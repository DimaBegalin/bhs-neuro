"use strict";
// Окно приложения. Ядро на Python доступно как window.pywebview.api
// (app/api.py): каждый вызов — Promise, ошибки ввода приходят как {error}.

const STATE_TEXT = {
  idle: "Ободок не подключён",
  searching: "Ищу ободок…",
  streaming: "Ободок передаёт сигнал",
  stalled: "Сигнал прервался, перезапускаю…",
  lost: "Связь с ободком потеряна",
  error: "Не удалось подключить ободок",
};
const STATE_DOT = { streaming: "good", searching: "warn", stalled: "warn", lost: "bad", error: "bad" };
const QUALITY = { good: ["good", "хороший"], noisy: ["warn", "шумит"], flat: ["bad", "нет контакта"] };
const STATUS_TEXT = { finished: "завершена", aborted: "прервана", interrupted: "оборвалась при сбое",
                      recording: "идёт" };
const CONNECT_PATIENCE_S = 120;

let api = null;
const ctx = { student: null, withHeadband: true, session: null, startedAt: 0, timers: [] };

// ── мелочи ──────────────────────────────────────────────────────────────

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else if (value !== false && value != null) el.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function mount(...nodes) {
  stopTimers();
  document.querySelector("main").replaceChildren(...nodes);
}

function managerMode() { document.body.classList.remove("stage"); }
function stageMode() { document.body.classList.add("stage"); }

function every(ms, fn) { fn(); ctx.timers.push(setInterval(fn, ms)); }
function stopTimers() { ctx.timers.forEach(clearInterval); ctx.timers = []; }
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function t(key) {
  const lang = (ctx.student && ctx.student.lang) || "ru";
  return (window.I18N[lang] && window.I18N[lang][key]) ?? window.I18N.ru[key];
}

let audio = null;
function beep(freq = 660, ms = 350) {
  try {
    audio = audio || new AudioContext();
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.15, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + ms / 1000);
    osc.connect(gain).connect(audio.destination);
    osc.start();
    osc.stop(audio.currentTime + ms / 1000);
  } catch (_) { /* звук не обязателен */ }
}

async function call(method, ...args) {
  const result = await api[method](...args);
  if (result && result.error) throw new Error(result.error);
  return result;
}

// ── верхняя панель ──────────────────────────────────────────────────────

async function refreshPill() {
  const state = await api.device_state();
  const pill = document.getElementById("device-pill");
  pill.replaceChildren(h("span", { class: `dot ${STATE_DOT[state.state] || ""}` }),
                       h("span", {}, STATE_TEXT[state.state] || state.state));
}

// ── экраны менеджера ────────────────────────────────────────────────────

async function showHome(message) {
  managerMode();
  const sessions = await api.sessions_list();
  const rows = sessions.slice(0, 30).map((s) => h("tr", {},
    h("td", {}, s.student.name), h("td", {}, s.student.grade), h("td", {}, s.student.lang),
    h("td", {}, s.with_headband ? "с ободком" : "без ободка"),
    h("td", {}, STATUS_TEXT[s.status] || s.status),
    h("td", { class: "muted" }, (s.started_at || "").replace("T", " ").slice(0, 16))));
  mount(h("div", { class: "page" },
    h("div", { class: "row spread" }, h("h1", {}, "Сессии"),
      h("button", { class: "primary big", onclick: () => showNewStudent() }, "Новый ученик")),
    message ? h("div", { class: "card" }, message) : null,
    h("div", { class: "card" },
      sessions.length
        ? h("table", {}, h("tr", {}, ...["Ученик", "Класс", "Язык", "Режим", "Статус", "Начало"]
            .map((x) => h("th", {}, x))), ...rows)
        : h("p", { class: "muted" }, "Сессий пока нет."))));
}

function segmented(options, value, onChange) {
  const wrap = h("div", { class: "seg", role: "group" });
  const render = (current) => wrap.replaceChildren(...options.map(([key, label]) =>
    h("button", { type: "button", "aria-pressed": String(key === current),
                  onclick: () => { render(key); onChange(key); } }, label)));
  render(value);
  return wrap;
}

// Подпись поля без <label>: label пересылает клик на первую кнопку внутри,
// и переключатель из кнопок всегда возвращался бы к первому варианту.
function field(caption, control) {
  return h("div", { class: "field" }, h("span", {}, caption), control);
}

function showNewStudent() {
  managerMode();
  const draft = { name: "", grade: null, lang: "ru", withHeadband: true };
  const error = h("div", { class: "error" });
  const name = h("input", { type: "text", maxlength: "80", autofocus: true,
                            placeholder: "Имя и фамилия" });
  const submit = () => {
    draft.name = name.value.trim();
    if (!draft.name) return (error.textContent = "Введите имя ученика");
    if (!draft.grade) return (error.textContent = "Выберите класс");
    ctx.student = { name: draft.name, grade: draft.grade, lang: draft.lang };
    ctx.withHeadband = draft.withHeadband;
    return draft.withHeadband ? showDevice() : showConsent();
  };
  mount(h("div", { class: "page" },
    h("h1", {}, "Новый ученик"),
    h("div", { class: "card stack" },
      h("label", {}, "Ученик", name),
      field("Класс", segmented([[8, "8"], [9, "9"], [10, "10"], [11, "11"]], null,
                                        (v) => (draft.grade = v))),
      field("Язык теста", segmented([["ru", "Русский"], ["kk", "Қазақша"]], "ru",
                                             (v) => (draft.lang = v))),
      field("Режим", segmented([[true, "С ободком"], [false, "Без ободка"]], true,
                                        (v) => (draft.withHeadband = v))),
      error),
    h("div", { class: "row" },
      h("button", { class: "ghost", onclick: () => showHome() }, "Назад"),
      h("button", { class: "primary big", onclick: submit }, "Далее"))));
  name.focus();
}

function showDevice() {
  managerMode();
  const shownAt = Date.now();
  const status = h("h2", {});
  const message = h("p", { class: "muted" });
  const channels = h("div", { class: "channels" });
  const battery = h("span", { class: "muted" });
  const hint = h("p", { class: "muted" });
  const next = h("button", { class: "primary big", disabled: true, onclick: () => showConsent() },
                 "Ободок готов, дальше");
  const connect = h("button", { onclick: () => api.device_connect() }, "Подключить");
  const reconnect = h("button", { onclick: () => api.device_reconnect() }, "Переподключить");
  const without = h("button", { class: "ghost", onclick: () => { ctx.withHeadband = false; showConsent(); } },
                    "Продолжить без ободка");
  mount(h("div", { class: "page" },
    h("h1", {}, "Ободок"),
    h("div", { class: "card stack" }, status, message, channels, battery, hint),
    h("div", { class: "row" }, h("button", { class: "ghost", onclick: () => showNewStudent() }, "Назад"),
      connect, reconnect, without, next)));

  every(500, async () => {
    const s = await api.device_state();
    status.textContent = STATE_TEXT[s.state] || s.state;
    message.textContent = s.message || (s.name ? s.name : "");
    channels.replaceChildren(...["T3", "T4", "O1", "O2"].map((ch) => {
      const [dot, text] = QUALITY[(s.quality || {})[ch]] || ["", "—"];
      return h("div", { class: "channel" }, h("b", {}, ch),
               h("span", { class: "row", style: "justify-content:center" },
                 h("span", { class: `dot ${dot}` }), text));
    }));
    battery.textContent = s.battery != null ? `Заряд: ${s.battery}%` : "";
    const streaming = s.state === "streaming" || s.state === "stalled";
    const good = Object.values(s.quality || {}).filter((q) => q === "good").length;
    next.disabled = !streaming;
    connect.disabled = streaming || s.state === "searching";
    if (!streaming && (Date.now() - shownAt) / 1000 > CONNECT_PATIENCE_S) {
      hint.textContent = "Ободок не подключается уже две минуты. Можно продолжить без ободка: рекомендация от этого не изменится.";
      without.classList.add("primary");
    } else if (streaming && good < 4) {
      hint.textContent = "Поправьте ободок: электроды без контакта или с шумом. Смочите их и прижмите плотнее.";
    } else if (s.state === "idle") {
      hint.textContent = "Наденьте ободок, нажмите на нём кнопку и нажмите «Подключить».";
    } else {
      hint.textContent = "";
    }
  });
}

function showSummary(result) {
  managerMode();
  const minutes = result.fs && result.samples ? (result.samples / result.fs / 60).toFixed(1) : null;
  const seconds = Math.round((Date.now() - ctx.startedAt) / 1000);
  mount(h("div", { class: "page" },
    h("h1", {}, "Сессия сохранена"),
    h("div", { class: "card stack" },
      h("h2", {}, ctx.student.name),
      h("p", {}, `Длительность: ${Math.floor(seconds / 60)} мин ${seconds % 60} с`),
      h("p", {}, ctx.withHeadband ? `Записано сигнала: ${minutes} мин` : "Без ободка"),
      h("p", { class: "muted" }, "Отчёт и рекомендация появятся на этапах 2–3.")),
    ctx.withHeadband ? h("div", { class: "card" },
      h("p", {}, "Перед следующим учеником снимите ободок, протрите электроды и переподключите его: после снятия ободок около 30 секунд держит старое соединение.")) : null,
    h("div", { class: "row" },
      h("button", { onclick: () => showHome() }, "К списку сессий"),
      h("button", { class: "primary big", onclick: () => showNewStudent() }, "Следующий ученик"))));
}

// ── экраны ученика ──────────────────────────────────────────────────────

function showConsent() {
  stageMode();
  const start = async (withHeadband) => {
    try {
      ctx.withHeadband = withHeadband;
      const result = await call("session_start", { ...ctx.student, with_headband: withHeadband });
      ctx.session = result;
      ctx.startedAt = Date.now();
      await runPlan(result.plan);
      const done = await call("session_finish");
      await showStudentDone();
      showSummary(done);
    } catch (error) {
      showHome(`Сессию не удалось начать: ${error.message}`);
    }
  };
  mount(h("div", { class: "stage-screen" },
    h("h1", {}, t("consent_title")),
    h("ul", { class: "consent" }, ...t("consent_items").map((item) => h("li", {}, item))),
    h("div", { class: "row" },
      ctx.withHeadband ? h("button", { class: "ghost", onclick: () => start(false) }, t("consent_no_headband")) : null,
      h("button", { class: "primary big", onclick: () => start(ctx.withHeadband) }, t("consent_yes"))),
    h("div", { class: "abort-hint" }, "Esc — прервать")));
}

function showStudentDone() {
  return new Promise((resolve) => {
    mount(h("div", { class: "stage-screen" },
      h("h1", {}, t("done_student_title")), h("p", {}, t("done_student_text")),
      h("button", { class: "ghost", onclick: resolve }, "Для менеджера: открыть итог")));
  });
}

const MODULES = {
  background: async (params) => {
    await new Promise((resolve) => mount(h("div", { class: "stage-screen" },
      h("h1", {}, t("bg_intro_title")), h("p", {}, t("bg_intro_text")),
      h("button", { class: "primary big", onclick: resolve }, t("bg_start")))));
    beep(520);
    await call("session_mark", "background_closed_start", {});
    const timer = h("div", { class: "timer" });
    mount(h("div", { class: "stage-screen" }, h("h1", {}, t("bg_closed")), h("p", {}, t("bg_closed_hint")), timer));
    await countdown(params.closed_s, timer);
    await call("session_mark", "background_closed_end", {});
    beep(880);
    await call("session_mark", "background_open_start", {});
    mount(h("div", { class: "stage-screen" }, h("div", { class: "cross" }, "+"), h("p", {}, t("bg_open_hint"))));
    await sleep(params.open_s * 1000);
    await call("session_mark", "background_open_end", {});
    beep(660, 200);
  },
};

async function countdown(seconds, el) {
  for (let left = seconds; left > 0; left--) {
    el.textContent = `${left}`;
    await sleep(1000);
  }
  el.textContent = "";
}

async function runPlan(plan) {
  for (const module of plan) {
    const run = MODULES[module.id];
    if (!run) throw new Error(`нет модуля ${module.id}`);
    await call("session_mark", "module_start", { module: module.id });
    await run(module.params || {});
    await call("session_mark", "module_end", { module: module.id });
  }
}

document.addEventListener("keydown", async (event) => {
  if (event.key !== "Escape" || !document.body.classList.contains("stage") || !ctx.session) return;
  if (!confirm("Прервать сессию? Записанное сохранится с пометкой «прервана».")) return;
  await api.session_abort("прервано менеджером");
  ctx.session = null;
  location.reload();
});

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  const info = await api.app_info();
  document.getElementById("version").textContent = `v${info.version}`;
  setInterval(refreshPill, 1000);
  refreshPill();
  showHome();
});
