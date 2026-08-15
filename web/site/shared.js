/* Общее для страниц сайта: облако, вход менеджера и связь с программой.

   Ключ anon публичный по замыслу: он лежит на странице, и записи защищает
   не он, а правила доступа базы. Чужие визиты по нему не прочитать. */
const BRIDGE = "http://127.0.0.1:8765";
const SESSION_KEY = "bhs_session";

function cloudSettings() {
  return {url: (window.BHS_CONFIG || {}).supabaseUrl || "",
          key: (window.BHS_CONFIG || {}).supabaseKey || ""};
}

function saveSession(session) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

function readSession() {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || "null"); }
  catch (e) { return null; }
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

/* Токен живёт час. Обновляем заранее, иначе панель посреди разбора
   вдруг покажет пустой список вместо визитов. */
async function liveToken() {
  const session = readSession();
  if (!session) { return null; }
  if (Date.now() / 1000 < session.expires_at - 300) { return session.access_token; }
  const {url, key} = cloudSettings();
  try {
    const response = await fetch(url + "/auth/v1/token?grant_type=refresh_token", {
      method: "POST",
      headers: {"apikey": key, "Content-Type": "application/json"},
      body: JSON.stringify({refresh_token: session.refresh_token})
    });
    if (!response.ok) { throw new Error("вход устарел"); }
    const body = await response.json();
    const fresh = {
      access_token: body.access_token,
      refresh_token: body.refresh_token || session.refresh_token,
      manager_id: session.manager_id,
      email: session.email,
      expires_at: Math.floor(Date.now() / 1000) + (body.expires_in || 3600)
    };
    saveSession(fresh);
    tellBridge(fresh);
    return fresh.access_token;
  } catch (e) {
    clearSession();
    return null;
  }
}

/* Программе на ноутбуке вход нужен свой: визит она отправляет сама,
   уже после того как посчитает профиль, и страница к тому моменту
   может быть закрыта. */
async function tellBridge(session) {
  try {
    await fetch(BRIDGE + "/manager", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(session)
    });
    return true;
  } catch (e) { return false; }
}

async function bridgeStatus() {
  try {
    const response = await fetch(BRIDGE + "/status");
    return await response.json();
  } catch (e) { return null; }
}

function requireSession() {
  if (!readSession()) { location.replace("login"); return false; }
  return true;
}

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g,
    c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}
