# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

""""Today" belongs to the patient, not to the container.

The containers run UTC, so `date.today()` answers with the SERVER's date — and
from early evening in the Americas that is already tomorrow for the patient.
§3am found this live at 20:54 on 2026-09-05: the AI tool queried 2026-09-06,
found nothing, and told a patient holding six logged meals and 58.4 g of sugar
that they had eaten nothing that day. Cloud Run is UTC too, so it fired in
production every evening.

That was fixed for the AI and tool path. It left ~14 other `date.today()` call
sites that mean "today" exactly, and these are the ones where a day's shift
changes what the patient sees or what is written to their record:

    wellness.py        score_date on the STORED WellnessScoreModel row
    wellness.py        the daily recommendations' own date
    planners.py        day 1 of a meal plan
    planners.py        day 1 of an exercise plan
    personalization.py log_date on a SymptomLog — a clinical write

Deliberately NOT changed, and the reasons are worth keeping:

* `wellness.py` line ~64 — `today` there only feeds `today - timedelta(days=30)`.
  Shifting a 30-day window by a day changes nothing anyone can see.
* 24 other sites are the same shape: a cutoff, not a date.
* `age_policy` / `users` / `ai` age arithmetic — a day's shift moves an age by
  at most a day, and only on a birthday.
* `fda_recalls` — the end of an FDA query range, not a patient's day.
* `patient_board._stale_note` — produces "Logged today" vs "last logged 1 day
  ago" for a CLINICIAN reading about a patient, so whose "today" it should use
  is a real question rather than an obvious fix; and reaching it would mean
  threading a date through every summary function in that service. Left, with
  this note, rather than changed on a guess (§3ap).
"""

import ast
import re
from datetime import date
from pathlib import Path

import pytest

API = Path(__file__).resolve().parent.parent / "app" / "api"

#: endpoint -> module. Each computes a date the PATIENT sees or owns.
_MUST_BE_PATIENT_DATED = {
    "get_wellness_score": "wellness.py",
    "get_daily_recommendations": "wellness.py",
    # Added 2026-10-11 when /wellness/trends moved onto `collect_signals`: its
    # window is anchored on the patient's today, so on the server's UTC date an
    # evening in the Americas would ask for a window ending tomorrow and lose
    # the day just logged from the near end of every stream.
    "get_health_trends": "wellness.py",
    "generate_meal_plan": "planners.py",
    "generate_exercise_plan": "planners.py",
    "analyze_symptoms": "personalization.py",
}


def _function(module: str, name: str) -> ast.AST:
    tree = ast.parse((API / module).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in {module} — was it renamed?")


@pytest.mark.parametrize("name,module", sorted(_MUST_BE_PATIENT_DATED.items()))
def test_the_endpoint_accepts_the_client_timezone_header(name, module):
    """A patient's date cannot be derived without their zone.

    `users.timezone` is NULL for 83 of 85 production users and one of the two
    that are set reads `America/New York`, which is not a valid IANA name — so
    the stored value cannot be the only source. The header is what the clients
    actually send on every request.
    """
    src = ast.unparse(_function(module, name))
    assert "TIMEZONE_HEADER" in src, (
        f"{module}:{name} computes a patient-facing date but never accepts "
        "X-Client-Timezone")


@pytest.mark.parametrize("name,module", sorted(_MUST_BE_PATIENT_DATED.items()))
def test_the_endpoint_does_not_read_the_servers_clock(name, module):
    """`date.today()` inside one of these is the bug, by definition."""
    src = ast.unparse(_function(module, name))
    assert not re.search(r"\bdate\.today\(\)", src), (
        f"{module}:{name} still reads the SERVER's date; use "
        "patient_today(client_timezone, current_user.timezone)")


def test_a_symptom_is_filed_on_the_date_it_is_given():
    """The clinical write, asserted behaviourally rather than by reading code.

    `_record_symptom_analysis` used to call `date.today()` itself, so a symptom
    described on Tuesday evening in New York was filed under Wednesday. A
    helper handed no date cannot know the patient's one, so it now takes it.
    """
    from app.api.personalization import _record_symptom_analysis

    added = []

    class _DB:
        def add(self, obj): added.append(obj)
        def commit(self): pass
        def refresh(self, obj): setattr(obj, "id", 1)

    class _User:
        id = 63

    patient_day = date(2026, 9, 5)          # 20:54 in New York …
    server_day = date(2026, 9, 6)           # … is already the 6th in UTC

    out = _record_symptom_analysis(
        _DB(), _User(), "dizzy, weak", {"analysis": "x"}, patient_day)

    logs = [o for o in added if hasattr(o, "log_date")]
    assert logs, "no SymptomLog was written"
    assert all(o.log_date == patient_day for o in logs)
    assert not any(o.log_date == server_day for o in logs)
    assert out["symptoms_logged"] == len(logs) == 2


def test_patient_today_still_resolves_the_way_the_ai_path_pinned_it():
    """The helper itself, re-asserted here so a change to it fails beside the
    endpoints that now depend on it rather than only in the AI tests."""
    from datetime import datetime
    from datetime import timezone as tz
    from unittest.mock import patch

    from app.core.patient_time import patient_today

    utc_now = datetime(2026, 9, 6, 0, 54, tzinfo=tz.utc)   # 20:54 on the 5th in NY
    with patch("app.core.patient_time.datetime") as fake:
        fake.now.return_value = utc_now
        assert str(patient_today("America/New_York")) == "2026-09-05"
        assert str(patient_today(None)) == "2026-09-06", "UTC remains the fallback"
