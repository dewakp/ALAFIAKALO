-- Correct profile heights that were stored as inches in a centimetre column.
--
-- The API used to accept a bare `height_cm` with no unit and no bounds, while
-- `core/units.py`'s `inches_to_cm` had no callers at all. An imperial patient
-- entering 70 was stored as a 70 cm adult, which then fed BMI and every
-- weight-derived nutrient target.
--
-- Two conditions must BOTH hold before a row is touched:
--
--   1. the stored height is impossible for the patient's age, and
--   2. the patient's OWN vitals_logs corroborate a real height that the
--      stored number matches when read as inches (within 5 cm).
--
-- Condition 2 is what makes this a correction rather than a guess. On the row
-- that prompted it, the profile said 70 while ten annual vitals entries from
-- 2011-2020 all said 176.35 cm, and 70 in = 177.8 cm. Where no corroborating
-- measurement exists, the row is LEFT ALONE and reported instead — inventing a
-- height is worse than holding a wrong one that a clinician can see.

\set ON_ERROR_STOP on

CREATE TEMP TABLE _fixable AS
WITH ages AS (
  SELECT u.id,
         u.height_cm,
         date_part('year', age(to_date(u.date_of_birth, 'YYYY-MM-DD')))::int AS age_years
  FROM users u
  WHERE u.height_cm IS NOT NULL
    AND u.date_of_birth IS NOT NULL
),
adults AS (
  -- Impossible as centimetres for an adult (the endpoint's own band).
  SELECT * FROM ages WHERE age_years >= 18 AND height_cm < 120
),
measured AS (
  SELECT a.id, a.height_cm, a.age_years,
         (SELECT round(avg(v.height_cm)::numeric, 2)
            FROM vitals_logs v
           WHERE v.user_id = a.id AND v.height_cm BETWEEN 120 AND 280) AS vitals_cm
  FROM adults a
)
SELECT id,
       height_cm                       AS stored,
       age_years,
       vitals_cm,
       round((height_cm * 2.54)::numeric, 2) AS as_inches_cm
FROM measured
WHERE vitals_cm IS NOT NULL
  AND abs(vitals_cm - (height_cm * 2.54)) <= 5.0;

\echo ''
\echo '== rows that WILL be corrected (stored inches -> the patient''s measured cm) =='
SELECT * FROM _fixable ORDER BY id;

\echo ''
\echo '== adults with an impossible height and NO corroborating measurement (left alone) =='
WITH ages AS (
  SELECT u.id, u.height_cm,
         date_part('year', age(to_date(u.date_of_birth, 'YYYY-MM-DD')))::int AS age_years
  FROM users u
  WHERE u.height_cm IS NOT NULL AND u.date_of_birth IS NOT NULL
)
SELECT a.id, a.height_cm AS stored, a.age_years,
       round((a.height_cm * 2.54)::numeric, 2) AS would_be_cm_if_inches
FROM ages a
WHERE a.age_years >= 18 AND a.height_cm < 120
  AND a.id NOT IN (SELECT id FROM _fixable)
ORDER BY a.id;

-- The write. Uses the patient's own measured height, not the arithmetic
-- conversion: 176.35 is what they were actually measured at, 177.8 is only
-- what 70 inches converts to.
UPDATE users u
   SET height_cm = f.vitals_cm,
       updated_at = NOW()
  FROM _fixable f
 WHERE u.id = f.id;

\echo ''
\echo '== after =='
SELECT u.id, u.height_cm FROM users u JOIN _fixable f ON f.id = u.id ORDER BY u.id;
