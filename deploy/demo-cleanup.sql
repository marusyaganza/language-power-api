-- Daily cleanup of the public demo's database, run by
-- .github/workflows/demo-cleanup.yml with psql in one transaction:
--   psql --single-transaction -v ON_ERROR_STOP=1 -v ttl_hours=24 -f deploy/demo-cleanup.sql
--
-- The app already deletes expired accounts at each signup (auth.service.signup);
-- this catches the days without signups. Prints two lines: the accounts deleted,
-- then the old daily search counts deleted.

-- Accounts older than ACCOUNT_TTL_HOURS, with everything they own (words,
-- examples, progress, game settings, search counts: ON DELETE CASCADE).
WITH deleted AS (
    DELETE FROM users
    WHERE created_at < now() - make_interval(hours => :ttl_hours)
    RETURNING 1
)
SELECT count(*) FROM deleted;

-- Everyone's daily search counts, kept a week in case a day needs looking into.
-- Days are UTC days, whatever the server's time zone.
WITH deleted AS (
    DELETE FROM daily_search_counts
    WHERE day < (now() AT TIME ZONE 'UTC')::date - 7
    RETURNING 1
)
SELECT count(*) FROM deleted;
