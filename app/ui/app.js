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
const ctx = { mac: false, student: null, withHeadband: true, session: null, startedAt: 0, timers: [] };

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

async function refreshCloud() {
  const [m, sync] = await Promise.all([api.manager_state(), api.sync_status()]);
  const mp = document.getElementById("manager-pill");
  mp.textContent = m.logged_in ? `Менеджер: ${m.name}` : (m.expired ? "Вход истёк — войти" : "Войти");
  mp.onclick = () => showLogin();
  const sp = document.getElementById("sync-pill");
  if (!sync.configured) { sp.style.display = "none"; return; }
  sp.style.display = "";
  sp.replaceChildren(h("span", { class: `dot ${sync.pending ? (sync.last_error ? "warn" : "") : "good"}` }),
    h("span", {}, sync.pending ? `В облако ждут: ${sync.pending}` : "Облако: всё отправлено"));
  sp.title = sync.last_error || "";
}

function showLogin() {
  managerMode();
  const error = h("div", { class: "error" });
  const email = h("input", { type: "text", placeholder: "Почта", autocomplete: "username" });
  const password = h("input", { type: "password", placeholder: "Пароль", autocomplete: "current-password" });
  const submit = async () => {
    error.textContent = "";
    const result = await api.manager_login(email.value, password.value);
    if (result.error) { error.textContent = result.error; return; }
    refreshCloud();
    showHome("Вход выполнен. Сессии будут уходить в облако, когда есть интернет.");
  };
  password.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  api.manager_state().then((m) => mount(h("div", { class: "page" },
    h("h1", {}, "Вход менеджера"),
    m.logged_in ? h("div", { class: "card stack" },
      h("p", {}, `Вы вошли как ${m.email}. Без интернета приложение работает ещё ${m.offline_days_left} дн.`),
      h("button", { class: "ghost", onclick: async () => { await api.manager_logout(); refreshCloud(); showLogin(); } }, "Выйти"))
    : h("div", { class: "card stack" },
      h("p", { class: "muted" }, "Первый вход требует интернет. Потом приложение работает без сети до 30 дней. Без входа сессии сохраняются на ноутбуке и уйдут в облако после входа."),
      field("Почта", email), field("Пароль", password), error,
      h("div", { class: "row" },
        h("button", { class: "ghost", onclick: () => showHome() }, "Продолжить без входа"),
        h("button", { class: "primary big", onclick: submit }, "Войти"))))));
}

// ── экраны менеджера ────────────────────────────────────────────────────

