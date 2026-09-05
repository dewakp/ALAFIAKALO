-- Read-only investigation of one member's subscription. SELECT only.
-- Usage: prod_psql -v who='%cecilia%' -f /sql/probe_subscription.sql
\set ON_ERROR_STOP on

\echo '== 1. the account =='
SELECT u.id, u.email, u.full_name, u.is_active, u.is_superuser,
       u.created_at, u.last_login, u.auth_provider
FROM users u
WHERE u.full_name ILIKE :'who' OR u.email ILIKE :'who'
ORDER BY u.id;

\echo ''
\echo '== 2. subscription rows (none at all is the finding) =='
SELECT s.id, s.user_id, s.status, s.provider, s.plan, s.price_usd,
       s.current_period_start, s.current_period_end,
       (s.current_period_end > NOW()) AS entitling_window,
       s.stripe_customer_id, s.stripe_subscription_id,
       s.cancel_at_period_end, s.canceled_at, s.created_at
FROM subscriptions s
JOIN users u ON u.id = s.user_id
WHERE u.full_name ILIKE :'who' OR u.email ILIKE :'who';

\echo ''
\echo '== 3. billing events attributed to them =='
SELECT e.id, e.event_type, e.created_at, e.user_id,
       (e.payload IS NULL) AS payload_null
FROM subscription_events e
JOIN users u ON u.id = e.user_id
WHERE u.full_name ILIKE :'who' OR u.email ILIKE :'who'
ORDER BY e.created_at;

\echo ''
\echo '== 4. ALL events since 2026-09-01, attributed or not =='
SELECT e.id, e.event_type, e.created_at, e.user_id,
       (e.payload IS NULL) AS payload_null,
       left(coalesce(e.payload::text, ''), 160) AS payload_head
FROM subscription_events e
WHERE e.created_at >= '2026-09-01'
ORDER BY e.created_at;

\echo ''
\echo '== 5. does the app consider them entitled? (status + exempt list) =='
SELECT u.id, u.email,
       (SELECT count(*) FROM subscriptions s WHERE s.user_id = u.id) AS sub_rows,
       (SELECT count(*) FROM subscriptions s
         WHERE s.user_id = u.id
           AND s.status IN ('active','trialing','past_due')
           AND (s.current_period_end IS NULL OR s.current_period_end > NOW())
       ) AS entitling_rows
FROM users u
WHERE u.full_name ILIKE :'who' OR u.email ILIKE :'who';
