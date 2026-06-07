-- Purge known source data-entry errors from medication tables.
-- "Sodium Carbonate" is a mislabel for "Sodium Bicarbonate" (and includes the
-- lone implausible 22500 mg 2025-06-16 dose). Per product decision these are
-- left at the source and NOT imported; this removes the already-imported rows.
-- The firebase_sync medicationLog blocklist prevents re-import on the next sync.
BEGIN;

CREATE TEMP TABLE _bad_doses ON COMMIT DROP AS
SELECT id, medication_id
FROM medication_dose_logs
WHERE lower(regexp_replace(trim(medication_name), '\s+', ' ', 'g')) = 'sodium carbonate';

-- Drop the Firebase ledger rows pointing at these dose logs so a corrected
-- source record can sync later (no stale pointer, no dedup short-circuit).
DELETE FROM synced_records s
USING _bad_doses b
WHERE s.data_type = 'medicationLog'
  AND s.target_record_id = b.id;

-- Remove the erroneous dose-taking events.
DELETE FROM medication_dose_logs WHERE id IN (SELECT id FROM _bad_doses);

-- Remove the orphaned catalog row(s) now that no dose log references them.
DELETE FROM medications m
WHERE lower(regexp_replace(trim(m.name), '\s+', ' ', 'g')) = 'sodium carbonate'
  AND NOT EXISTS (
      SELECT 1 FROM medication_dose_logs d WHERE d.medication_id = m.id
  );

SELECT COUNT(*) AS deleted_dose_logs FROM _bad_doses;

COMMIT;
