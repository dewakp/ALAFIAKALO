# The clinician patient board

How a physician sees a patient, and the traps that made it show the wrong thing.

A clinician opens **My Patients** → a patient card → a board of **category
cards** (latest values per category, plus the wellness score) → one card → trends
and the full records behind them.

```
/clinician-dashboard/                              patient grid
/clinician-dashboard/patient/{id}/board            category cards
/clinician-dashboard/patient/{id}/category/{key}   trends + records
```

## One registry, not fourteen endpoints

Every category is declared once in **`app/services/patient_board.py`**:

```python
Category("labs", "Labs", "flask", _labs_summary, _labs_detail)
```

The board, the drill-down and the `all` grant all read that list, so a category
cannot exist in one and be missing from another. **Adding a category means adding
one `Category`** — plus an icon in each client's map.

Clients render whatever the registry returns; they do not each decide what a
patient's record contains.

## `all` means all

`ALL_DATA_TYPES` in `app/models/data_sharing.py` is the definition. A grant of
`all` covers every entry, including ones added after the grant was written — a
patient never has to re-share because we shipped a category.

`tests/test_clinician_board.py` asserts **every** grantable type has a card. The
earlier version of that test only checked the cards that existed, which is how
`dialysis`, `symptoms` and `lifestyle` sat in `ALL_DATA_TYPES` with no card while
the suite stayed green — a physician saw no Therapies on a patient sharing
everything.

Categories the patient did **not** share stay on the board, greyed and locked.
Dropping them silently reads as "no data", which is a different clinical fact.

## The four ways this surface lied

Every one of these shipped, and every one showed *emptiness* where data existed.

| It said | It was |
|---|---|
| "No active medications" | reading `medications` (2 rows, stopped 2017, from the EHR sandbox) instead of `medication_dose_logs` (921 rows) |
| "No active conditions" | reading `health_conditions` — **zero writers anywhere in the app** — instead of `chronic_conditions`, which held End-Stage Renal Disease, severe, active |
| "No hemodialysis sessions" | a tz-aware datetime compared to a naive column → asyncpg `DataError` → 500 → swallowed by `catch (e) { console.error(e) }` |
| "Nothing logged in the last 7 days" | a hard 7-day window on a patient who last logged 60 days ago |

Two rules fall out of that list:

1. **Read through `app/services/clinical_sources.py`** for conditions and
   medications. `tests/test_clinical_sources.py` fails the build if anything
   queries those models directly. See CLAUDE.md §3aa.
2. **An error is never an empty state.** Keep a distinct error variable and show
   it. A windowed card reports *when* the patient last logged rather than
   rendering blank.

## A model attribute defined twice

`TherapySession` declared `clinical_notes` as **both** a `Column(Text)` and a
`relationship()`. Python keeps the last assignment, so the relationship silently
shadowed the column — and the column had never been migrated, so the mismatch was
invisible until something wrote to it.

The create schema still offered `clinical_notes` as a string, so submitting the
Hemodialysis **Session Form** passed it into the constructor, which tried to
assign a string to a relationship:

```
TypeError: Incompatible collection type: None is not list-like   → 500
```

Every session create failed. Notes are their own append-only rows
(`POST /chronic/therapy-sessions/{id}/notes`, with a SHA-512 integrity hash and a
blockchain anchor) — the session-level free-text column that does exist is
`patient_notes`.

Two lessons worth keeping:

- **A response model that declares a relationship obliges every read path to
  eager-load it.** All five `selectinload` sites now load `clinical_notes` as well
  as `intradialytic_readings`; missing one 500s only on the path nobody tested.
- **Grep case-sensitively at your peril.** The notes routes already existed at
  `/notes`; searching for `clinical` missed them because the symbol is
  `ClinicalNoteResponse`. iOS was calling `/clinical-notes`, a path that never
  existed, and its catch block made that look like "no notes yet" forever.

## Counting

Never let a query `LIMIT` become a count. The Therapies card reported "200
sessions" on a patient with 730 because `len(rows)` counted the limit. Counts
come from `func.count()`; the capped list is only for display.

Group medication dose logs **case-insensitively** — the same drug arrives as
"Calcium Carbonate" and "Calcium carbonate", and two rows misstate the regimen.

## Charts

Small multiples, never a dual axis. Series that share a unit share a plot;
different units get their own. Above six series the clinician picks which to
plot — six is the validated palette width, and a seventh would have to reuse a
hue.

Labs deliberately ignore the day window: they are episodic, and a 90-day window
on a real record returned a single draw per test and therefore no trend at all.

The palette in `pages/clinician/chartPalette.js` was validated against **this
app's** surfaces (`#ffffff` / `#1e293b`) with the `dataviz` skill's checker, not
inherited. Both modes pass with a contrast WARN, which obliges visible labels —
so every chart ships a legend and the full table underneath.

## Verifying

**Against the population, not one patient:**

```bash
docker compose --profile test run --rm backend-test python scripts/board_sweep.py
```

It runs every category against every user holding data and names the paths that
never executed. On this database that is how `fitness` (no rows for any user),
`lifestyle` (data belongs to a user I was not testing) and `pd_sessions` were
found to be unexercised.

```bash
docker compose --profile test run --rm backend-test pytest tests/test_clinician_board.py
docker compose --profile test run --rm backend-test pytest tests/test_clinical_sources.py
```

Known gap: **`fitness_logs` is empty for every user in this database**, so that
card has never run against real data.
