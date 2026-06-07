-- Clear auto-fabricated medication LIST rows.
-- The buggy get-or-CREATE sync invented one `medications` (LIST = curated
-- prescription record) row per drug NAME seen in dose events. These rows carry
-- no real prescription data (NULL dosage/dosage_unit/frequency/prescribing_doctor
-- /reason) — they are artifacts, not a list the user curated. Keeping them
-- pollutes the medication LIST with phantom prescriptions (data drift).
--
-- This removes only those fabricated rows. ALL "TAKEN" data is preserved:
-- medication_dose_logs keep their own medication_name; we just null their FK
-- link to the deleted LIST rows. The sync is now get-only, so it will never
-- re-create them.
BEGIN;

CREATE TEMP TABLE _fab_meds ON COMMIT DROP AS
SELECT id
FROM medications
WHERE dosage IS NULL
  AND dosage_unit IS NULL
  AND frequency IS NULL
  AND prescribing_doctor IS NULL
  AND reason IS NULL;

-- Unlink dose events from the rows about to be deleted (keep the TAKEN history).
UPDATE medication_dose_logs d
SET medication_id = NULL
WHERE d.medication_id IN (SELECT id FROM _fab_meds);

-- Delete the fabricated LIST rows.
DELETE FROM medications WHERE id IN (SELECT id FROM _fab_meds);

SELECT COUNT(*) AS deleted_list_rows FROM _fab_meds;

COMMIT;
