import pytest
from meridian.wrappers.cost import estimate_cost, COST_PER_1K_TOKENS


def test_known_model_zero_tokens():
    assert estimate_cost("gemini-1.5-flash", 0, 0) == 0.0


def test_known_model_input_only():
    # 1000 input tokens at $0.000075/1k = $0.000075
    cost = estimate_cost("gemini-1.5-flash", 1000, 0)
    assert abs(cost - 0.000075) < 1e-9


def test_known_model_output_only():
    # 1000 output tokens at $0.0003/1k = $0.0003
    cost = estimate_cost("gemini-1.5-flash", 0, 1000)
    assert abs(cost - 0.0003) < 1e-9


def test_known_model_combined():
    cost = estimate_cost("gemini-1.5-flash", 1000, 1000)
    expected = 0.000075 + 0.0003
    assert abs(cost - expected) < 1e-9


def test_unknown_model_returns_zero():
    assert estimate_cost("gpt-99-turbo", 5000, 5000) == 0.0


def test_model_with_prefix_stripped():
    # "models/gemini-1.5-flash" should resolve same as "gemini-1.5-flash"
    cost_prefixed = estimate_cost("models/gemini-1.5-flash", 1000, 1000)
    cost_plain = estimate_cost("gemini-1.5-flash", 1000, 1000)
    assert cost_prefixed == cost_plain


def test_pro_model_higher_than_flash():
    flash = estimate_cost("gemini-1.5-flash", 10_000, 10_000)
    pro = estimate_cost("gemini-1.5-pro", 10_000, 10_000)
    assert pro > flash


def test_all_known_models_return_positive():
    for model in COST_PER_1K_TOKENS:
        assert estimate_cost(model, 1000, 1000) > 0


def test_large_token_count():
    cost = estimate_cost("gemini-1.5-pro", 1_000_000, 500_000)
    assert cost > 0
    assert cost < 10_000  # sanity upper bound
