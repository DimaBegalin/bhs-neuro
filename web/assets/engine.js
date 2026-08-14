/* Движок теста: калибровка и четыре блока задач.
   Ребёнок своего результата не видит ни на одном экране. */

const CALIB_CLOSED_S = 45;
const CALIB_OPEN_S = 20;
const BLOCK_SECONDS = 45;
const REST_SECONDS = 8;
const WM_STIMULUS_MS = 1400;
const DOMAIN_ORDERS = [
  ["numeric", "spatial", "verbal", "working_memory"],
  ["spatial", "verbal", "working_memory", "numeric"],
  ["verbal", "working_memory", "numeric", "spatial"],
  ["working_memory", "numeric", "spatial", "verbal"]
];
const WM_SYMBOLS = ["◆", "●", "▲", "■", "★", "✦"];
const GRID = 4;

let lang = "ru";
let sessionId = null;
let sessionMeta = null;

function t(key) { return BHS_I18N[lang][key]; }
function screen() { return document.getElementById("screen"); }
function wait(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

function orderForSession(id) {
  let sum = 0;
  for (const ch of id) { sum += ch.charCodeAt(0); }
  return DOMAIN_ORDERS[sum % DOMAIN_ORDERS.length];
}

/* --- процедурные фигуры для пространственного блока --- */

function randomShape() {
  const cells = [[1, 1]];
  const steps = [[0, 1], [1, 0], [0, -1], [-1, 0]];
  while (cells.length < 5) {
    const base = cells[Math.floor(Math.random() * cells.length)];
    const step = steps[Math.floor(Math.random() * steps.length)];
    const next = [base[0] + step[0], base[1] + step[1]];
    const inside = next[0] >= 0 && next[0] < GRID && next[1] >= 0 && next[1] < GRID;
    const taken = cells.some(c => c[0] === next[0] && c[1] === next[1]);
    if (inside && !taken) { cells.push(next); }
  }
  return cells;
}

function rotate(cells) { return cells.map(([r, c]) => [c, GRID - 1 - r]); }
function mirror(cells) { return cells.map(([r, c]) => [r, GRID - 1 - c]); }
function normalize(cells) {
  const minR = Math.min(...cells.map(c => c[0]));
  const minC = Math.min(...cells.map(c => c[1]));
  return cells.map(([r, c]) => [r - minR, c - minC]).sort((a, b) => a[0] - b[0] || a[1] - b[1]);
}
function sameShape(a, b) {
  return JSON.stringify(normalize(a)) === JSON.stringify(normalize(b));
}

function shapeSvg(cells, size) {
  const step = size / GRID;
  const rects = normalize(cells).map(([r, c]) =>
    `<rect x="${c * step + 2}" y="${r * step + 2}" width="${step - 4}" height="${step - 4}" rx="4" fill="#c77df0"/>`
  ).join("");
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">${rects}</svg>`;
}

function makeRotationTask(index) {
  const base = randomShape();
  const answer = rotate(base);
  const options = [answer];
  const candidates = [mirror(answer), rotate(rotate(base)), randomShape(), mirror(base)];
  for (const candidate of candidates) {
    if (options.length >= 4) { break; }
    if (!options.some(o => sameShape(o, candidate))) { options.push(candidate); }
  }
  while (options.length < 4) { options.push(randomShape()); }
  return {
    id: "spa-" + index,
    stem: shapeSvg(base, 130),
    prompt: BHS_BLOCKS.spatial["prompt_" + lang],
    options: options.map(cells => shapeSvg(cells, 96)),
    correct: 0
  };
}

/* --- поток символов для блока рабочей памяти --- */

function makeNbackStream(count) {
  const stream = [WM_SYMBOLS[Math.floor(Math.random() * WM_SYMBOLS.length)]];
  for (let i = 1; i < count; i++) {
    const repeat = Math.random() < 0.35;
    stream.push(repeat ? stream[i - 1]
      : WM_SYMBOLS[Math.floor(Math.random() * WM_SYMBOLS.length)]);
  }
  return stream;
}

/* --- показ задания --- */

function shuffled(options) {
  const indexed = options.map((text, index) => ({text: text, index: index}));
  for (let i = indexed.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [indexed[i], indexed[j]] = [indexed[j], indexed[i]];
  }
  return indexed;
}

function showItem(task) {
  return new Promise(resolve => {
    const options = shuffled(task.options);
    screen().innerHTML = `
      <div class="task">
        <p class="prompt">${task.prompt}</p>
        ${task.stem ? `<div class="stem">${task.stem}</div>` : ""}
        <div class="options">
          ${options.map((o, i) => `<button class="option" data-i="${i}">${o.text}</button>`).join("")}
        </div>
      </div>`;
    screen().querySelectorAll(".option").forEach(button => {
      button.addEventListener("click", () => resolve(options[Number(button.dataset.i)].index));
    });
  });
}

function showMessage(text, extra) {
  screen().innerHTML = `<div class="message"><p>${text}</p>${extra || ""}</div>`;
}

function showCross() {
  screen().innerHTML = `<div class="message"><div class="cross">+</div></div>`;
}

/* --- блоки --- */

async function runFixedBlock(domain) {
  const bank = BHS_BLOCKS[domain];
  const started = performance.now();
  let index = 0;
  while (performance.now() - started < BLOCK_SECONDS * 1000) {
    const item = bank[index % bank.length];
    const task = {
      id: item.id,
      prompt: item["prompt_" + lang],
      options: item["options_" + lang],
      correct: item.correct
    };
    const shownAt = performance.now();
    const picked = await showItem(task);
    await bridgeEvent("trial", {
      domain: domain, index: index, stimulus_id: item.id,
      correct: picked === item.correct,
      rt_ms: Math.round(performance.now() - shownAt)
    });
    index += 1;
  }
}

async function runSpatialBlock() {
  const started = performance.now();
  let index = 0;
  while (performance.now() - started < BLOCK_SECONDS * 1000) {
    const task = makeRotationTask(index);
    const shownAt = performance.now();
    const picked = await showItem(task);
    await bridgeEvent("trial", {
      domain: "spatial", index: index, stimulus_id: task.id,
      correct: picked === task.correct,
      rt_ms: Math.round(performance.now() - shownAt)
    });
    index += 1;
  }
}

async function runWorkingMemoryBlock() {
  const config = BHS_BLOCKS.working_memory;
  showMessage(t("wm_intro"));
  await wait(2500);
  const stream = makeNbackStream(config.count * 3);
  const started = performance.now();
  let index = 1;
  while (performance.now() - started < BLOCK_SECONDS * 1000 && index < stream.length) {
    const symbol = stream[index];
    const isRepeat = symbol === stream[index - 1];
    const task = {
      id: "wm-" + index,
      prompt: config["prompt_" + lang],
      stem: `<div class="symbol">${symbol}</div>`,
      options: config["options_" + lang],
      correct: isRepeat ? 0 : 1
    };
    const shownAt = performance.now();
    const picked = await Promise.race([showItem(task), wait(WM_STIMULUS_MS).then(() => -1)]);
    await bridgeEvent("trial", {
      domain: "working_memory", index: index, stimulus_id: task.id,
      correct: picked === task.correct,
      rt_ms: Math.round(performance.now() - shownAt)
    });
    index += 1;
  }
}

async function runBlock(domain) {
  // сторож: если мост перезапускался, запись сейчас выключена и блок
  // ушёл бы в пустоту. Поднимаем её, теряя в худшем случае один блок
  await bridgeEnsureRecording(sessionId, sessionMeta);
  await bridgeEvent("block_start", {domain: domain});
  if (domain === "spatial") { await runSpatialBlock(); }
  else if (domain === "working_memory") { await runWorkingMemoryBlock(); }
  else { await runFixedBlock(domain); }
  await bridgeEvent("block_end", {domain: domain});
}

/* --- проверка контакта и калибровка --- */

async function waitForContact() {
  showMessage(t("contact_title"), `<p class="hint">${t("contact_hint")}</p>
    <div class="contact-row" id="contact-row"></div>
    <button class="option start" id="go" disabled>${t("start")}</button>`);
  const row = document.getElementById("contact-row");
  const go = document.getElementById("go");
  const tick = async () => {
    const status = await bridgeStatus();
    const contact = status.contact || {};
    const names = Object.keys(contact);
    row.innerHTML = names.map(name =>
      `<span class="chan ${contact[name] >= 0.6 ? "good" : "bad"}">${name}</span>`).join("");
    const allGood = names.length === 4 && names.every(n => contact[n] >= 0.6);
    // мост недоступен: не держим ребёнка на экране контакта, тест идёт без нейро
    go.disabled = !(allGood || window.BHS_BRIDGE_DOWN);
    if (window.BHS_BRIDGE_DOWN) { row.innerHTML = `<span class="hint">${t("bridge_down")}</span>`; }
  };
  await tick();
  const timer = setInterval(tick, 1000);
  await new Promise(resolve => go.addEventListener("click", resolve));
  clearInterval(timer);
}

async function runCalibration() {
  await bridgeEvent("calibration_eyes_closed_start", {});
  showMessage(t("calib_closed"));
  await wait(CALIB_CLOSED_S * 1000);
  await bridgeEvent("calibration_eyes_closed_end", {});

  await bridgeEvent("calibration_eyes_open_start", {});
  showMessage(t("calib_open"), `<div class="cross">+</div>`);
  await wait(CALIB_OPEN_S * 1000);
  await bridgeEvent("calibration_eyes_open_end", {});
  await bridgeCalibrationFinish();
}

/* --- сценарий целиком --- */

let sessionRunning = false;

async function showBridgeState() {
  // менеджер открывает страницу с сайта, а прибор висит на его же ноутбуке.
  // Если мост не поднят, тест молча пройдёт без нейро-слоя, и узнают об этом
  // только на разборе. Поэтому состояние моста видно до начала теста
  const hint = document.getElementById("bridge-hint");
  if (!hint) { return; }
  window.BHS_BRIDGE_DOWN = false;
  const status = await bridgeStatus();
  if (window.BHS_BRIDGE_DOWN) {
    // программы на этом ноутбуке нет вовсе. Тест пройдёт, но без мозга,
    // и менеджер узнает об этом только на разборе, если не сказать сейчас
    hint.innerHTML = "<b>Программа не установлена на этом ноутбуке.</b><br>"
      + "Тест сейчас запишет только ответы, без нейро-слоя. Установите "
      + "«Нейропрофориентация BHS» и откройте страницу заново.";
    hint.style.color = "#F0666B";
    return;
  }
  const place = status.operator_name || status.operator || "";
  if (!status.connected) {
    hint.innerHTML = "<b>Ободок не найден.</b> " + (status.device_error
      || "Включите его и подключите в Mind Tracker.")
      + "<br>Программа ждёт прибор и подхватит его сама."
      + (place ? " Рабочее место: " + place + "." : "");
    hint.style.color = "#F0666B";
    return;
  }
  hint.textContent = "Прибор на связи" + (place ? ", рабочее место: " + place : "")
    + ". Батарея " + (status.battery || 0) + "%.";
  hint.style.color = "";
}

async function runSession() {
  // повторный клик по «Начать» создавал гонку: один старт проходил,
  // ошибка соседнего затирала экран, тест зависал с живой записью
  if (sessionRunning) { return; }
  const studentName = document.getElementById("student-name").value.trim();
  const grade = document.getElementById("grade").value;
  lang = document.getElementById("lang").value;
  if (!studentName) {
    document.getElementById("setup-hint").textContent =
      "Напишите имя и фамилию, без этого карточка не сохранится.";
    return;
  }
  sessionRunning = true;
  const runButton = document.getElementById("run");
  runButton.disabled = true;
  sessionId = "";   // имя сессии выдаёт мост, оно техническое

  sessionMeta = {student_name: studentName, grade: grade, track: lang};
  const started = await bridgeSessionStart(sessionId, sessionMeta);
  if (!started.ok) {
    // запись не пошла: честно останавливаемся, иначе визит пройдёт впустую
    showMessage("Запись не запустилась: " + started.error,
      '<p class="hint">Позовите специалиста. Тест можно начать заново.</p>');
    sessionRunning = false;
    runButton.disabled = false;
    return;
  }
  sessionId = started.sessionId || sessionId;
  document.getElementById("setup").hidden = true;
  await bridgeEvent("session_start", {session_id: sessionId, lang: lang});

  await waitForContact();
  await runCalibration();

  showMessage(t("block_intro"));
  await wait(3000);

  for (const domain of orderForSession(sessionId)) {
    await runBlock(domain);
    await bridgeEvent("rest_start", {});
    showMessage(t("rest"), `<div class="cross">+</div>`);
    await wait(REST_SECONDS * 1000);
    await bridgeEvent("rest_end", {});
  }

  await bridgeEvent("session_end", {});
  const saved = await bridgeSessionStop();
  showMessage(t("done"));
  if (saved) { console.log("запись сохранена", saved); }
}

document.getElementById("run").addEventListener("click", runSession);
showBridgeState();
setInterval(showBridgeState, 5000);
