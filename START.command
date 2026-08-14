#!/bin/bash
# Запуск нейропрофориентации BHS: мост к прибору на этом ноутбуке.
# Страница теста открывается с сайта, но данные пишет мост, который здесь.
cd "$(dirname "$0")"
if [ ! -x ./.venv/bin/python ]; then
  echo "Сначала запустите setup.command (установка, один раз)."
  read -r -p "Нажмите Enter, чтобы закрыть..."
  exit 1
fi
# адрес теста можно задать строкой TEST_URL в файле .env
TEST_URL=$(grep -E '^TEST_URL=' .env 2>/dev/null | cut -d= -f2- | tr -d ' ')
if [ -z "$TEST_URL" ]; then
  TEST_URL="http://127.0.0.1:8080/index.html"
  ./.venv/bin/python tools/serve_web.py > /tmp/bhs_web.log 2>&1 &
  WEB=$!
  trap 'kill $WEB 2>/dev/null' EXIT
fi
WHO=$(./.venv/bin/python -c "from bridge.operator import operator_code, operator_name; print(operator_name() or operator_code())" 2>/dev/null)
( sleep 4; open "$TEST_URL" ) &
echo "Рабочее место: ${WHO:-не определено}"
echo "Страница теста откроется сама: $TEST_URL"
echo "Ободок должен быть включён, Mind Tracker на вкладке Мониторинг."
echo "Чтобы остановить всё: закройте это окно."
echo "----------------------------------------------------------"
./.venv/bin/python -m bridge.main
