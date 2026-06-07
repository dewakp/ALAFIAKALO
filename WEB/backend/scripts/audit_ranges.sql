SELECT 'lab_results' as tbl, MIN(test_date)::text as earliest, MAX(test_date)::text as latest FROM lab_results WHERE user_id=1
UNION ALL SELECT 'therapy_sessions', MIN(scheduled_date::date)::text, MAX(scheduled_date::date)::text FROM therapy_sessions WHERE condition_id=14
UNION ALL SELECT 'nutrition_logs', MIN(log_date)::text, MAX(log_date)::text FROM nutrition_logs WHERE user_id=1
UNION ALL SELECT 'bowel_movements', MIN(log_date)::text, MAX(log_date)::text FROM bowel_movements WHERE user_id=1
UNION ALL SELECT 'vomiting_logs', MIN(log_date)::text, MAX(log_date)::text FROM vomiting_logs WHERE user_id=1
UNION ALL SELECT 'medication_logs', MIN(log_date)::text, MAX(log_date)::text FROM medication_logs WHERE user_id=1
UNION ALL SELECT 'vitals_logs', MIN(log_date)::text, MAX(log_date)::text FROM vitals_logs WHERE user_id=1
UNION ALL SELECT 'mood_entries', MIN(entry_date)::text, MAX(entry_date)::text FROM mood_entries WHERE user_id=1
ORDER BY tbl;
