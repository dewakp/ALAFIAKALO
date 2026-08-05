-- Undo deactivate_test_accounts.sql.
--
-- Restores every account listed in `deactivated_accounts` to its original email
-- and active state, and re-enables the matching identity rows. Safe to run more
-- than once.
--
--   psql … -f deactivate_test_accounts_rollback.sql

\set ON_ERROR_STOP on

BEGIN;

\echo '── restoring ──'
SELECT count(*) AS to_restore FROM deactivated_accounts;

UPDATE users u
SET email = d.original_email,
    is_active = true
FROM deactivated_accounts d
WHERE u.id = d.user_id;

UPDATE identity.users i
SET account_status = 'active',
    updated_at = now()
FROM deactivated_accounts d
WHERE lower(i.email) = lower(COALESCE(d.identity_email, d.original_email));

-- Identity-only robot accounts disabled by step 5.
UPDATE identity.users i
SET account_status = 'active', updated_at = now()
FROM deactivated_identity_only o
WHERE i.email = o.identity_email;

DELETE FROM deactivated_accounts;
DELETE FROM deactivated_identity_only;

SELECT 'active users now: ' || count(*) FROM users WHERE is_active = true;

COMMIT;
\echo '*** restored ***'
