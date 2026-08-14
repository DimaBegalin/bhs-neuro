#!/bin/bash
# Снятие нейропрофориентации с ноутбука: останавливает автозапуск.
# Записи визитов остаются на месте, папку можно удалить руками.
cd "$(dirname "$0")"
AGENT="$HOME/Library/LaunchAgents/school.bhs.neuro.plist"
launchctl unload "$AGENT" 2>/dev/null
rm -f "$AGENT"
pkill -f "bridge.main" 2>/dev/null
echo "Автозапуск снят, программа остановлена."
echo "Записи визитов остались в папке data, папку можно удалить вручную."
read -r -p "Нажмите Enter, чтобы закрыть..."
