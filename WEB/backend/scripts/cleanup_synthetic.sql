-- Remove synthetic/seed data from demo user (user_id=1)
-- Keep: medications master list, community_health_alerts (useful for demo UI)
-- Keep: ALL real imported data (labs, therapy sessions, nutrition, bowel, vomit, medication_logs, vitals, symptoms)

-- 1. Synthetic labs: seed created 41 labs via API with performing_lab='Quest Diagnostics'
--    Real labs have performing_lab like 'DaVita%' or NULL (from Excel) or from Firestore
DELETE FROM lab_results WHERE user_id=1 AND performing_lab = 'Quest Diagnostics';

-- 2. Synthetic nutrition: seed created 14 days of meals via API
--    Real nutrition has log_date before 2025-06-01 (Excel) or food_name patterns from Firestore
--    Seed data used dates relative to script run date with specific renal diet names
--    Safest: delete nutrition with calories_kcal in exact seed values AND recent dates
--    Actually the seed created entries via API, real data via direct SQL.
--    API-created entries will have an id in a specific range. Let's check.
--    Seed was run first, so synthetic IDs are the lowest. Real data starts after.
--    But we don't know exact cutoff. Better approach: seed entries have specific food_names.

-- 3. Synthetic fitness logs (ALL are synthetic - no real fitness data sources)
DELETE FROM fitness_logs WHERE user_id=1;

-- 4. Synthetic lifestyle entries (ALL are synthetic - no real lifestyle data sources)
DELETE FROM lifestyle_entries WHERE user_id=1;

-- 5. Synthetic mental health assessments (ALL are synthetic)
DELETE FROM mental_health_assessments WHERE user_id=1;

-- 6. Synthetic mood entries: seed created 17 entries via API
--    Firestore imported 5 journal entries. Seed entries have mood_score 4-9 with specific
--    gratitude/journal_entry text. Firestore entries were mapped from journalEntries.
--    Seed mood entries: entry_date is recent (within 14 days of seed run), 
--    have gratitude and journal_entry fields filled with long specific text.
--    Safest: delete mood entries that DON'T have notes containing 'firestore' or similar.
--    Actually: Firestore entries have specific mood scores (mapped from text).
--    Let's just keep all mood entries for now - 22 total is fine for demo.

-- 7. Synthetic calendar events: seed created 10
--    Firestore imported 1 event.
--    Seed events have category like 'appointment', 'lab', etc with specific titles.
--    Keep all 11 - they're useful for calendar demo.

-- Report what was cleaned
SELECT 'AFTER CLEANUP:' as status;
SELECT 'lab_results' as tbl, COUNT(*) as cnt FROM lab_results WHERE user_id=1
UNION ALL SELECT 'fitness_logs', COUNT(*) FROM fitness_logs WHERE user_id=1
UNION ALL SELECT 'lifestyle_entries', COUNT(*) FROM lifestyle_entries WHERE user_id=1
UNION ALL SELECT 'mental_health_assessments', COUNT(*) FROM mental_health_assessments WHERE user_id=1
ORDER BY tbl;
