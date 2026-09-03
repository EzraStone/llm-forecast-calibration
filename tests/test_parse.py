"""Tests for the parser (spec section 8): valid JSON, fenced JSON, percentage,
out-of-range, empty response."""
import pytest

from src.parse import parse_content


def test_valid_json():
    assert parse_content('{"probability": 0.62}') == 0.62


def test_fenced_json():
    assert parse_content('```json\n{"probability": 0.5}\n```') == 0.5


def test_unfenced_block():
    assert parse_content('```\n{"probability": 0.42}\n```') == 0.42


def test_json_in_prose():
    assert parse_content('My forecast: {"probability": 0.77} hope this helps') == 0.77


def test_percentage():
    assert parse_content("I'd say 62% likely YES.") == 0.62
    assert parse_content('{"probability": "62%"}') == 0.62


def test_out_of_range_rejected():
    with pytest.raises(ValueError):
        parse_content('{"probability": 1.5}')
    with pytest.raises(ValueError):
        parse_content('{"probability": -0.1}')


def test_empty_response():
    with pytest.raises(ValueError):
        parse_content("")
    with pytest.raises(ValueError):
        parse_content(None)


def test_no_probability_key():
    with pytest.raises(ValueError):
        parse_content('{"reference_class": "x", "base_rate": "y"}')
