# Windows: единый EXE

Готовая программа — один файл `BHS-Neuro.exe`. Внутри уже находятся Python,
расчёты, драйверный слой SDK, локальный сайт и генератор PDF. Устанавливать
Python и запускать `pip` на ноутбуке менеджера не нужно.

## Использование

1. Положить `BHS-Neuro.exe` в постоянную папку, например
   `C:\BHS-Neuro\BHS-Neuro.exe`.
2. Закрыть Mind Tracker: в Windows ободок может держать только одно
   подключение, и EXE подключается к нему через официальный SDK.
3. Включить ободок и запустить EXE. Браузер откроется сам.
4. При первом запуске войти под учётной записью менеджера.

Записи, отчёты, очередь облака и журнал лежат не во временной папке EXE, а в
`%LOCALAPPDATA%\BHS Neuro`. Обновление EXE поэтому не удаляет визиты.

Для автозапуска от текущего пользователя:

```powershell
.\BHS-Neuro.exe --install-autostart
```

Отключение автозапуска:

```powershell
.\BHS-Neuro.exe --remove-autostart
```

Проверка без прибора:

```powershell
.\BHS-Neuro.exe --fake
```

## Как получить EXE

PyInstaller собирает Windows-программу только на Windows. Есть два пути.

### GitHub Actions

В настройках репозитория создать secrets `SUPABASE_URL` и
`SUPABASE_ANON_KEY`, при необходимости variable `TEST_URL`. Затем открыть
Actions → **Windows EXE** → **Run workflow**. После тестов готовый файл будет
в artifact `BHS-Neuro-Windows-x64` вместе с SHA-256.

### Локальная сборка на Windows x64

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows.txt
.\.venv\Scripts\python.exe tools\build_windows.py
```

Результат: `dist\BHS-Neuro.exe`. Сборщик берёт настройки облака из `.env`
или из одноимённых переменных окружения и встраивает их внутрь файла.

## Диагностика

Журнал: `%LOCALAPPDATA%\BHS Neuro\logs\bridge.log`. Локальная проверка:
`http://127.0.0.1:8765/status`. Если Windows Defender впервые спрашивает о
доступе, внешний сетевой доступ не нужен: программа слушает только
`127.0.0.1`.
