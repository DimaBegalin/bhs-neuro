# -*- coding: utf-8 -*-
"""Печать отчёта в PDF и кнопка, которая её запускает."""
import os

import pytest

from report import to_pdf


def test_browser_absence_is_named_plainly(monkeypatch):
    """Без браузера печатать нечем, и сказать это надо понятно.

    Мост показывает эту причину менеджеру на экране, поэтому она не должна
    быть похожа на след от падения.
    """
    monkeypatch.setattr(to_pdf, "CHROME_CANDIDATES", ())
    monkeypatch.setattr(to_pdf.shutil, "which", lambda name: None)
    with pytest.raises(to_pdf.BrowserNotFound) as error:
        to_pdf.find_browser()
    assert "Chrome" in str(error.value)


def test_printing_does_not_wait_for_a_hung_browser(monkeypatch, tmp_path):
    """Chrome печатает документ, а закрыться забывает.

    Живая проверка 14.08: файл готов за пять секунд, а браузер висел до
    принудительного убийства. Ждать надо файл, иначе кнопка «Скачать PDF»
    молчит полминуты.
    """
    pdf_path = tmp_path / "готовый.pdf"

    class HangingBrowser:
        """Пишет файл сразу, но не завершается никогда."""
        def __init__(self, *args, **kwargs):
            pdf_path.write_bytes(b"%PDF-1.4 test")
            self.killed = False

        def poll(self):
            return None if not self.killed else 0

        def kill(self):
            self.killed = True

        def communicate(self, timeout=None):
            return b"", b""

    monkeypatch.setattr(to_pdf, "find_browser", lambda: "/bin/echo")
    monkeypatch.setattr(to_pdf.subprocess, "Popen", HangingBrowser)
    monkeypatch.setattr(to_pdf, "POLL_S", 0.01)
    monkeypatch.setattr(to_pdf, "TIMEOUT_S", 3)

    result = to_pdf.html_to_pdf(str(tmp_path / "нет.html"), str(pdf_path))
    assert os.path.exists(result)


def test_empty_result_is_reported_as_failure(monkeypatch, tmp_path):
    """Пустой файл нельзя отдать семье вместо документа."""
    pdf_path = tmp_path / "пусто.pdf"

    class SilentBrowser:
        def __init__(self, *args, **kwargs):
            pass

        def poll(self):
            return 0

        def kill(self):
            pass

        def communicate(self, timeout=None):
            return b"", "chrome: не смог".encode()

    monkeypatch.setattr(to_pdf, "find_browser", lambda: "/bin/echo")
    monkeypatch.setattr(to_pdf.subprocess, "Popen", SilentBrowser)
    monkeypatch.setattr(to_pdf, "POLL_S", 0.01)
    monkeypatch.setattr(to_pdf, "TIMEOUT_S", 1)

    with pytest.raises(RuntimeError):
        to_pdf.html_to_pdf(str(tmp_path / "нет.html"), str(pdf_path))
