-- Identify synthetic (seeded) vs real (imported) data for user_id=1

SELECT 'medications_master' as tbl, COUNT(*) as cnt FROM medications WHERE user_id=1
UNION ALL SELECT 'fitness_logs', COUNT(*) FROM fitness_logs WHERE user_id=1
UNION ALL SELECT 'mental_health_assessments', COUNT(*) FROM mental_health_assessments WHERE user_id=1
UNION ALL SELECT 'lifestyle_entries', COUNT(*) FROM lifestyle_entries WHERE user_id=1
UNION ALL SELECT 'community_health_alerts', COUNT(*) FROM community_health_alerts
UNION ALL SELECT 'health_conditions', COUNT(*) FROM health_conditions WHERE user_id=1
UNION ALL SELECT 'insurances', COUNT(*) FROM insurances WHERE user_id=1
UNION ALL SELECT 'mood_entries', Count(*) FROM mood_entries WHERE user_id=1
UNION ALL SELECT 'calendar_events', COUNT(*) FROM calendar_events WHERE user_id=1
UNION ALL SELECT 'telehealth_sessions', COUNT(*) FROM telehealth_sessions
ORDER BY tbl;
