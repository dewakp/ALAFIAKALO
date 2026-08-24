"""The AI timeout ladder must stay ordered, and no two rungs may be equal.

CLAUDE.md §3ae and §5. The rule keeps being re-learned in a new place, so it is
pinned here as a check rather than a paragraph.

Most recent instance: background nutrient enrichment wrapped the whole estimate
in `asyncio.wait_for(..., 120.0)` — hardcoded — while production ran
OLLAMA_TIMEOUT=290. The OUTER rung was shorter than the inner one, so Ollama's
own limit could never fire, and every meal that needed the AI fallback died at
exactly 120 s. Two production meals show it to the second:

    log 1002  created 01:23:07  ->  "Nutrient enrichment timed out"  01:25:07
    log 1003  created 08:34:26  ->  "Nutrient enrichment timed out"  08:36:26

The user saw "unavailable" and had no way to know a clock had run out.
"""

from app.core.config import settings

# §5: a COLD Ollama call pays a model load (~77 s) before generating (up to
# ~172 s). Any rung that waits on it must clear roughly this.
COLD_OLLAMA_PATH_SECONDS = 250


def test_enrichment_outlasts_the_model_call_it_wraps():
    assert settings.NUTRIENT_ENRICHMENT_TIMEOUT > settings.OLLAMA_TIMEOUT, (
        "The wrapper must not kill the call it is waiting on — otherwise the "
        "inner timeout is unreachable and its error message never appears."
    )


def test_enrichment_clears_a_cold_model_load():
    assert settings.NUTRIENT_ENRICHMENT_TIMEOUT >= COLD_OLLAMA_PATH_SECONDS, (
        "alafia-ollama scales to zero by design (§5), so the FIRST request of "
        "the day pays a ~77 s model load on top of generation."
    )


def test_no_two_rungs_are_equal():
    """Equal rungs mean two limits can fire together and neither is diagnostic."""
    rungs = {
        "OLLAMA_TIMEOUT": settings.OLLAMA_TIMEOUT,
        "NUTRIENT_ENRICHMENT_TIMEOUT": settings.NUTRIENT_ENRICHMENT_TIMEOUT,
    }
    assert len(set(rungs.values())) == len(rungs), f"equal rungs: {rungs}"


def test_the_rung_is_configurable_not_hardcoded():
    """It drifted from the ladder precisely because it was a module constant."""
    from app.services import nutrient_enrichment

    original = settings.NUTRIENT_ENRICHMENT_TIMEOUT
    try:
        object.__setattr__(settings, "NUTRIENT_ENRICHMENT_TIMEOUT", 999)
        assert nutrient_enrichment._enrichment_timeout() == 999.0
    finally:
        object.__setattr__(settings, "NUTRIENT_ENRICHMENT_TIMEOUT", original)
