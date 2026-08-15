-- Attach (or fill in) the ProfessionalProfile on a user's professional role —
-- IDEMPOTENT, and safe to re-run.
--
-- Same reason as grant_comp_and_role.sql for being SQL: the only way to write a
-- professional profile through the API is `PUT /users/roles/{id}/profile`, which
-- needs the target user's own bearer token. For a user you cannot log in as,
-- the database is the only door.
--
-- It only ever WRITES THE FIELDS YOU PASS. An omitted field leaves whatever is
-- already there untouched (COALESCE on the conflict path), so running this to
-- seed a placeholder can never wipe out details the user later filled in
-- themselves.
--
-- `verification_status` is always written as 'unverified' on insert and never
-- touched on update. Credential verification is a real review step
-- (clinician_directory.py owns it for the public directory); a provisioning
-- script must not be able to mark someone verified.
--
-- Parameters (the wrapper script supplies them; '' means "leave alone"):
--   -v emails='a@x.com,b@y.com'   targets, comma-separated
--   -v role='physician'           which role assignment to attach the profile to
--   -v license='…'                license_number
--   -v specialty='…'              specialty
--   -v practice='…'               practice_name
--   -v dry_run=1|0                1 = print everything, then ROLLBACK

\set ON_ERROR_STOP on

BEGIN;

SET LOCAL TimeZone = 'UTC';

-- psql does not interpolate inside dollar-quoted strings, so the PL/pgSQL guard
-- below reads its parameters from here rather than from :vars directly.
CREATE TEMP TABLE _params ON COMMIT DROP AS
SELECT :'emails'::text    AS emails,
       :'role'::text      AS role,
       :'license'::text   AS license,
       :'specialty'::text AS specialty,
       :'practice'::text  AS practice;

CREATE TEMP TABLE _targets ON COMMIT DROP AS
SELECT u.id, u.email, u.full_name
FROM users u
JOIN _params p ON true
JOIN unnest(string_to_array(p.emails, ',')) AS t(email)
  ON lower(u.email) = lower(btrim(t.email));

-- Two ways this can quietly do nothing: an email that matches no user, or a
-- user who does not actually hold the role being decorated. Both abort.
DO $$
DECLARE missing text; roleless text;
BEGIN
    SELECT string_agg(btrim(t.email), ', ')
      INTO missing
      FROM _params p, unnest(string_to_array(p.emails, ',')) AS t(email)
     WHERE NOT EXISTS (
         SELECT 1 FROM users u WHERE lower(u.email) = lower(btrim(t.email))
     );
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'no users row for: %', missing;
    END IF;

    SELECT string_agg(t.email, ', ')
      INTO roleless
      FROM _targets t, _params p
     WHERE NOT EXISTS (
         SELECT 1 FROM user_role_assignments ra
          WHERE ra.user_id = t.id AND ra.role = p.role AND ra.is_active
     );
    IF roleless IS NOT NULL THEN
        RAISE EXCEPTION 'no active % role assignment for: %',
              (SELECT role FROM _params), roleless
              USING HINT = 'grant the role first: scripts/db/grant_comp.sh --role …';
    END IF;
END $$;

\echo '── profiles before ──'
SELECT t.email, ra.id AS role_assignment_id, ra.role,
       pp.id AS profile_id, pp.license_number, pp.specialty, pp.practice_name,
       pp.verification_status
FROM _targets t
JOIN _params p ON true
JOIN user_role_assignments ra ON ra.user_id = t.id AND ra.role = p.role AND ra.is_active
LEFT JOIN professional_profiles pp ON pp.role_assignment_id = ra.id
ORDER BY t.id;

INSERT INTO professional_profiles (
    role_assignment_id, license_number, specialty, practice_name,
    telemedicine_available, verification_status, created_at, updated_at
)
SELECT ra.id,
       NULLIF(p.license, ''),
       NULLIF(p.specialty, ''),
       NULLIF(p.practice, ''),
       false,
       'unverified',
       now(), now()
FROM _targets t
JOIN _params p ON true
JOIN user_role_assignments ra ON ra.user_id = t.id AND ra.role = p.role AND ra.is_active
ON CONFLICT (role_assignment_id) DO UPDATE
SET license_number = COALESCE(EXCLUDED.license_number, professional_profiles.license_number),
    specialty      = COALESCE(EXCLUDED.specialty,      professional_profiles.specialty),
    practice_name  = COALESCE(EXCLUDED.practice_name,  professional_profiles.practice_name),
    updated_at     = now();

\echo ''
\echo '── profiles after ──'
SELECT t.email, ra.id AS role_assignment_id, ra.role,
       pp.id AS profile_id, pp.license_number, pp.specialty, pp.practice_name,
       pp.verification_status, pp.updated_at
FROM _targets t
JOIN _params p ON true
JOIN user_role_assignments ra ON ra.user_id = t.id AND ra.role = p.role AND ra.is_active
LEFT JOIN professional_profiles pp ON pp.role_assignment_id = ra.id
ORDER BY t.id;

\if :dry_run
  \echo ''
  \echo '*** DRY RUN — rolling back. Re-run with -v dry_run=0 to apply. ***'
  ROLLBACK;
\else
  COMMIT;
  \echo ''
  \echo '*** APPLIED. ***'
\endif
