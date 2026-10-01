-- Repair lab rows that cannot be true, and flags that were never computed.
--
-- Run through scripts/db/repair_impossible_labs.sh, which appends COMMIT or
-- ROLLBACK so the dry run executes byte-identical statements to the real run.
--
-- ─────────────────────────────────────────────────────────────────────────────
-- PART 1 — the fabricated haematocrit
--
-- A record carries `HGBX 338.4 %` against a printed range of 42-52, rendered to
-- the patient with a green tick. The true value is 38.4%. The analyte is
-- HCT CALC (HGBX3) — haematocrit calculated as haemoglobin x 3 — and that day's
-- haemoglobin was 12.8, so 12.8 x 3 = 38.4 exactly. A literal "3" migrated from
-- the END of the NAME to the FRONT of the VALUE upstream, leaving the figure
-- exactly 300 too high.
--
--      date         stored    true    HGB x 3
--      2025-01-27   327.3     27.3    9.1 x 3
--      2025-03-21   324.6     24.6    8.2 x 3
--      2025-07-17   338.4     38.4    12.8 x 3
--
-- NOT our parser: the value arrives that way in the Firestore export, where the
-- analyte is stored as bare `HGBX` with the 3 missing from the name.
-- `Records.xlsx` sheet `Lab` is clean (2016-04-28 -> 2023-03-09, no value over
-- 100), and every PDF prints `HGBX3` correctly.
--
-- THIS IS A REPAIR, NOT A GUESS — and it proves that to itself before writing.
-- §3ab warns that putting an invented value onto a clinical record is worse
-- than removing the row, so the UPDATE fires only where TWO independent
-- derivations agree to within a rounding tolerance:
--
--      (a) stored - 300               the transposed-digit signature
--      (b) that day's HGB x 3         the analyte's own definition
--
-- A row where they disagree is left exactly as it is, for a human.
-- ─────────────────────────────────────────────────────────────────────────────

\echo ''
\echo '=== PART 1: impossible percentages, and what the arithmetic says ==='

SELECT x.id,
       x.user_id,
       x.test_date,
       x.test_name,
       x.value                         AS stored,
       x.value - 300                   AS implied_by_transposition,
       round((h.value * 3)::numeric, 2) AS implied_by_hgb_times_3,
       h.value                         AS hgb_that_day,
       CASE
         WHEN h.value IS NULL THEN 'NO HGB THAT DAY — left alone'
         WHEN abs((x.value - 300) - (h.value * 3)) < 0.05 THEN 'REPAIRABLE'
         ELSE 'DERIVATIONS DISAGREE — left alone'
       END                             AS verdict
FROM lab_results x
LEFT JOIN lab_results h
       ON h.user_id = x.user_id
      AND h.test_date = x.test_date
      AND upper(h.test_name) = 'HGB'
-- A percentage cannot exceed the whole. `trim(unit) LIKE '\%%'` matches '%'
-- and '%Final' alike — a narrow unit column welds the status onto the unit.
WHERE trim(x.unit) LIKE '\%%'
  AND x.value > 100
ORDER BY x.test_date;

-- The repair. Both derivations must agree, and the row must still be impossible
-- (> 100%) — so re-running this after it has been applied changes nothing.
UPDATE lab_results x
SET value = x.value - 300,
    -- FM999999.99 trimmed renders 38.4 as "38.4", not "38.40": `value_string`
    -- is what the report printed, and padding it invents precision the lab
    -- never stated.
    value_string = trim(to_char(x.value - 300, 'FM999999.99')),
    notes = concat_ws(' | ', nullif(x.notes, ''),
                      'Repaired 2026-09-30: stored value was 300 too high — a '
                      'digit from the analyte name HGBX3 had migrated into the '
                      'value upstream. Confirmed against that day''s HGB x 3.')
FROM lab_results h
WHERE h.user_id = x.user_id
  AND h.test_date = x.test_date
  AND upper(h.test_name) = 'HGB'
  AND trim(x.unit) LIKE '\%%'
  AND x.value > 100
  AND abs((x.value - 300) - (h.value * 3)) < 0.05;

\echo ''
\echo '=== PART 1 result: any percentage still above 100 needs a human ==='
SELECT id, user_id, test_date, test_name, value, unit
FROM lab_results
WHERE trim(unit) LIKE '\%%' AND value > 100
ORDER BY test_date;

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 2 — the abnormality flag that was never computed
--
-- `is_abnormal` is a TRI-STATE: true, false, or NULL meaning "nothing ever
-- compared this value to a range". On this database 9,417 of 9,745 rows are
-- NULL, and every client rendered that as the reassuring branch — "Normal"
-- beside a potassium of 6.7 against a 3.5-5.5 range.
--
-- The clients are fixed to show three states. This fills in the flag wherever
-- the row already carries the range needed to compute it, which is what
-- `normalize.compute_abnormal` would have done had the bulk importers called
-- it. `import_unified_labs.py` stores ref_low, ref_high AND value, and simply
-- passes through whatever `flag` the source CSV had — empty, for the firestore
-- rows.
--
-- Rows with no range keep NULL, which is now honest rather than silent: the
-- clients say "Not assessed".
-- ─────────────────────────────────────────────────────────────────────────────

\echo ''
\echo '=== PART 2: rows that contradict their own printed range ==='
SELECT count(*) AS contradicts_own_range
FROM lab_results
WHERE is_abnormal IS NULL
  AND value IS NOT NULL
  AND ((reference_range_high IS NOT NULL AND value > reference_range_high)
    OR (reference_range_low  IS NOT NULL AND value < reference_range_low));

\echo '=== PART 2: rows that will be flagged in range ==='
SELECT count(*) AS will_be_in_range
FROM lab_results
WHERE is_abnormal IS NULL
  AND value IS NOT NULL
  AND (reference_range_low IS NOT NULL OR reference_range_high IS NOT NULL)
  AND (reference_range_high IS NULL OR value <= reference_range_high)
  AND (reference_range_low  IS NULL OR value >= reference_range_low);

UPDATE lab_results
SET is_abnormal = (
      (reference_range_high IS NOT NULL AND value > reference_range_high)
   OR (reference_range_low  IS NOT NULL AND value < reference_range_low)
    )
WHERE is_abnormal IS NULL
  AND value IS NOT NULL
  AND (reference_range_low IS NOT NULL OR reference_range_high IS NOT NULL);

\echo ''
\echo '=== PART 2 result: the tri-state, after ==='
SELECT is_abnormal, count(*) FROM lab_results GROUP BY is_abnormal ORDER BY 2 DESC;
