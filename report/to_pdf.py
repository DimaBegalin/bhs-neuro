# -*- coding: utf-8 -*-
"""Печать отчёта в PDF тем же браузером, что показывает его на экране.

Почему не своей вёрсткой на reportlab: документ обязан совпадать с тем, что
родитель видел на экране, до колец и цветов. Любая вторая вёрстка неизбежно
разъедется с первой, и разбираться, почему в PDF другие числа, придётся
на встрече с семьёй. Chrome печатает ровно ту же страницу.

Печатные стили лежат в самом отчёте: они раскрывают все три вкладки
и сохраняют тёмный фон.
"""
import os
import shutil
import subprocess
import tempfile
import time

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
TIMEOUT_S = 40
POLL_S = 0.4


class BrowserNotFound(RuntimeError):
    pass


def find_browser() -> str:
    for path in CHROME_CANDIDATES:
        if os.path.exists(path):
            return path
    for name in ("google-chrome", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise BrowserNotFound("на этом ноутбуке нет Chrome, PDF печатать нечем")


def html_to_pdf(html_path: str, pdf_path: str) -> str:
    """Печатает файл отчёта в PDF. Возвращает путь к готовому файлу."""
    browser = find_browser()
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    # свой временный профиль обязателен: с профилем пользователя Chrome тянет
    # расширения и синхронизацию, печать идёт втрое дольше и спотыкается
    # об уже открытое окно
    with tempfile.TemporaryDirectory(prefix="bhs-print-") as profile:
        process = subprocess.Popen(
            [browser, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--no-default-browser-check",
             "--disable-extensions", "--disable-sync",
             "--disable-background-networking",
             f"--user-data-dir={profile}",
             # страница тянет шрифты со стороны: без бюджета времени Chrome
             # ждёт их до победного, а на визите интернета может не быть
             "--virtual-time-budget=8000",
             "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}",
             "file://" + os.path.abspath(html_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        # Ждём файл, а не браузер. Chrome печатает документ за несколько
        # секунд, но после этого не закрывается: на живом отчёте 14.08 он
        # висел до принудительного убийства, и кнопка ждала бы полминуты
        # вместо пяти секунд. Как только размер файла перестал расти,
        # документ готов и браузер больше не нужен.
        deadline = time.monotonic() + TIMEOUT_S
        size = -1
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            current = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
            if current > 0 and current == size:
                break
            size = current
            time.sleep(POLL_S)
        err = b""
        if process.poll() is None:
            process.kill()
        try:
            _, err = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
        tail = (err or b"").decode("utf-8", "replace")[-200:]
        raise RuntimeError("браузер не напечатал документ: " + tail)
    return pdf_path


if __name__ == "__main__":
    import sys
    print(html_to_pdf(sys.argv[1], sys.argv[2]))