async function showHome(message) {
  managerMode();
  const [sessions, sync] = await Promise.all([api.sessions_list(), api.sync_status()]);
  // проверка версии ходит в сеть: без интернета ждать её нельзя, плашка появится сама
  const updateSlot = h("div", {});
  api.update_check().then((update) => {
    if (!update) return;
    updateSlot.replaceChildren(h("div", { class: "card row spread" },
      h("span", {}, `Доступна версия ${update.version}. ${update.notes || ""}`),
      update.url ? h("button", { class: "primary", onclick: () => api.open_url(update.url) }, "Скачать") : null));
  });
  const rows = sessions.slice(0, 30).map((s) => h("tr", {},
    h("td", {}, s.student.name), h("td", {}, s.student.grade), h("td", {}, s.student.lang),
    h("td", {}, s.with_headband ? "с ободком" : "без ободка"),
    h("td", {}, STATUS_TEXT[s.status] || s.status),
    h("td", { class: "muted" }, (s.started_at || "").replace("T", " ").slice(0, 16)),
    h("td", {}, s.status === "finished"
      ? h("button", { class: "ghost", onclick: () => showSessionView(s.id) }, "Открыть") : "")));
  mount(h("div", { class: "page" },
    h("div", { class: "row spread" }, h("h1", {}, "Сессии"),
      h("button", { class: "primary big", onclick: () => showNewStudent() }, "Новый ученик")),
    message ? h("div", { class: "card" }, message) : null,
    updateSlot,
    sync.pending ? h("div", { class: "card row spread" },
      h("span", {}, `Не отправлено в облако: ${sync.pending}. ${sync.last_error || ""}`),
      h("button", { onclick: async () => { await api.sync_now(); refreshCloud(); showHome(); } }, "Отправить сейчас")) : null,
    h("div", { class: "card" },
      sessions.length
        ? h("table", {}, h("tr", {}, ...["Ученик", "Класс", "Язык", "Режим", "Статус", "Начало", ""]
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

  // на Mac ободок держит Mind Tracker BCI, программа лишь подключается к нему вторым
  if (ctx.mac) api.device_connect();
  const idleHint = ctx.mac
    ? "Откройте Mind Tracker BCI, подключите в нём ободок и перейдите на вкладку «Мониторинг». Mind Tracker BCI не закрывайте до конца сессии. Затем нажмите «Подключить»."
    : "Закройте Mind Tracker, наденьте ободок, нажмите на нём кнопку и нажмите «Подключить».";

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
    } else if (s.state === "idle" || (ctx.mac && s.state === "error")) {
      hint.textContent = idleHint;
    } else if (ctx.mac && (s.state === "stalled" || s.state === "lost")) {
      hint.textContent = "Сигнал идёт, только пока Mind Tracker BCI открыт на вкладке «Мониторинг». Проверьте его и нажмите «Переподключить».";
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
      resultBlock(result)),
    ctx.withHeadband ? h("div", { class: "card" },
      h("p", {}, "Перед следующим учеником снимите ободок, протрите электроды и переподключите его: после снятия ободок около 30 секунд держит старое соединение.")) : null,
    h("div", { class: "row" },
      h("button", { onclick: () => showHome() }, "К списку сессий"),
      h("button", { class: "primary big", onclick: () => showNewStudent() }, "Следующий ученик"))));
}

const TYPE_NAMES = { R: "практический", I: "исследовательский", A: "творческий",
                     S: "социальный", E: "предпринимательский", C: "организационный" };
const LEVEL_TEXT = { bright: "выражены ярко", moderate: "выражены умеренно", flat: "пока не выражены" };
const SPATIAL_TEXT = { strong: "сильная сторона", middle: "средний уровень", zone: "зона развития" };
const STYLE_NAMES = { E: "Общительность", A: "Доброжелательность", C: "Организованность",
                      I: "Любознательность" };
const FLAG_TEXT = { too_fast: "отвечал(а) слишком быстро", straightlining: "много одинаковых ответов подряд",
                    inconsistent: "опросник и карточки сильно расходятся", guessing: "задачи похоже решались наугад" };

// Итог для разговора с учеником: саммари, направления, комментарий профориентолога.
function resultBlock(summary) {
  const r = summary.result;
  if (!r || !summary.report) return h("p", { class: "error" }, `Итог не посчитан: ${summary.result_error || "нет данных"}`);
  const items = summary.report.summary.map((item, i) => h("div", { class: "summary-item" },
    h("h3", {}, `${i + 1}. ${item.title}`),
    item.steps ? h("ul", {}, ...item.steps.map((x) => h("li", {}, x))) : h("p", {}, item.text)));
  const clusters = summary.report.clusters.map((c, i) =>
    h("p", {}, h("b", {}, `${i + 1}. ${c.title}`), " — ", c.professions.join(", ") || "—"));
  return h("div", { class: "stack" },
    h("div", { class: "row" },
      h("button", { onclick: () => api.open_report(summary.id, "manager") }, "PDF для профориентолога"),
      roadmapButton(summary),
      h("button", { class: "ghost", onclick: () => api.show_folder(summary.id) }, "Папка сессии")),
    ...items,
    clusters.length ? h("h3", {}, "Направления и профессии") : null, ...clusters,
    commentBlock(summary));
}

// дорожная карта BHS — для 8–10 класса, печатается вместе с отчётами
function roadmapButton(summary) {
  const student = summary.student || (summary.meta && summary.meta.student) || {};
  if (![8, 9, 10].includes(student.grade)) return null;
  const note = h("span", { class: "error" });
  const button = h("button", { class: "primary", onclick: async () => {
    const res = await api.open_report(summary.id, "roadmap");
    note.textContent = res && res.error ? res.error : "";
  } }, "Дорожная карта BHS");
  return h("span", { class: "row" }, button, note);
}

function commentBlock(summary) {
  const status = h("div", { class: "muted" },
    summary.comment ? `Комментарий сохранён ${summary.comment.updated_at.replace("T", " ").slice(0, 16)}` :
      "Комментарий попадёт в конец PDF для родителя.");
  const text = h("textarea", { rows: "6", maxlength: "3000",
                               placeholder: "Что вы обсудили с учеником и родителями, на что обратить внимание, что попробовать" });
  text.value = (summary.comment && summary.comment.text) || "";
  const build = h("button", { class: "primary big", onclick: async () => {
    build.disabled = true;
    const res = await api.session_comment(summary.id, text.value);
    build.disabled = false;
    if (res.error) { status.textContent = res.error; status.className = "error"; return; }
    summary.comment = res.comment;
    status.className = "muted";
    status.textContent = res.comment ? "PDF для родителя сформирован с комментарием и открыт." :
      "PDF для родителя сформирован без комментария и открыт.";
  } }, "Сформировать PDF для родителя");
  return h("div", { class: "card stack comment" },
    h("h2", {}, "Комментарий профориентолога"), text, status,
    h("div", { class: "row" }, build,
      h("button", { class: "ghost", onclick: () => api.open_report(summary.id, "parent") }, "Открыть PDF для родителя")));
}

async function showSessionView(sessionId) {
  managerMode();
  const view = await api.session_view(sessionId);
  if (view.error) return showHome(view.error);
  const st = view.meta.student || {};
  mount(h("div", { class: "page" },
    h("div", { class: "row spread" }, h("h1", {}, st.name || sessionId),
      h("button", { class: "ghost", onclick: () => showHome() }, "К списку сессий")),
    h("p", { class: "muted" }, `${st.grade} класс · ${st.lang} · ${(view.meta.started_at || "").replace("T", " ").slice(0, 16)}`),
    h("div", { class: "card stack" }, resultBlock(view))));
}

// ── экраны ученика ──────────────────────────────────────────────────────

function showConsent() {
  stageMode();
  const start = async (withHeadband) => {
    try {
      ctx.withHeadband = withHeadband;
      const result = await call("session_start", { ...ctx.student, with_headband: withHeadband });
      ctx.session = result;
      ctx.content = await call("session_content");
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
  interests: () => likert(ctx.content.interests.items, ctx.content.interests.scale,
                          t("interests_question"), "interest_answer"),

  bigfive: async () => {
    await new Promise((resolve) => mount(h("div", { class: "stage-screen" },
      h("h1", {}, t("bigfive_intro_title")), h("p", {}, t("bigfive_intro_text")),
      h("button", { class: "primary big", onclick: resolve }, t("start")))));
    await likert(ctx.content.bigfive.items, ctx.content.bigfive.scale, ctx.content.bigfive.question,
                 "bigfive_answer");
  },

  cards: async () => {
    const byId = Object.fromEntries(ctx.content.cards.map((card) => [card.id, card]));
    const pairs = ctx.content.card_pairs;
    await new Promise((resolve) => mount(h("div", { class: "stage-screen" },
      h("h1", {}, t("cards_intro_title")), h("p", {}, t("cards_intro_text")),
      h("button", { class: "primary big", onclick: resolve }, t("start")))));
    for (let i = 0; i < pairs.length; i++) {
      const pair = pairs[i];
      const shownAt = performance.now();
      const chosen = await new Promise((done) => mount(h("div", { class: "stage-screen" },
        progress(i, pairs.length),
        h("h1", {}, t("cards_question")),
        h("div", { class: "pair" }, ...pair.map((id) =>
          h("button", { class: "choice-card", onclick: () => done(id) },
            h("img", { src: byId[id].image, alt: "" }), h("span", {}, byId[id].text)))))));
      await call("session_mark", "card_choice",
                 { pair, chosen, rt_ms: Math.round(performance.now() - shownAt) });
    }
  },

  spatial: () => tasks("spatial"),
  numeric: () => tasks("numeric"),
  verbal: () => tasks("verbal"),

  context: async () => {
    const chosen = new Set();
    const max = ctx.content.max_subjects;
    await new Promise((resolve) => {
      const render = () => mount(h("div", { class: "stage-screen" },
        h("h1", {}, t("context_title")), h("p", {}, t("context_text").replace("{n}", max)),
        h("div", { class: "subjects" }, ...ctx.content.subjects.map((s) =>
          h("button", { class: chosen.has(s.id) ? "primary" : "",
                        disabled: !chosen.has(s.id) && chosen.size >= max,
                        onclick: () => { chosen.has(s.id) ? chosen.delete(s.id) : chosen.add(s.id); render(); } },
            s.text))),
        h("button", { class: "primary big", disabled: chosen.size === 0, onclick: resolve }, t("done"))));
      render();
    });
    await call("session_mark", "context_subjects", { subjects: [...chosen] });
  },
};

// Утверждение на экране, шкала из 5 кнопок, клавиши 1–5, можно вернуться.
async function tasks(name) {
  const block = ctx.content[name];
  await new Promise((resolve) => mount(h("div", { class: "stage-screen" },
    h("h1", {}, block.title), h("p", {}, block.instruction),
    h("button", { class: "primary big", onclick: resolve }, t("start")))));
  for (let i = 0; i < block.items.length; i++) {
    const item = block.items[i];
    const options = item.options || block.options;
    const shownAt = performance.now();
    const timer = h("div", { class: "timer" });
    const choice = await new Promise((done) => {
      let left = block.time_limit_s;
      timer.textContent = `${left}`;
      const tick = setInterval(() => {
        left -= 1;
        timer.textContent = `${Math.max(left, 0)}`;
        if (left <= 0) { clearInterval(tick); done(null); }
      }, 1000);
      mount(h("div", { class: `stage-screen task ${name}`, "data-block": name },
        progress(i, block.items.length),
        item.image ? h("img", { src: item.image, alt: "" }) : h("h1", {}, item.text),
        h("div", { class: `options n${options.length}` }, ...options.map((option) =>
          h("button", { class: "big", onclick: () => { clearInterval(tick); done(option.value); } }, option.label))),
        timer));
    });
    await call("session_mark", `${name}_answer`,
               { item: item.id, choice, rt_ms: choice === null ? null : Math.round(performance.now() - shownAt) });
  }
}

async function likert(items, scale, question, eventKind) {
  const answers = {};
  let index = 0;
  await new Promise((resolve) => {
    const render = () => {
      const item = items[index];
      const shownAt = performance.now();
      const choose = async (value) => {
        const rt = Math.round(performance.now() - shownAt);
        answers[item.id] = value;
        document.removeEventListener("keydown", onKey);
        await call("session_mark", eventKind, { item: item.id, value, rt_ms: rt });
        index += 1;
        if (index >= items.length) resolve(); else render();
      };
      const onKey = (e) => { if (e.key >= "1" && e.key <= "5") choose(Number(e.key)); };
      document.addEventListener("keydown", onKey);
      mount(h("div", { class: "stage-screen" },
        progress(index, items.length),
        h("p", { class: "muted" }, question),
        h("h1", {}, item.text),
        h("div", { class: "scale" }, ...scale.map((label, i) =>
          h("button", { class: answers[item.id] === i + 1 ? "primary" : "", onclick: () => choose(i + 1) },
            h("b", {}, String(i + 1)), h("span", {}, label)))),
        index > 0 ? h("button", { class: "ghost", onclick: () => {
          document.removeEventListener("keydown", onKey); index -= 1; render(); } }, t("back")) : null));
    };
    render();
  });
}

function progress(index, total) {
  return h("div", { class: "progress" }, h("div", { style: `width:${Math.round(index / total * 100)}%` }));
}

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
  ctx.mac = info.mac;
  setInterval(refreshPill, 1000);
  setInterval(refreshCloud, 5000);
  refreshPill();
  refreshCloud();
  showHome();
});
