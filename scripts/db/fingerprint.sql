-- ALAFIA DB parity fingerprint.
--
-- Emits one line per table: schema, table, row count, content hash — plus a
-- schema fingerprint and the alembic revision. Run this against PROD and DEV;
-- identical output means the two databases are logically identical.
--
-- Determinism notes (why the SET lines matter): the content hash is built from
-- each row rendered as text, so anything that changes text rendering changes the
-- hash. TimeZone, DateStyle and extra_float_digits all do. Pinning them here is
-- what makes the same data hash the same on two different servers.
--
-- Read-only: no temp tables, no writes. Safe to run against production.

-- Invoke with:  psql -q -A -t -F '|' -v schemas=public,identity -f fingerprint.sql
-- (formatting lives in the flags so this file stays pure SQL and diffs cleanly)

SET TimeZone = 'UTC';
SET DateStyle = 'ISO, YMD';
SET extra_float_digits = 3;

-- ── 1. Per-table row count + order-independent content hash ──────────────
-- query_to_xml lets one statement aggregate over every table without plpgsql.
SELECT
  'TABLE|' || t.table_schema || '|' || t.table_name || '|' ||
  COALESCE((xpath(
    '/row/c/text()',
    query_to_xml(
      format('SELECT count(*) AS c FROM %I.%I', t.table_schema, t.table_name),
      false, true, '')
  ))[1]::text, '0') || '|' ||
  COALESCE((xpath(
    '/row/h/text()',
    query_to_xml(
      format(
        'SELECT COALESCE(md5(string_agg(rh, %L ORDER BY rh)), %L) AS h '
        'FROM (SELECT md5(x.*::text) AS rh FROM %I.%I x) s',
        '', 'EMPTY', t.table_schema, t.table_name),
      false, true, '')
  ))[1]::text, 'EMPTY')
FROM information_schema.tables t
WHERE t.table_schema = ANY (string_to_array(:'schemas', ','))
  AND t.table_type = 'BASE TABLE'
ORDER BY t.table_schema, t.table_name;

-- ── 2. Schema fingerprint (column shape of every table) ──────────────────
SELECT 'SCHEMA|' || md5(string_agg(sig, E'\n' ORDER BY sig))
FROM (
  SELECT table_schema || '.' || table_name || '.' || column_name || ':' ||
         data_type || ':' || is_nullable || ':' ||
         COALESCE(column_default, '-') || ':' ||
         COALESCE(character_maximum_length::text, '-') AS sig
  FROM information_schema.columns
  WHERE table_schema = ANY (string_to_array(:'schemas', ','))
) c;

-- ── 3. Alembic revision (the migration state both sides must agree on) ───
SELECT 'ALEMBIC|' || COALESCE(
  (SELECT string_agg(version_num, ',' ORDER BY version_num) FROM public.alembic_version),
  'NONE');
