# ALAFIA — queued work

Work that is agreed but not yet started. Completed work goes in `WORKLOG.md`.

---

## ~~Flowsheet housekeeping~~ — DONE 2026-08-20

Shipped on backend, web, iOS and Android. Kept here as the spec.
Queued and completed 2026-08-20. Three changes to new-treatment entry, all of which exist to
stop a patient re-entering data that has not changed since last time.

Canon §3 applies: web, iOS and Android each need this, verified by building.

### 1. Target weight from a 7-treatment moving average

Today's target (dry) weight should default to the **mean of the last 7
treatments' post weights**, not be typed in fresh.

- Source: `therapy_sessions.post_dialysis_weight_kg`, the 7 most recent
  *completed* sessions before today.
- Fewer than 7 on file → use what exists and say so; do not silently average 2.
- Show the value as a default the patient can override, with the basis visible
  ("average of your last 7 post weights").
- Watch: post weight is nullable and a session with none must not be counted as
  zero — that would drag the mean down and set an unsafe fluid-removal target.

### 2. Pre-populate the fields that rarely change

Carry forward from the most recent completed session, always editable:

- Physician, Nurse
- Machine type / make / model
- Dialysate type, dialysate volume, dialysate K⁺ and Ca²⁺ prescription
- Cartridge #, SAK #

Notes:
- These are *defaults*, never silently submitted values — the patient must be
  able to see and change each one.
- Bath potassium feeds the transfer model (`DIALYSIS_BALANCE.md`), so a
  carried-forward value that is stale would quietly skew the day's balance.
  Carry it, but re-validate against the plausible band (0–4 mEq/L) — 11 rows
  already carry 45, which is the lactate value in the wrong column.

### 3. Access type carry-forward, with fistula fields disabled for a catheter

- Default the access type to whatever the previous session used.
- If it is a **catheter**, gray out (disable, not hide) the fistula-only fields:
  **Needle Gauge, Needle Length, Buttonhole, Access Bruit**.
- A catheter has no needles and no bruit, so those fields being enabled invites
  meaningless data; disabling rather than hiding keeps the form recognisable
  and makes the reason visible.
- Switching the access type back to a fistula must re-enable them immediately.
- Existing rows that already carry needle data on a catheter session should be
  left alone, not blanked.

### Verification

- Backend: a "last session defaults" endpoint (or an extension of the existing
  session read) with tests for the empty case, the fewer-than-7 case, and the
  null-post-weight case.
- `docker compose --profile test run --rm backend-test` / `frontend-test` / `e2e`
- `xcodebuild -scheme ALAFIA` and `./gradlew :app:assembleDebug`
