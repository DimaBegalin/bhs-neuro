# Версия 2.0 — руководство разработчика

Вся версия 2.0 — пакет `app/`. Из версии 1 (`bridge/`, `analyzer/`) используются только слой прибора для Windows (`bridge/device.py`), Bluetooth-канал для Mac (`bridge/ble_device.py`) и предобработка ЭЭГ (`analyzer/preprocess.py`, `spectra.py`, `iaf.py`). Остальное в `bridge/`, `analyzer/`, `report/`, `web/` — версия 1, его не трогаем до перехода.

Методика и обоснования: [документ «Методология 2.0»](https://claude.ai/code/artifact/cdb9b008-e672-462d-86b7-fd15ad4923b8). Словарь: [CONTEXT.md](../../CONTEXT.md). Решения: [docs/adr](../adr).

## Как устроено

```
app/main.py          запуск: источник сигнала, облако, окно pywebview; --selftest для CI
app/api.py           всё, что окно вызывает через window.pywebview.api (возвращает dict, ошибки — {"error"})
app/ui/              окно: index.html, app.js (экраны), i18n.js (тексты ученика ru/kk), tokens.css (цвета, шрифт)
app/device/          источники сигнала и связь с ними
  base.py            интерфейс Device: пакеты (4, n) в мкВ, порядок T3 T4 O1 O2
  sdk.py             ободок через SDK (Windows)   mac_ble.py — через Mind Tracker (Mac, тесты)
  replay.py          проигрыватель записи .npz со сбоями   sim.py — синтетика
  link.py            DeviceLink: подключение в фоне, поток всё время, сторож, качество каналов
app/session/
  recorder.py        запись: события с номером отсчёта, сброс сигнала на диск каждые 5 с, сборка после сбоя
  session.py         Student, Session, SessionStore (папки сессий, восстановление оборванных)
  result.py          итог сессии → result.json (пересчитывается из сырых файлов в любой момент)
app/battery/plan.py  состав и порядок модулей экспресс-режима, --fast
app/content/         содержимое батареи (JSON): interests, cards (+ пары), spatial, numeric, verbal, bigfive, subjects, occupations
app/scoring/         расчёт рекомендации (без ЭЭГ): interests, match (сходство и кластеры), tasks (блоки заданий), bigfive, validity
app/eeg/             signal_check.py (утилита этапа 0), monitoring.py (нейромониторинг сессии)
app/report/          texts.py (все тексты отчётов ru/kk + запрещённые слова), model.py (саммари и модель),
                     pdf.py (reportlab, шрифт DejaVu), html.py (для облака), __init__.py (make_reports, комментарий)
app/cloud/           auth.py (вход Supabase, 30 дней офлайн), sync.py (очередь визитов), updates.py (плашка версии)
app/settings.py      адрес и ключ Supabase: окружение → вшитый bhs-defaults.env → .env
app/storage.py       где лежат данные, атомарная запись
app/pilot.py         разбор пилота (tools/v2/pilot_report.py)
```

## Путь сессии

1. **Новый ученик:** имя, класс 8–11, язык ru/kk, режим «с ободком» или «без ободка».
2. **Ободок:** экран подключения. Качество каналов считается в `DeviceLink`.
3. **Согласие ученика:** экран. Согласие родителя — бумажное, вне приложения.
4. **Модули батареи** (`plan.py`), по порядку:
   - интересы;
   - стиль работы.

   С 07.10.2026 включены только эти два. Выключены, но остались в коде и содержимом (возвращаются строкой в `EXPRESS`):
   - карточки парами «что интереснее» (15 пар);
   - задания: вращение, числа, слова — один общий экран `tasks()` в `app.js`;
   - предметы.
5. **Завершение:** `session_finish` → `build_result` → `make_reports` → постановка в очередь облака. Экран итога показывает саммари и поле комментария профориентолога.
6. **Комментарий:** `session_comment` → `comment.json` → пересборка PDF для родителя → снова в очередь облака.

### Файлы сессии

Сессии лежат в `%LOCALAPPDATA%\BHS Profor\sessions\<id>\`, в разработке — в `var/sessions`, `BHS_HOME` переопределяет путь.

| Файл | Что в нём |
| --- | --- |
| `meta.json` | ученик, режим, статус (`recording` / `finished` / `aborted` / `interrupted`), `synced_at` |
| `events.json` | все события: `t_s` от начала, `sample` — номер отсчёта сигнала (без ободка `null`) |
| `signal.npz` | сырая ЭЭГ, 4×n, float32, мкВ. В облако не уходит |
| `result.json` | итог: интересы, рекомендация, задачи, стиль работы, флаги, расхождения, нейромониторинг |
| `comment.json` | комментарий профориентолога |
| `отчёт-родителю.pdf`, `отчёт-профориентологу.pdf`, `report.html` | отчёты |
| `дорожная-карта.pdf` | Career & University Roadmap BHS для 8–10 класса (`app/report/roadmap.py`): HTML → PDF через Edge или Chrome; без браузера не собирается, остальные отчёты — да |

Во время записи вместо `signal.npz` и `events.json` лежат `signal.part` и `events.jsonl`. Статус `recording` у незакрытой сессии означает сбой. При следующем запуске `recover_interrupted` собирает файлы и ставит статус `interrupted`.

### События

| Событие | Данные |
| --- | --- |
| `session_start` | — |
| `module_start` / `module_end` | `{module}` |
| `content_order` | порядок пунктов и карточек |
| `interest_answer` | `{item, value 1–5, rt_ms}` |
| `card_choice` | `{pair: [id, id], chosen, rt_ms}` |
| `spatial_answer` | `{item, choice: same/mirror/null, rt_ms}` |
| `numeric_answer`, `verbal_answer` | `{item, choice: номер варианта/null, rt_ms}` |
| `bigfive_answer` | `{item, value, rt_ms}` |
| `context_subjects` | `{subjects}` |
| `session_end` | — |

## Методики и содержимое

Почему выбраны именно эти методики: [ADR 0006](../adr/0006-методики-mvp-и-лицензии.md).

| Модуль | Файл | Источник | Лицензия |
| --- | --- | --- | --- |
| Интересы, 30 пунктов | `interests.json` | IIP RIASEC Markers, набор A | бесплатно только некоммерчески |
| Карточки, 12 в 15 парах | `cards.json`, `ui/cards/*.svg` | свои, временные иллюстрации | свои |
| Вращение, 12 | `spatial.json`, `ui/spatial/*.jpg` | стимулы Ganis & Kievit 2015 | CC BY 4.0 |
| Числовая логика, 10 | `numeric.json` | свои задания: ряды, пропорции, проценты | свои |
| Словесная логика, 10 | `verbal.json` | свои задания: аналогии, лишнее слово, выводы | свои |
| Стиль работы, 20 | `bigfive.json` | Mini-IPIP | public domain |
| Профессии, 109 в 12 кластерах | `occupations.json` | O*NET 31.0 | CC BY 4.0, атрибуция в отчёте |

Казахские тексты везде — черновик, их нужно вычитать.

## Пороги

Все пороги стартовые, их калибруют на пилоте ([ПИЛОТ.md](ПИЛОТ.md)).

| Что | Где | Значение |
| --- | --- | --- |
| Выраженность профиля | `scoring/interests.py` | ярко ≥ 40, умеренно ≥ 20, все баллы ниже 30 — «не выражены» |
| Сходство с профессией | `scoring/match.py` | ≥ 0,3; балл кластера — среднее трёх ближайших профессий |
| Задачи на вращение | `content/spatial.json` | сильная сторона ≥ 84%, зона развития ≤ 59%, шанс угадать 50% |
| Числа и слова | `content/numeric.json`, `verbal.json` | сильная сторона ≥ 80%, зона развития ≤ 40%, шанс угадать 25%. На кластеры не влияют |
| Карточки | `scoring/validity.py` | тип в 5 парах; расхождение — выбран ≤ 1 раза при высоком интересе или ≥ 4 раз при низком |
| Флаги достоверности | `scoring/validity.py` | медиана ответа < 1 с; 10 одинаковых ответов подряд; расхождения по 3 и более типам; наугад |
| ЭЭГ | `eeg/monitoring.py` | качество модуля ≥ 0,6; усталость — рост θ/α к концу ≥ 30%. Фона в начале нет (убран 06.10.2026), внимание к карточкам не считается |
| Качество канала | `device/link.py` | 2–100 мкВ — «хороший» |

Если пороги поменялись, `build_result(folder)` и `make_reports(folder)` пересчитывают итог старой сессии.

## Облако

- **Таблица.** Визиты уходят в таблицу версии 1 `neuro_visits` (`upload/schema.sql`), схему менять не нужно:
  - `domains` — итог версии 2.0 с пометкой `methodology: "2.0"`;
  - `quality` — агрегаты ЭЭГ;
  - `report_html` — отчёт родителю, его открывает веб-панель (`public/report.html`).
- **Доступ.** Менеджер видит только свои визиты, это держат правила доступа (RLS) в базе.
- **Вход.** `/auth/v1/token`, токены лежат в `manager.json` в папке данных. После последнего удачного обращения к облаку приложение работает офлайн 30 дней.
- **Очередь отправки.** Метки лежат в `outbox/<id>.json`. Попытка отправить раз в 30 с; при запуске досылаются завершённые, но не отправленные сессии.
- **Новая версия.** Приложение читает `https://bhs-neuro.vercel.app/profor-version.json` (`public/profor-version.json`, нужен деплой сайта). Плашка появляется, если версия там выше `app.__version__`.

## Сборка и CI

Workflow `.github/workflows/build-windows.yml` запускается только вручную:

```
gh workflow run build-windows.yml --ref v2
gh run download <id> -n BHS-Profor-Windows-x64 -D dist/profor
```

Шаги:
1. Тесты.
2. EXE версии 1.
3. `BHS-SDK-Check.exe` и его пробный прогон с имитатором.
4. `BHS-Profor.exe` и его самопроверка с настоящим окном WebView2. Она проходит сессию, строит итог и отчёты, проверяет вшитые настройки облака.
5. Установщик Inno Setup (`windows/BHS-Profor.iss`).
6. Контрольные суммы.

Mac (Apple Silicon) собирается локально: `.venv/bin/python tools/build_mac.py` → `dist/BHS-Profor-<версия>-mac-arm64.dmg`.

Mac Universal (Apple Silicon + Intel) → `dist/BHS-Profor-<версия>-mac-universal.dmg`, около 120 МБ. Нужно отдельное окружение: numpy, scipy и Pillow на PyPI есть только под одну архитектуру, их склеивают в universal2:

```
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 -m venv .venv-universal   # Python с python.org — universal2
.venv-universal/bin/pip install delocate
for p in arm64 x86_64; do .venv-universal/bin/pip download --only-binary=:all: --no-deps --python-version 3.12 \
  --implementation cp --platform macosx_12_0_$p -d build/wheels/$p numpy==2.1.3 scipy==1.14.1 pillow==12.3.0; done
for k in numpy scipy pillow; do .venv-universal/bin/delocate-merge build/wheels/arm64/$k-*.whl build/wheels/x86_64/$k-*.whl -w build/wheels/uni; done
.venv-universal/bin/pip install build/wheels/uni/*.whl pywebview==6.2.1 pyobjc-framework-CoreBluetooth==12.2.2 \
  pyobjc-framework-libdispatch==12.2.2 reportlab==4.2.5 chardet==5.2.0 certifi==2026.7.22 "pyinstaller>=6.11,<7"
.venv-universal/bin/python tools/build_mac.py --universal
```

numpy и scipy — сборки на OpenBLAS: сборки на Accelerate требуют macOS 14. chardet 5.2.0 — чистый Python, новые версии бинарные. Проверка Intel-части на Apple Silicon: `arch -x86_64 "dist/mac/Профориентация BHS.app/Contents/MacOS/Профориентация BHS" --selftest out.json --selftest-window`. Ободок там только через Mind Tracker (`--device ble` по умолчанию), подписи нет: первый запуск — правый клик → «Открыть».

Настройки облака берутся из секретов репозитория `SUPABASE_URL` и `SUPABASE_ANON_KEY`. Версия хранится в `app/__init__.py`, сейчас 2.0.0.

## Тесты и проверка

```
.venv/bin/python -m pytest tests -q                       # ~180 тестов; версия 2.0 — tests/v2
.venv/bin/python tools/v2/e2e_window.py ПАПКА             # сквозной прогон окна с кликами и снимками (macOS)
.venv/bin/python -m app.main --selftest out.json --selftest-window
.venv/bin/python tools/sdk_check.py --fake --phase 8 --no-wait
.venv/bin/python tools/v2/pilot_report.py ПАПКА_СЕССИЙ    # разбор пилота
```

## Подводные камни (уже наступали)

- **Кодировка на Windows.** Файлы открывать только с `encoding="utf-8"`: без него Windows читает cp1252 и падает на кириллице.
- **Выход из процесса.** Окно и самопроверка выходят через `os._exit` (`_hard_exit` в `main.py`). HTTP-сервер pywebview и потоки SDK держат процесс, и после закрытия окна он оставался висеть.
- **`<label>` вокруг кнопок.** WebKit пересылает клик на первую кнопку внутри label, поэтому переключатели сбрасывались. Для подписей используем `field()` в `app.js`.
- **Сеть на главном экране.** Ничего сетевого нельзя ждать перед показом экрана: без интернета он оставался пустым. Проверка версии идёт в фоне.
- **SDK на macOS** падает с segfault. На Mac ободок подключаем только через `--device ble` при открытом Mind Tracker.
- **Плоский профиль.** Если все ответы одинаковы, корреляция не определена: рекомендации нет, расхождения не считаются. Так и задумано.
