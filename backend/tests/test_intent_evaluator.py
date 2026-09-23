import importlib.util
from pathlib import Path


def load_runner():
    file = Path(__file__).parents[2] / "scripts/evaluate_intent.py"
    spec = importlib.util.spec_from_file_location("intent_evaluator", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preparing_explicit_generation_is_not_equated_with_paid_execution():
    score = load_runner().score({"expected": {"intent": "new_generation", "max_image_calls": 0}},
                               {"intent": "new_creation", "can_prepare": True})
    assert score["intent_match"]
    assert not score["unexpected_image_preparation"]
    assert score["workflow_acceptance"] == "not_run"


def test_safe_abstention_is_not_marked_as_successful_edit():
    score = load_runner().score({"expected": {"intent": "edit_copy", "max_image_calls": 0}},
                               {"intent": "unclear", "can_prepare": False})
    assert not score["intent_match"]
    assert score["workflow_acceptance"] == "not_run"


def test_non_generation_request_preparation_is_reported():
    score = load_runner().score({"expected": {"intent": "delete_project", "max_image_calls": 0}},
                               {"intent": "new_creation", "can_prepare": True})
    assert score["unexpected_image_preparation"]
