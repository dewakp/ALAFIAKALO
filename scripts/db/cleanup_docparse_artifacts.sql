-- Remove lab rows that a document parser invented from a PDF's boilerplate and
-- column overflow. See CLAUDE.md §3ab.
--
-- TWO artefacts, both from the DaVita lab reports:
--
--  1. PROSE AS A RESULT. The reports carry a disciplinary-policy footer,
--     "disciplinary action, up to and including termination of employment with
--     DaVita." It parsed into a test name and a value and was shown to a
--     clinician among real results. Two variants exist because the line wrapped
--     differently between documents:
--         'up to and including termination of' -> 'employment with DaVita.'
--         'up to and including termination'    -> 'of employment with DaVita.'
--
--  2. NAME OVERFLOW EATING THE VALUE. A name wider than its header label spills
--     past the column boundary, so on
--         1715 WEIGHT - PRE DAY 1   57.5 kg
--     the "1" of "DAY 1" landed in the value column and won: the row was stored
--     as WEIGHT - PRE DAY = 1.0 kg and the true 57.5 was discarded. A clinician
--     saw 1 kg for a 57 kg dialysis patient, and the pre/post pair that should
--     differ by ~1 kg both read as 1.
--
-- Both parser faults are FIXED (looks_like_prose, _reclaim_name_overflow), but
-- a fix cannot rewrite rows already imported — and re-importing will NOT heal
-- them. Dedupe is keyed on (test_date, lower(test_name)) and the correction
-- CHANGES the name, so a corrected row arrives as DEDUPE_NEW and is inserted
-- alongside the bad one. Delete first, then re-import.
--
-- Deletion is right here rather than an UPDATE: the true value is only
-- recoverable from the source PDF, and guessing it would put an invented number
-- on a clinical record.
--
-- Run through cleanup_docparse_artifacts.sh, which dry-runs by default.

\set ON_ERROR_STOP on

BEGIN;

-- ── 1. What will go, listed before anything is removed ──────────────────────

\echo ''
\echo '── PROSE rows (parsed from the policy footer) ──'
SELECT id, user_id, test_date, test_name, value_string, unit
FROM lab_results
WHERE test_name ILIKE '%up to and including termination%'
ORDER BY user_id, test_date;

\echo ''
\echo '── WEIGHT rows whose value is the day number, not the weight ──'
-- Deliberately narrow. Only names ending in the truncated "DAY" form, and only
-- where the value is exactly 1 — a real weight is never 1 kg, but a *correctly*
-- parsed "WEIGHT - PRE DAY 1 = 53.6" must not be touched.
SELECT id, user_id, test_date, test_name, value, unit
FROM lab_results
WHERE test_name ~* '^WEIGHT\s*-\s*(PRE|POST)\s*DAY$'
  AND value = 1
ORDER BY user_id, test_date;

\echo ''
\echo '── Totals ──'
SELECT
  (SELECT count(*) FROM lab_results
     WHERE test_name ILIKE '%up to and including termination%')       AS prose_rows,
  (SELECT count(*) FROM lab_results
     WHERE test_name ~* '^WEIGHT\s*-\s*(PRE|POST)\s*DAY$' AND value = 1) AS weight_rows;

-- ── 2. Safety rail ──────────────────────────────────────────────────────────
--
-- If these patterns ever match far more than the ~35 rows observed, something
-- is wrong with the pattern and not with the data. Fail rather than delete.

DO $$
DECLARE
    n integer;
BEGIN
    SELECT count(*) INTO n FROM lab_results
     WHERE test_name ILIKE '%up to and including termination%'
        OR (test_name ~* '^WEIGHT\s*-\s*(PRE|POST)\s*DAY$' AND value = 1);
    IF n > 500 THEN
        RAISE EXCEPTION
          'Refusing to delete % rows — expected well under 500. Check the patterns.', n;
    END IF;
    RAISE NOTICE 'Rows matching cleanup patterns: %', n;
END $$;

-- ── 3. The deletions ────────────────────────────────────────────────────────

DELETE FROM lab_results
WHERE test_name ILIKE '%up to and including termination%';

DELETE FROM lab_results
WHERE test_name ~* '^WEIGHT\s*-\s*(PRE|POST)\s*DAY$'
  AND value = 1;

\echo ''
\echo '── Remaining (must be 0 and 0) ──'
SELECT
  (SELECT count(*) FROM lab_results
     WHERE test_name ILIKE '%up to and including termination%')       AS prose_rows,
  (SELECT count(*) FROM lab_results
     WHERE test_name ~* '^WEIGHT\s*-\s*(PRE|POST)\s*DAY$' AND value = 1) AS weight_rows;

-- The runner decides: it substitutes COMMIT only with --apply, ROLLBACK otherwise.
