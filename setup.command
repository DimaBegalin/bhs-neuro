#!/bin/bash
# Установка окружения нейропрофориентации BHS. Запускается один раз.
cd "$(dirname "$0")"
echo "Ищу Python 3.12..."
PY=""
for candidate in python3.12 /usr/local/bin/python3.12 /opt/homebrew/bin/python3.12; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
  echo ""
  echo "Python 3.12 не найден. Установите его с python.org (см. УСТАНОВКА.md)"
  echo "и запустите этот файл ещё раз."
  read -r -p "Нажмите Enter, чтобы закрыть..."
  exit 1
fi
echo "Нашёл: $PY"
echo "Создаю окружение и ставлю зависимости, это займёт пару минут..."
"$PY" -m venv .venv || exit 1
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt || {
  echo "Зависимости не встали. Проверьте интернет и запустите ещё раз."
  read -r -p "Нажмите Enter, чтобы закрыть..."
  exit 1
}
echo ""
echo "ГОТОВО. Дальше: ободок в Mind Tracker, затем START.command"
read -r -p "Нажмите Enter, чтобы закрыть..."
