-- Blank the weights that are not a person's, and the fluid figure derived from
-- them, in PRODUCTION.
--
-- `fluid_removed_ml` is exactly (pre - post) x 1000, so a weighing-machine
-- fault becomes a fluid figure and then a bad average: the clinician
-- dashboard's "average fluid removed" reads 608 ml against a true 663 ml,
-- because nine rows sit inside the mean.
--
-- The SESSION is not deleted. The treatment happened; only the weighing is
-- wrong, and removing the row would lose a real dialysis session. The bad
-- fields are set to NULL, which the app already renders as "not recorded"
-- rather than as a zero.
--
-- Selection is by physiology, not by a list of ids: a weight outside 20-300 kg
-- is not a human being, and a session cannot change body mass by more than
-- about a tenth. Those are the same bounds `TherapySessionBase` now enforces on
-- the way in, so this cleans exactly what the validation would refuse today.

\set ON_ERROR_STOP on

CREATE TEMPORARY TABLE _bad AS
SELECT id, scheduled_date::date AS d,
       pre_dialysis_weight_kg AS pre, post_dialysis_weight_kg AS post,
       fluid_removed_ml AS fluid
FROM therapy_sessions
WHERE (pre_dialysis_weight_kg IS NOT NULL
         AND (pre_dialysis_weight_kg <= 20 OR pre_dialysis_weight_kg >= 300))
   OR (post_dialysis_weight_kg IS NOT NULL
         AND (post_dialysis_weight_kg <= 20 OR post_dialysis_weight_kg >= 300))
   OR (fluid_removed_ml IS NOT NULL AND post_dialysis_weight_kg IS NOT NULL
         AND abs(fluid_removed_ml) / 1000.0 > 0.10 * post_dialysis_weight_kg)
   OR (pre_dialysis_weight_kg IS NOT NULL AND post_dialysis_weight_kg IS NOT NULL
         AND abs(pre_dialysis_weight_kg - post_dialysis_weight_kg)
             > 0.10 * post_dialysis_weight_kg);

\echo ''
\echo 'Sessions to be corrected (weights and derived fluid set to NULL):'
SELECT id, d, pre, post, fluid FROM _bad ORDER BY abs(COALESCE(fluid,0)) DESC;

\echo ''
\echo 'Effect on the clinician dashboard average:'
SELECT round(avg(fluid_removed_ml)::numeric, 1) AS avg_now,
       round(avg(fluid_removed_ml) FILTER (
           WHERE id NOT IN (SELECT id FROM _bad))::numeric, 1) AS avg_after
FROM therapy_sessions WHERE fluid_removed_ml IS NOT NULL;

UPDATE therapy_sessions t
SET pre_dialysis_weight_kg =
      CASE WHEN t.pre_dialysis_weight_kg <= 20 OR t.pre_dialysis_weight_kg >= 300
           THEN NULL ELSE t.pre_dialysis_weight_kg END,
    post_dialysis_weight_kg =
      CASE WHEN t.post_dialysis_weight_kg <= 20 OR t.post_dialysis_weight_kg >= 300
           THEN NULL ELSE t.post_dialysis_weight_kg END,
    -- The fluid figure was computed from those weights, so it goes with them.
    fluid_removed_ml = NULL
FROM _bad b
WHERE t.id = b.id;

\echo ''
\echo 'Rows updated:'
SELECT count(*) AS corrected FROM _bad;
