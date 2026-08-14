# Файлы шрифта Halvar Breitschrift

Сюда кладём webfont-файлы Halvar от TypeMates. Имена важны, они прописаны в `build.py`
и в каждом превью:

| Файл | Начертание | Где используется |
| --- | --- | --- |
| `HalvarBreit-Rg` | Regular 400 | основной текст, абзацы |
| `HalvarBreit-Md` | Medium 500 | подписи, caption, номера шагов |
| `HalvarBreit-Bd` | Bold 700 (и 600) | заголовки, цифры, кнопки, подзаголовки |
| `HalvarBreit-Blk` | Black 900 | крупные цифры на крео |
| `HalvarBreit-RgSlanted` | Regular Slanted | курсив, технические подписи |

Каждое начертание лежит в двух форматах: `.woff2` основной, `.woff` резервный.
Полный набор из 28 стилей Breitschrift (Hairline, ExtraThin, Thin, Light, Regular, Medium,
Bold, ExtraBold, Black плюс Slanted и SuperSlanted) хранится отдельно, здесь только рабочие веса.

Для макетов в Figma нужны десктопные `.otf` или `.ttf`, они ставятся в систему,
а не в эту папку.
