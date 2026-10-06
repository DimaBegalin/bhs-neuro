import pytest

from app.scoring.interests import TYPES, score_interests
from app.scoring.match import Occupation, pearson, rank
from app.scoring.tasks import score_tasks
from app.scoring.validity import card_shares, discrepancies, longest_run, validity_flags

ITEMS = [{"id": f"{t}{i}", "type": t} for t in TYPES for i in range(5)]


def answers(per_type: dict[str, int]) -> dict[str, int]:
    return {item["id"]: per_type[item["type"]] for item in ITEMS}


def test_scores_map_scale_to_0_100_and_detect_bright_profile():
    p = score_interests(ITEMS, answers({"R": 5, "I": 4, "A": 1, "S": 2, "E": 1, "C": 3}))
    assert p.scores == {"R": 100.0, "I": 75.0, "A": 0.0, "S": 25.0, "E": 0.0, "C": 50.0}
    assert p.level == "bright" and p.top(2) == ["R", "I"]


def test_flat_and_all_low_profiles_are_flat():
    assert score_interests(ITEMS, answers({t: 3 for t in TYPES})).level == "flat"
    low = score_interests(ITEMS, answers({"R": 2, "I": 2, "A": 1, "S": 1, "E": 1, "C": 1}))
    assert low.level == "flat"


def test_missing_answers_are_scored_by_answered_items():
    partial = {k: v for k, v in answers({t: 5 for t in TYPES}).items() if not k.startswith("R")}
    p = score_interests(ITEMS, partial)
    assert p.answered["R"] == 0 and p.expected["R"] == 5 and p.scores["I"] == 100.0


def test_out_of_scale_answer_is_rejected():
    with pytest.raises(ValueError):
        score_interests(ITEMS, {"R0": 6})


def test_pearson_ignores_generosity_of_ratings():
    shape = [1, 2, 3, 4, 5, 6]
    assert pearson(shape, [x + 30 for x in shape]) == pytest.approx(1.0)
    assert pearson([3] * 6, shape) is None


def test_rank_picks_clusters_by_their_closest_professions():
    occs = [
        Occupation("eng", {"ru": "Инженер"}, "engineering", (7, 6, 2, 2, 3, 4)),
        Occupation("mech", {"ru": "Механик"}, "engineering", (7, 4, 1, 2, 2, 3)),
        Occupation("teach", {"ru": "Учитель"}, "education", (2, 3, 4, 7, 4, 3)),
        Occupation("art", {"ru": "Дизайнер"}, "design", (3, 3, 7, 3, 4, 2)),
    ]
    result = rank([90, 70, 10, 15, 20, 40], occs, ["engineering", "education", "design"], top_clusters=2)
    assert result["top"][0] == "engineering"
    eng = result["clusters"][0]
    assert [p["id"] for p in eng["professions"]] == ["eng", "mech"]
    assert all(p["similarity"] >= 0.3 for c in result["clusters"] for p in c["professions"])


def test_task_levels_and_timeouts():
    trials = [{"item": i, "correct": i < 6, "rt_ms": 5000} for i in range(8)]
    assert score_tasks(trials)["level"] == "strong"
    trials = [{"item": i, "correct": None if i < 6 else False, "rt_ms": None} for i in range(8)]
    s = score_tasks(trials)
    assert s["level"] == "zone" and s["timeouts"] == 6


def choices(prefer: str, avoid: str) -> list[dict]:
    """Все 15 пар типов: prefer выбирают всегда, avoid — никогда, остальное — первый из пары."""
    import itertools
    out = []
    for a, b in itertools.combinations(TYPES, 2):
        chosen = prefer if prefer in (a, b) else (b if a == avoid else a)
        out.append({"types": [a, b], "chosen_type": chosen})
    return out


def test_card_shares_count_won_pairs():
    shares = card_shares(choices(prefer="A", avoid="R"))
    assert shares["A"] == 1.0 and shares["R"] == 0.0
    assert all(v is not None for v in shares.values())


def test_discrepancy_when_cards_contradict_questionnaire():
    p = score_interests(ITEMS, answers({"R": 5, "I": 4, "A": 1, "S": 2, "E": 1, "C": 3}))
    found = {d["type"]: d for d in discrepancies(p, choices(prefer="A", avoid="R"))}
    assert found["R"]["cards"] == "no" and found["A"]["cards"] == "yes"


def test_validity_flags():
    p = score_interests(ITEMS, answers({t: 3 for t in TYPES}))
    rows = [{"item": i["id"], "value": 3, "rt_ms": 400} for i in ITEMS]
    guessed = {"median_rt_ms": 1500, "share": 0.3, "chance": 0.25}
    careful = {"median_rt_ms": 9000, "share": 0.3, "chance": 0.25}
    assert set(validity_flags(rows, p, [], [careful, guessed])) == {"too_fast", "straightlining", "guessing"}
    assert "guessing" not in validity_flags(rows, p, [], [careful])
    assert longest_run([1, 1, 2, 2, 2, 1]) == 3


def test_task_keys_are_valid_and_hidden_from_window():
    from app import content
    for block in ("numeric", "verbal"):
        data = content.load(block)
        assert len(data["items"]) >= 10
        for item in data["items"]:
            for lang in ("ru", "kk"):
                options = item["options"][lang] if isinstance(item["options"], dict) else item["options"]
                assert len(options) == 4 and len(set(options)) == 4 and 0 <= item["answer"] < 4, item["id"]
                assert item["text"][lang], item["id"]
        shown = content.for_window("kk")[block]
        assert all("answer" not in i for i in shown["items"])
        assert shown["items"][0]["options"][0]["value"] == 0


def test_card_pairs_meet_every_type_once():
    import itertools
    from app import content
    types = content.card_types()
    met = sorted(tuple(sorted(types[c] for c in pair)) for pair in content.load("cards")["pairs"])
    assert met == sorted(tuple(sorted(p)) for p in itertools.combinations(TYPES, 2))


def test_bigfive_reverse_keys_and_stability():
    from app.scoring.bigfive import score_bigfive
    items = [{"id": "a", "scale": "C", "keyed": "+"}, {"id": "b", "scale": "C", "keyed": "-"},
             {"id": "n", "scale": "N", "keyed": "+"}]
    r = score_bigfive(items, {"a": 5, "b": 1, "n": 2})
    assert r["scores"]["C"] == 100.0 and r["scores"]["N"] == 25.0 and r["stability"] == 75.0
    assert r["scores"]["E"] is None


def test_flat_profile_has_no_discrepancies():
    p = score_interests(ITEMS, answers({t: 4 for t in TYPES}))
    assert p.level == "flat" and discrepancies(p, choices(prefer="E", avoid="R")) == []
