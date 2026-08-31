-- Read-only probe: what profile context does the planner/chat actually have?
-- Answers "why does ALAFIA not know the weight, and why is G6PD missing?"
-- Safe to run against prod: SELECT only.

\echo '== users carrying a G6PD condition =='
SELECT u.id,
       u.current_weight_kg,
       u.height_cm,
       u.gender,
       (u.date_of_birth IS NOT NULL) AS has_dob,
       (SELECT count(*) FROM chronic_conditions c
         WHERE c.user_id = u.id AND c.is_active) AS active_conds
FROM users u
WHERE EXISTS (
  SELECT 1 FROM chronic_conditions c
   WHERE c.user_id = u.id
     AND (c.name ILIKE '%G6PD%' OR c.name ILIKE '%glucose-6%' OR c.icd11_code = '3A10.00')
)
ORDER BY u.id;

\echo ''
\echo '== those users conditions, with is_active =='
SELECT c.user_id, c.name, c.is_active, c.severity, c.icd11_code, c.icd10_code
FROM chronic_conditions c
WHERE c.user_id IN (
  SELECT c2.user_id FROM chronic_conditions c2
   WHERE c2.name ILIKE '%G6PD%' OR c2.name ILIKE '%glucose-6%' OR c2.icd11_code = '3A10.00'
)
ORDER BY c.user_id, c.is_active DESC, c.name;

\echo ''
\echo '== weight coverage across users holding nutrition data =='
SELECT count(*) FILTER (WHERE u.current_weight_kg IS NOT NULL) AS with_weight,
       count(*) FILTER (WHERE u.current_weight_kg IS NULL)     AS without_weight,
       count(*)                                                AS total
FROM users u
WHERE EXISTS (SELECT 1 FROM nutrition_logs n WHERE n.user_id = u.id);

\echo ''
\echo '== is there a dry weight recorded in therapy_sessions instead? =='
SELECT t.user_id,
       count(*)                              AS sessions,
       max(t.scheduled_date)                 AS last_session,
       count(t.post_weight_kg)               AS post_weights,
       max(t.post_weight_kg)                 AS a_post_weight,
       count(t.pre_weight_kg)                AS pre_weights,
       max(t.pre_weight_kg)                  AS a_pre_weight
FROM therapy_sessions t
GROUP BY t.user_id
ORDER BY sessions DESC
LIMIT 5;
