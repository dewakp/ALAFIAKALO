# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A treatment that ends after midnight ends on the NEXT day.

Reported from the data, not a screen: 4 of 22 live-app sessions carrying both
clock ends store the end BEFORE the start — ids 2745, 2749, 2750, 2755, created
2026-08-27 through 2026-09-16.

    id 2745  2026-08-26  22:10 -> 02:15 stored on 2026-08-26   = -1195 min
    id 2749  2026-09-03  20:43 -> 00:50 stored on 2026-09-03   = -1193 min
    id 2750  2026-09-05  21:03 -> 00:50 stored on 2026-09-05   = -1213 min
    id 2755  2026-09-15  22:45 -> 03:40 stored on 2026-09-15   = -1145 min

Each rolls to 245, 247, 227 and 295 minutes — against a stored median of 227.
So the times the patient typed are right; the app discarded the day.

WHY NO CLIENT GOT THIS RIGHT
============================
All three compose the stored timestamp by stamping the session's date onto one
clock at a time:

    Hemodialysis.jsx        next[f] = `${day}T${clock}:00`     (both fields)
    HemodialysisView.swift  Self.iso(day: String(day), clock: endClock)
    HemodialysisScreen.kt   isoAt(date, endTime)

A helper handed ONE time cannot know it belongs to the next day — that is only
visible from the PAIR. So this is not a platform that got it wrong beside two
that got it right (§3av): there is no correct client to copy, which is why the
rule belongs where both values are in hand.

`_naive_session_payload` is that place. It already loops over
`actual_start_time` / `actual_end_time` / `scheduled_date`, and it has exactly
two callers — create (line 456) and update (line 574) — with exactly one
`TherapySession(` constructor in the app. Fixing it there covers every shipped
client at once, including the TestFlight build and the distributed APK, which
cannot be updated by changing their source.

> The web form ALREADY rolls over for display: `minutesBetween` does
> `if (mins < 0) mins += 24 * 60`, and its docstring says "a treatment that
> starts 21:00 and ends 01:00 runs four hours, not minus twenty". So the
> duration shown was right while the duration stored was negative — two
> computations of one interval disagreeing, which §3ai names and which the
> comment above `clockMinutes` in that same file already cites.

WHAT THIS DELIBERATELY DOES NOT DO
==================================
Only a SAME-DATE inversion is rolled. Three production rows have an end dated
days before their start (ids 4, 11, 13 — gaps of 7, 3 and 1 days, all from the
2026-06-04 import), and adding 24 hours would not repair those; they are a
different fault and are reported for a person. An end already stamped on a
later date is left exactly as it is.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.api.chronic_conditions import _naive_session_payload


