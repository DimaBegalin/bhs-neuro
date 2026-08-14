"""Банк задач проверяется питоном, чтобы ошибки ловились до визита."""
import json
import re
from pathlib import Path

BLOCKS_JS = Path(__file__).resolve().parents[1] / "web" / "assets" / "blocks.js"
I18N_JS = Path(__file__).resolve().parents[1] / "web" / "assets" / "i18n.js"
FIXED_DOMAINS = ("numeric", "verbal")
GENERATED_DOMAINS = ("spatial", "working_memory")
FORBIDDEN = ["диагноз", "обследование", "сканирование мозга", "МРТ", "IQ"]


def load_blocks() -> dict:
    text = BLOCKS_JS.read_text(encoding="utf-8")
    return json.loads(re.search(r"const BHS_BLOCKS = (\{.*\});", text, re.S).group(1))


def test_all_four_domains_present():
    blocks = load_blocks()
    assert set(blocks) == set(FIXED_DOMAINS) | set(GENERATED_DOMAINS)


def test_fixed_domains_have_enough_items():
    blocks = load_blocks()
    assert len(blocks["numeric"]) >= 16
    assert len(blocks["verbal"]) >= 18


def test_generated_domains_declare_generator_and_count():
    blocks = load_blocks()
    assert blocks["spatial"]["generator"] == "rotation"
    assert blocks["spatial"]["count"] >= 12
    assert blocks["working_memory"]["generator"] == "nback"
    assert blocks["working_memory"]["count"] >= 20


def test_every_fixed_item_is_bilingual_and_well_formed():
    blocks = load_blocks()
    for domain in FIXED_DOMAINS:
        ids = set()
        for item in blocks[domain]:
            assert item["id"] not in ids, f"дубль id {item['id']}"
            ids.add(item["id"])
            assert len(item["options_ru"]) == len(item["options_kk"]) >= 3
            assert 0 <= item["correct"] < len(item["options_ru"])
            assert item["prompt_ru"] and item["prompt_kk"]
            assert item["prompt_ru"] != item["prompt_kk"], f"нет перевода у {item['id']}"


def test_no_forbidden_words_and_no_em_dash():
    for path in (BLOCKS_JS, I18N_JS):
        text = path.read_text(encoding="utf-8")
        for word in FORBIDDEN:
            assert word.lower() not in text.lower(), f"стоп-слово в {path.name}: {word}"
        assert "—" not in text, f"длинное тире в {path.name}"


def test_i18n_has_both_languages_with_same_keys():
    text = I18N_JS.read_text(encoding="utf-8")
    data = json.loads(re.search(r"const BHS_I18N = (\{.*\});", text, re.S).group(1))
    assert set(data) == {"ru", "kk"}
    assert set(data["ru"]) == set(data["kk"])
    assert all(v for v in data["ru"].values())
    assert all(v for v in data["kk"].values())
