#!/bin/bash
# Установка нейропрофориентации BHS на ноутбук менеджера.
# Ставит всё нужное, прописывает автозапуск и больше не требует внимания.
set -u
cd "$(dirname "$0")"
APP_DIR="$(pwd)"
AGENT_ID="school.bhs.neuro"
AGENT="$HOME/Library/LaunchAgents/$AGENT_ID.plist"
SITE=$(grep -E '^TEST_URL=' .env 2>/dev/null | cut -d= -f2- | tr -d ' ')
[ -z "$SITE" ] && SITE="https://bhs-neuro.vercel.app"

echo "=========================================="
echo "  Нейропрофориентация BHS: установка"
echo "=========================================="
echo ""

# --- 1. Python и библиотеки ---
# Сначала пробуем припасы из коробки: ничего не качается и ничего не
# собирается из исходников. Сборка из исходников заставляет macOS предлагать
# инструменты разработчика, и менеджер видит предложение поставить Xcode.
VENDOR="$APP_DIR/вендор"
VPY="$VENDOR/python/bin/python3"
PYBIN=""

if [ -x "$VPY" ]; then
  MARK=$("$VPY" -c "
import json, platform, sys
try:
    m = json.load(open('$VENDOR/метка.json', encoding='utf-8'))
except Exception:
    sys.exit(1)
print('да' if (m.get('platform') == sys.platform
      and m.get('machine') == platform.machine()) else 'нет')
" 2>/dev/null)
  if [ "${MARK:-нет}" = "да" ]; then
    echo "Ставлю из коробки, интернет не нужен..."
    "$VPY" -m pip install --quiet --no-index \
      --find-links "$VENDOR/колёса" -r requirements.txt && PYBIN="$VPY"
    [ -n "$PYBIN" ] || echo "Припасы не подошли, пробую через интернет..."
  else
    echo "Припасы в коробке не для этого ноутбука, ставлю через интернет..."
  fi
fi

# Запасной путь: скачиваем Python и библиотеки. Нужен интернет.
if [ -z "$PYBIN" ]; then
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
    echo "ОШИБКА: нет интернета, а припасы в коробке не подошли."
    echo "Попросите коробку, собранную под такой же ноутбук."
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
  PYBIN="$APP_DIR/.venv/bin/python"
fi

# Имя менеджера здесь не спрашиваем: он называет себя при входе на сайте,
# и программа берёт его оттуда. Два места для одного имени неизбежно
# разошлись бы, и в панели оказался бы не тот менеджер.

# --- 2. Автозапуск. Программа поднимается сама при входе в систему ---
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
    <string>$PYBIN</string>
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
  echo "  3. Откройте в Chrome: $SITE"
  echo "     Войдите по почте и паролю, которые дала школа."
else
  echo "Программа установлена, но пока не отвечает."
  echo "Перезагрузите ноутбук и откройте сайт теста."
fi
echo ""
read -r -p "Нажмите Enter, чтобы закрыть..."
