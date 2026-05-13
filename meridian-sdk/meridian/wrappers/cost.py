from __future__ import annotations

# USD per 1 000 tokens (input, output)
COST_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "gemini-1.5-pro":               (0.00125,  0.005),
    "gemini-1.5-pro-latest":        (0.00125,  0.005),
    "gemini-1.5-flash":             (0.000075, 0.0003),
    "gemini-1.5-flash-latest":      (0.000075, 0.0003),
    "gemini-2.0-flash":             (0.000075, 0.0003),
    "gemini-2.0-flash-lite":        (0.000037, 0.00015),
    "gemini-2.5-pro":               (0.00125,  0.010),
    "gemini-2.5-flash":             (0.000075, 0.0003),
    "gemini-2.5-flash-lite":        (0.000037, 0.00015),
    "gemini-3.0-flash":             (0.000075, 0.0003),
    "gemini-3.0-flash-lite":        (0.000037, 0.00015),
    "gemini-3.1-flash":             (0.000075, 0.0003),
    "gemini-3.1-flash-lite":        (0.000037, 0.00015),
    "gemini-3.1-flash-lite-preview":(0.000037, 0.00015),
    "gemini-pro":                   (0.0005,   0.0015),
}

# Prefix fallback order: most specific first
_FALLBACK_PREFIXES: list[tuple[str, tuple[float, float]]] = [
    ("gemini-2.5-pro",   (0.00125,  0.010)),
    ("gemini-2.5-flash", (0.000075, 0.0003)),
    ("gemini-2.0-flash", (0.000075, 0.0003)),
    ("gemini-1.5-pro",   (0.00125,  0.005)),
    ("gemini-1.5-flash", (0.000075, 0.0003)),
    ("gemini",           (0.000075, 0.0003)),   # generic Gemini fallback
    ("gpt-4",            (0.01,     0.03)),
    ("gpt-3",            (0.001,    0.002)),
    ("claude",           (0.003,    0.015)),
]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = model.lower().split("/")[-1]  # strip "models/" prefix if present
    # Strip "-preview", "-exp", "-latest" suffixes for lookup
    bare = key.replace("-preview", "").replace("-exp", "").replace("-latest", "").rstrip("-")

    rates = COST_PER_1K_TOKENS.get(key) or COST_PER_1K_TOKENS.get(bare)
    if rates is None:
        for prefix, fallback_rates in _FALLBACK_PREFIXES:
            if key.startswith(prefix) or bare.startswith(prefix):
                rates = fallback_rates
                break
    if rates is None:
        return 0.0
    return round((input_tokens / 1000) * rates[0] + (output_tokens / 1000) * rates[1], 8)
