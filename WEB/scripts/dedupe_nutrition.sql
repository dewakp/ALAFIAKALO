-- Deduplicate nutrition_logs: keep the richest row per
-- (user_id, log_date, meal_type, food_name) group, repoint the Firebase
-- ledger to the survivor, then delete the duplicates.
BEGIN;

CREATE TEMP TABLE _dups ON COMMIT DROP AS
WITH ranked AS (
    SELECT
        id,
        FIRST_VALUE(id) OVER w AS keep_id,
        ROW_NUMBER()     OVER w AS rn
    FROM nutrition_logs
    WINDOW w AS (
        PARTITION BY user_id, log_date, meal_type, food_name
        ORDER BY (calories IS NOT NULL AND calories > 0) DESC, id ASC
    )
)
SELECT id, keep_id FROM ranked WHERE rn > 1;

-- Repoint the Firebase ledger so every external_id still maps to a live row
-- (prevents re-import on the next sync).
UPDATE synced_records s
SET target_record_id = d.keep_id
FROM _dups d
WHERE s.target_record_id = d.id
  AND s.data_type = 'nutritionLog';

-- Remove the duplicate nutrition rows.
DELETE FROM nutrition_logs WHERE id IN (SELECT id FROM _dups);

SELECT COUNT(*) AS deleted_rows FROM _dups;

COMMIT;