class TestOvernightRollover:
    def test_an_end_before_the_start_on_the_SAME_date_moves_to_the_next_day(self):
        """id 2745's shape: 22:10 -> 02:15, both stamped 2026-08-26."""
        out = _naive_session_payload({
            "scheduled_date": datetime(2026, 8, 26, 0, 0),
            "actual_start_time": datetime(2026, 8, 26, 22, 10),
            "actual_end_time": datetime(2026, 8, 26, 2, 15),
        })
        assert out["actual_end_time"] == datetime(2026, 8, 27, 2, 15)
        minutes = (out["actual_end_time"]
                   - out["actual_start_time"]).total_seconds() / 60
        assert minutes == 245, "a real treatment length, not -1195"

    def test_every_one_of_the_four_production_rows_becomes_plausible(self):
        rows = [
            (datetime(2026, 8, 26, 22, 10), datetime(2026, 8, 26, 2, 15), 245),
            (datetime(2026, 9, 3, 20, 43), datetime(2026, 9, 3, 0, 50), 247),
            (datetime(2026, 9, 5, 21, 3), datetime(2026, 9, 5, 0, 50), 227),
            (datetime(2026, 9, 15, 22, 45), datetime(2026, 9, 15, 3, 40), 295),
        ]
        for start, end, expected in rows:
            out = _naive_session_payload({
                "actual_start_time": start, "actual_end_time": end,
            })
            got = (out["actual_end_time"] - start).total_seconds() / 60
            assert got == expected, f"{start} -> {end}"
            assert 60 <= got <= 600, "inside a plausible treatment length"

    def test_an_ordinary_daytime_session_is_untouched(self):
        out = _naive_session_payload({
            "actual_start_time": datetime(2025, 6, 6, 16, 50),
            "actual_end_time": datetime(2025, 6, 6, 20, 55),
        })
        assert out["actual_end_time"] == datetime(2025, 6, 6, 20, 55)

    def test_an_end_ALREADY_on_the_next_date_is_untouched(self):
        """Not double-rolled. The backfill writes this shape directly."""
        out = _naive_session_payload({
            "actual_start_time": datetime(2018, 5, 6, 23, 35),
            "actual_end_time": datetime(2018, 5, 7, 2, 4),
        })
        assert out["actual_end_time"] == datetime(2018, 5, 7, 2, 4)

    def test_an_end_dated_DAYS_before_the_start_is_left_alone(self):
        """ids 4, 11 and 13 — gaps of 7, 3 and 1 days. Adding 24 hours would
        not repair them, and a backfill that half-fixed a corrupt row would
        hide it. They are reported for a person instead."""
        out = _naive_session_payload({
            "actual_start_time": datetime(2025, 7, 13, 7, 3),
            "actual_end_time": datetime(2025, 7, 6, 11, 30),
        })
        assert out["actual_end_time"] == datetime(2025, 7, 6, 11, 30)

    def test_an_end_with_no_start_in_the_payload_uses_the_STORED_start(self):
        """The update path sends `exclude_unset=True`, so editing only the end
        time arrives WITHOUT the start — and the rule cannot see the pair.
        Fixing create and leaving this is the half-wiring this file's own
        neighbour warns about (`session_drugs`, ten months behind)."""
        out = _naive_session_payload(
            {"actual_end_time": datetime(2026, 9, 3, 0, 50)},
            stored_start=datetime(2026, 9, 3, 20, 43),
        )
        assert out["actual_end_time"] == datetime(2026, 9, 4, 0, 50)

    def test_an_end_with_no_start_ANYWHERE_is_left_alone(self):
        """Unknown is not the same as wrong. With no start there is nothing to
        compare against, and inventing a day would be a guess (§0)."""
        out = _naive_session_payload({"actual_end_time": datetime(2026, 9, 3, 0, 50)})
        assert out["actual_end_time"] == datetime(2026, 9, 3, 0, 50)

    def test_a_payload_with_no_times_at_all_is_unchanged(self):
        out = _naive_session_payload({"pre_dialysis_weight_kg": 57.5})
        assert out == {"pre_dialysis_weight_kg": 57.5}

    def test_a_start_with_no_end_is_unchanged(self):
        out = _naive_session_payload({
            "actual_start_time": datetime(2025, 7, 6, 6, 0)})
        assert out["actual_start_time"] == datetime(2025, 7, 6, 6, 0)
        assert "actual_end_time" not in out


class TestNaiveNormalisationStillHolds:
    """The rollover must not break what this function already did.

    §3aa: these columns are `DateTime` WITHOUT timezone, and a browser sends an
    instant. Comparing aware to naive makes asyncpg raise DataError, the
    endpoint 500s, and the page renders it as "No hemodialysis sessions found"
    on a patient with 730 sessions.
    """

    def test_an_aware_datetime_is_still_made_naive(self):
        out = _naive_session_payload({
            "scheduled_date": datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc),
            "actual_start_time": datetime(2026, 8, 26, 22, 10, tzinfo=timezone.utc),
        })
        assert out["scheduled_date"].tzinfo is None
        assert out["actual_start_time"].tzinfo is None

    def test_the_rollover_works_on_AWARE_input_too(self):
        """Both values arrive with a Z from a browser. If the rollover ran
        before normalisation it would compare aware to naive and raise."""
        out = _naive_session_payload({
            "actual_start_time": datetime(2026, 9, 15, 22, 45, tzinfo=timezone.utc),
            "actual_end_time": datetime(2026, 9, 15, 3, 40, tzinfo=timezone.utc),
        })
        assert out["actual_end_time"].tzinfo is None
        assert out["actual_end_time"] == datetime(2026, 9, 16, 3, 40)

    def test_an_offset_is_converted_to_utc_not_merely_stripped(self):
        out = _naive_session_payload({
            "actual_start_time": datetime(2026, 9, 15, 22, 45,
                                          tzinfo=timezone(timedelta(hours=1))),
        })
        assert out["actual_start_time"] == datetime(2026, 9, 15, 21, 45)

    def test_an_explicit_none_is_preserved(self):
        out = _naive_session_payload({"actual_end_time": None,
                                      "actual_start_time": None})
        assert out["actual_end_time"] is None
        assert out["actual_start_time"] is None
