SELECT 'lab_results' as tbl, COUNT(*) as cnt FROM lab_results WHERE user_id=1
UNION ALL SELECT 'therapy_sessions', COUNT(*) FROM therapy_sessions WHERE condition_id=14
UNION ALL SELECT 'intradialytic_readings', COUNT(*) FROM intradialytic_readings r JOIN therapy_sessions s ON r.session_id=s.id WHERE s.condition_id=14
UNION ALL SELECT 'nutrition_logs', COUNT(*) FROM nutrition_logs WHERE user_id=1
UNION ALL SELECT 'bowel_movements', COUNT(*) FROM bowel_movements WHERE user_id=1
UNION ALL SELECT 'vomiting_logs', COUNT(*) FROM vomiting_logs WHERE user_id=1
UNION ALL SELECT 'medication_logs', COUNT(*) FROM medication_logs WHERE user_id=1
UNION ALL SELECT 'vitals_logs', Count(*) FROM vitals_logs WHERE user_id=1
UNION ALL SELECT 'mood_entries', COUNT(*) FROM mood_entries WHERE user_id=1
UNION ALL SELECT 'symptom_logs', COUNT(*) FROM symptom_logs WHERE user_id=1
UNION ALL SELECT 'calendar_events', COUNT(*) FROM calendar_events WHERE user_id=1
ORDER BY tbl;
