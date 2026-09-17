import pytest

from jev_agent_browser.policy import action_space, validate_choice


def test_action_space_indexes_elements_and_operations():
    actions = [
        {"id": "e1", "node": 7, "kind": "fill", "role": "textbox", "label": "Origin", "value": ""},
        {"id": "e2", "node": 7, "kind": "click", "role": "textbox", "label": "Open Origin", "value": ""},
        {"id": "e3", "node": 9, "kind": "click", "role": "button", "label": "Search", "value": ""},
        {"id": "wait", "kind": "wait", "label": "Wait"},
    ]

    elements, targets, controls = action_space(actions)

    assert elements == [
        {"role": "textbox", "value": "", "index": "1", "label": "Origin", "operations": ["TYPE_TEXT", "CLICK"]},
        {"role": "button", "value": "", "index": "2", "label": "Search", "operations": ["CLICK"]},
    ]
    assert targets["TYPE_TEXT"]["1"]["id"] == "e1"
    assert targets["CLICK"]["1"]["id"] == "e2"
    assert targets["CLICK"]["2"]["id"] == "e3"
    assert controls["WAIT"]["id"] == "wait"


def test_validate_choice_rejects_incomplete_probability_space():
    with pytest.raises(ValueError, match="Invalid TypeSafe response"):
        validate_choice({"choice": "CLICK", "confidence": 1, "probabilities": {"CLICK": 1}}, {"CLICK": 1, "DONE": 1})
