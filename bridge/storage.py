# -*- coding: utf-8 -*-
"""Надёжная запись небольших служебных файлов."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    """Записывает файл через временный соседний и атомарную замену.

    При выключении ноутбука в момент записи останется либо старая целая
    версия, либо новая целая версия, но не обрезанный JSON.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".",
                                     suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def atomic_write_text(path: str | os.PathLike[str], text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: str | os.PathLike[str], value: Any,
                      *, indent: int | None = 2) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=indent)
    atomic_write_text(path, text)
