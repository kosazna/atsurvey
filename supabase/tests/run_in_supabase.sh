#!/usr/bin/env bash
# Run the database tests inside the running local Supabase container (real Postgres 17 +
# PostGIS), in a throwaway database. The app database is never touched.
#
#   bash supabase/tests/run_in_supabase.sh        (after `npx supabase start`)
#
# CI uses run.sh on a plain PostgreSQL cluster instead; both apply the same shim and tests.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
DB=atsurvey_rls_test
CONTAINER="$(docker ps --format '{{.Names}}' | grep -m1 '^supabase_db_' || true)"
[[ -n "$CONTAINER" ]] || { echo "local Supabase is not running: npx supabase start"; exit 1; }

PSQL=(docker exec -i "$CONTAINER" psql -U postgres -X -q -v ON_ERROR_STOP=1)
cleanup() { "${PSQL[@]}" -d postgres -c "drop database if exists $DB" >/dev/null 2>&1 || true; }
trap cleanup EXIT

"${PSQL[@]}" -d postgres -c "drop database if exists $DB" -c "create database $DB" >/dev/null 2>&1
echo "== applying shim and migrations"
{
  cat "$HERE/00_supabase_shim.sql"
  for f in "$ROOT"/migrations/*.sql; do cat "$f"; echo; done
} | "${PSQL[@]}" -d "$DB" >/dev/null 2>"${TMPDIR:-/tmp}/rls-apply.err" || {
  grep -v NOTICE "${TMPDIR:-/tmp}/rls-apply.err"; exit 1; }

echo "== running tests"
set +e
OUT="$("${PSQL[@]}" -d "$DB" < "$HERE/rls_test.sql" 2>&1)"
STATUS=$?
set -e
echo "$OUT" | sed -e 's/^psql:[^:]*:[0-9]*: //' -e 's/^NOTICE:  //' | grep -E 'ok - |ERROR|ALL TESTS|DETAIL|HINT|CONTEXT' || true
PASSED=$(grep -c 'ok - ' <<<"$OUT" || true)
FAILED=$(grep -c 'not ok - ' <<<"$OUT" || true)
echo "== passed: $((PASSED - FAILED))  failed: $FAILED"
[[ $STATUS -eq 0 && $FAILED -eq 0 ]] && grep -q 'ALL TESTS PASSED' <<<"$OUT" || { echo "== FAILED"; exit 1; }
