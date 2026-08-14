from analyzer.wording import describe_domain, describe_profile, FORBIDDEN

STRONG = {"domain": "spatial", "accuracy": 0.95, "median_rt_ms": 900.0,
          "cost": -1.1, "efficiency": 1.8, "attention_slope": -0.002}
COSTLY = {"domain": "verbal", "accuracy": 0.55, "median_rt_ms": 1600.0,
          "cost": 1.2, "efficiency": -1.7, "attention_slope": -0.05}


def test_strong_domain_reads_as_strength():
    text = describe_domain(STRONG)
    assert "сильн" in text["verdict"].lower()
    assert "95" in text["detail"]


def test_costly_domain_names_the_price():
    text = describe_domain(COSTLY)
    assert "дорог" in text["verdict"].lower() or "усили" in text["verdict"].lower()


def test_kazakh_variant_exists():
    text = describe_domain(STRONG, lang="kk")
    assert text["title"] and text["verdict"]
    assert text != describe_domain(STRONG, lang="ru")


def test_no_forbidden_words_anywhere():
    profile = {"has_eeg": True, "iaf": 10.2, "domains": [STRONG, COSTLY],
               "quality": {"reasons": []}}
    blob = " ".join(str(v) for v in describe_profile(profile).values()).lower()
    for word in FORBIDDEN:
        assert word.lower() not in blob


def test_profile_without_eeg_says_so_plainly():
    profile = {"has_eeg": False, "iaf": None,
               "domains": [dict(STRONG, cost=None, efficiency=None)],
               "quality": {"reasons": ["альфа-пик не выделен, нейро-слой не считается"]}}
    text = describe_profile(profile)
    assert "сигнал" in text["disclaimer"].lower()
    assert text["strong"]


def test_attention_line_names_the_worst_block():
    profile = {"has_eeg": True, "iaf": 10.2, "domains": [STRONG, COSTLY],
               "quality": {"reasons": []}}
    assert "Слова и смыслы" in describe_profile(profile)["attention"]
