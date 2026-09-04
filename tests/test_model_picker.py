"""Smoke: model picker sorting."""

from pico_tui.model_picker import sort_models


def _m(id: str, name: str, is_free: bool) -> dict:
    return {"id": id, "name": name, "is_free": is_free}


def test_sort_models_free_first_then_alphabetical():
    models = [
        _m("z/paid", "Zeta Paid", False),
        _m("b/free", "Beta Free", True),
        _m("a/paid", "Alpha Paid", False),
        _m("a/free", "Alpha Free", True),
    ]
    result = sort_models(models)
    assert [m["id"] for m in result] == ["a/free", "b/free", "a/paid", "z/paid"]
