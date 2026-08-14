#!/bin/bash
# Установка нейропрофориентации BHS на ноутбук менеджера.
# Ставит всё нужное, прописывает автозапуск и больше не требует внимания.
set -u
cd "$(dirname "$0")"
APP_DIR="$(pwd)"
AGENT_ID="school.bhs.neuro"
AGENT="$HOME/Library/LaunchAgents/$AGENT_ID.plist"

echo "=========================================="
echo "  Нейропрофориентация BHS: установка"
echo "=========================================="
echo ""

# --- 1. Python. Ставим свой, чтобы не зависеть от того, что уже стоит ---
UV="$HOME/.local/bin/uv"
if [ ! -x "$UV" ]; then
  if command -v uv >/dev/null 2>&1; then
    UV="$(command -v uv)"
  else
    echo "Ставлю служебные файлы, это займёт минуту..."
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
    UV="$HOME/.local/bin/uv"
  fi
fi
if [ ! -x "$UV" ]; then
  echo "ОШИБКА: не получилось поставить служебные файлы."
  echo "Проверьте интернет и запустите этот файл ещё раз."
  read -r -p "Нажмите Enter, чтобы закрыть..."
  exit 1
fi

echo "Готовлю программу..."
"$UV" python install 3.12 >/dev/null 2>&1
"$UV" venv --python 3.12 .venv >/dev/null 2>&1 || {
  echo "ОШИБКА: не удалось подготовить окружение."
  read -r -p "Нажмите Enter, чтобы закрыть..."
  exit 1
}
VIRTUAL_ENV="$APP_DIR/.venv" "$UV" pip install --quiet -r requirements.txt || {
  echo "ОШИБКА: не встали зависимости. Проверьте интернет."
  read -r -p "Нажмите Enter, чтобы закрыть..."
  exit 1
}

# --- 2. Подпись рабочего места ---
CURRENT=$(grep -E '^OPERATOR_NAME=' .env 2>/dev/null | cut -d= -f2-)
echo ""
if [ -n "${CURRENT:-}" ]; then
  echo "Рабочее место уже подписано: $CURRENT"
  read -r -p "Оставить как есть? [Enter — да, или впишите новое имя]: " WHO
  WHO="${WHO:-$CURRENT}"
else
  read -r -p "Ваше имя и фамилия (появится в панели): " WHO
fi
if [ -n "${WHO:-}" ]; then
  # код считает сама программа: она переводит кириллицу в латиницу,
  # иначе русское имя выпадало в бессмысленный хеш вида 7fe77581
  CODE=$(./.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from bridge.operator import _slug
print(_slug(sys.argv[1]))
" "$WHO" 2>/dev/null)
  [ -z "$CODE" ] && CODE=$(echo "$WHO" | md5 -q 2>/dev/null | cut -c1-8)
  touch .env
  grep -v -E '^(OPERATOR|OPERATOR_NAME)=' .env > .env.tmp 2>/dev/null || true
  mv .env.tmp .env
  printf 'OPERATOR=%s\nOPERATOR_NAME=%s\n' "$CODE" "$WHO" >> .env
  echo "Записано: $WHO (код $CODE)"
fi

# --- 3. Автозапуск. Мост поднимается сам при входе в систему ---
mkdir -p "$HOME/Library/LaunchAgents" logs
cat > "$AGENT" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$AGENT_ID</string>
  <key>ProgramArguments</key>
  <array>
    <string>$APP_DIR/.venv/bin/python</string>
    <string>-m</string>
    <string>bridge.main</string>
  </array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$APP_DIR/logs/мост.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/logs/мост.log</string>
</dict>
</plist>
PLIST

launchctl unload "$AGENT" >/dev/null 2>&1 || true
launchctl load "$AGENT" >/dev/null 2>&1

echo ""
echo "Проверяю, что программа отвечает (до минуты на первый запуск)..."
OK=""
for i in $(seq 1 60); do
  sleep 1
  if curl -s -m 2 http://127.0.0.1:8765/status >/dev/null 2>&1; then OK="да"; break; fi
done

echo ""
if [ -n "$OK" ]; then
  echo "=========================================="
  echo "  ГОТОВО. Программа работает и будет"
  echo "  запускаться сама при включении ноутбука."
  echo "=========================================="
  echo ""
  echo "Дальше, перед первым ребёнком:"
  echo "  1. Включите ободок и сопрягите его:"
  echo "     Системные настройки, Bluetooth, Подключить."
  echo "  2. Откройте Mind Tracker BCI, вкладка Мониторинг."
  echo "  3. Откройте сайт теста в Chrome."
else
  echo "Программа установлена, но пока не отвечает."
  echo "Перезагрузите ноутбук и откройте сайт теста."
fi
echo ""
read -r -p "Нажмите Enter, чтобы закрыть..."
