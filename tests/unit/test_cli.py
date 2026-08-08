from linkedinbot.cli import _deep_merge


def test_deep_merge_overrides_leaf_value():
    base = {"a": 1, "b": 2}
    overrides = {"b": 20}

    assert _deep_merge(base, overrides) == {"a": 1, "b": 20}


def test_deep_merge_recurses_into_nested_dicts_preserving_sibling_keys():
    # M1.4 seed script'inin tam olarak dayandigi davranis: target_criteria
    # icindeki "locations" ezilirken "departments"/"experience_levels"
    # sistem varsayilanindan korunmalidir.
    base = {
        "target_criteria": {
            "locations": ["Istanbul"],
            "departments": {"Sales": ["Sales Executive"]},
            "experience_levels": ["Entry Level"],
        }
    }
    overrides = {
        "target_criteria": {
            "locations": ["Istanbul"],
            "workplace_types": ["On-site", "Hybrid"],
        }
    }

    merged = _deep_merge(base, overrides)

    assert merged["target_criteria"]["locations"] == ["Istanbul"]
    assert merged["target_criteria"]["workplace_types"] == ["On-site", "Hybrid"]
    assert merged["target_criteria"]["departments"] == {"Sales": ["Sales Executive"]}
    assert merged["target_criteria"]["experience_levels"] == ["Entry Level"]


def test_deep_merge_does_not_mutate_base():
    base = {"a": {"x": 1}}
    overrides = {"a": {"y": 2}}

    _deep_merge(base, overrides)

    assert base == {"a": {"x": 1}}


def test_deep_merge_non_dict_override_replaces_dict_wholesale():
    # Bir taraf dict, diger taraf degilse recursive birlestirme yapilmaz -
    # overrides'taki deger oldugu gibi kazanir.
    base = {"a": {"x": 1}}
    overrides = {"a": "replaced"}

    assert _deep_merge(base, overrides) == {"a": "replaced"}
