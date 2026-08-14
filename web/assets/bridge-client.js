const BRIDGE = "http://127.0.0.1:8765";

window.BHS_BRIDGE_DOWN = false;

async function bridgeEvent(kind, payload) {
  try {
    const response = await fetch(BRIDGE + "/event", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({kind: kind, payload: payload || {}})
    });
    return await response.json();
  } catch (error) {
    // мост недоступен: тест продолжается, сессия останется без нейро-слоя
    window.BHS_BRIDGE_DOWN = true;
    return null;
  }
}

async function bridgeStatus() {
  try {
    const response = await fetch(BRIDGE + "/status");
    return await response.json();
  } catch (error) {
    window.BHS_BRIDGE_DOWN = true;
    return {connected: false, contact: {}};
  }
}

async function bridgeSessionStart(sessionId, meta) {
  // возвращает: {ok:true, sessionId} | {ok:false, error} | {ok:true, offline:true}
  // анкету обязательно класть в оба запроса: она стояла только в повторной
  // попытке, и на нормальном старте мост получал пустое имя. Все визиты
  // 13.08 записались как «без имени», различить их в панели было нечем
  const body0 = Object.assign({session_id: sessionId, out_dir: "data",
                               force: false}, meta || {});
  try {
    const response = await fetch(BRIDGE + "/session/start", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body0)
    });
    let body = await response.json();
    if (response.status === 409) {
      // страницу перезагрузили посреди теста: старая запись висит на мосту.
      // Закрываем её (данные сохранятся файлом) и стартуем заново сами
      await fetch(BRIDGE + "/session/stop", {method: "POST"}).catch(function(){});
      const retry = await fetch(BRIDGE + "/session/start", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(Object.assign(
          {session_id: sessionId, out_dir: "data", force: false}, meta || {}))
      });
      body = await retry.json();
      if (!retry.ok) {
        return {ok: false, error: body.detail || ("мост отказал, код " + retry.status)};
      }
      return {ok: true, sessionId: body.session_id || sessionId};
    }
    if (!response.ok) {
      return {ok: false, error: body.detail || ("мост отказал, код " + response.status)};
    }
    return {ok: true, sessionId: body.session_id || sessionId};
  } catch (error) {
    // моста нет вовсе: тест идёт без нейро-слоя, это штатная деградация
    window.BHS_BRIDGE_DOWN = true;
    return {ok: true, offline: true, sessionId: sessionId};
  }
}

async function bridgeEnsureRecording(sessionId, meta) {
  // Мост может перезапуститься посреди теста: упасть, быть обновлённым руками.
  // Тогда он остаётся жив и продолжает принимать метки, но запись выключена,
  // и сигнал молча уходит в никуда. Ребёнок доходит до конца, а визит остаётся
  // без нейро-слоя, и узнают об этом только на разборе. Поэтому перед каждым
  // блоком спрашиваем, идёт ли запись, и поднимаем её обратно.
  try {
    const status = await bridgeStatus();
    if (status.running) { return false; }
    const response = await fetch(BRIDGE + "/session/start", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.assign(
        {session_id: sessionId, out_dir: "data", force: true}, meta || {}))
    });
    if (response.ok) { console.warn("запись возобновлена: мост перезапускался"); }
    return response.ok;
  } catch (error) {
    return false;   // моста нет вовсе, это штатная деградация
  }
}

async function bridgeCalibrationFinish() {
  try {
    const response = await fetch(BRIDGE + "/calibration/finish", {method: "POST"});
    return await response.json();
  } catch (error) {
    return null;
  }
}

async function bridgeSessionStop() {
  try {
    const response = await fetch(BRIDGE + "/session/stop", {method: "POST"});
    return await response.json();
  } catch (error) {
    return null;
  }
}
