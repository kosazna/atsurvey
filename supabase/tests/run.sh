#!/usr/bin/env bash
# Run the database tests against a throwaway local PostgreSQL cluster.
#
#   supabase/tests/run.sh
#
# Env:
#   PG_BIN       PostgreSQL bin dir (default: /usr/lib/postgresql/16/bin or `pg_config --bindir`)
#   PGTEST_DIR   working dir for the cluster (default: mktemp -d)
#   PGTEST_PORT  port (default: 54399)
#   KEEP_CLUSTER=1  leave the cluster running for inspection
#
# Requires PostGIS for the same major version (e.g. apt-get install postgresql-16-postgis-3).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

if [[ -z "${PG_BIN:-}" ]]; then
  if [[ -x /usr/lib/postgresql/16/bin/postgres ]]; then
    PG_BIN=/usr/lib/postgresql/16/bin
  else
    PG_BIN="$(pg_config --bindir)"
  fi
fi
PORT="${PGTEST_PORT:-54399}"
WORK="${PGTEST_DIR:-$(mktemp -d -t atsurvey-pgtest-XXXXXX)}"
mkdir -p "$WORK"
DATA="$WORK/data"
SOCK="$WORK/sock"
LOG="$WORK/postgres.log"

# initdb/postgres refuse to run as root: drop to the postgres user when needed.
RUN=()
if [[ "$(id -u)" == "0" ]]; then
  id postgres >/dev/null 2>&1 || useradd --system --no-create-home postgres
  chown -R postgres "$WORK"
  chmod 755 "$WORK"
  RUN=(runuser -u postgres --)
fi

cleanup() {
  if [[ "${KEEP_CLUSTER:-0}" != "1" ]]; then
    "${RUN[@]}" "$PG_BIN/pg_ctl" -D "$DATA" -m immediate stop >/dev/null 2>&1 || true
    rm -rf "$WORK"
  else
    echo "cluster kept: psql -h $SOCK -p $PORT -U postgres postgres"
  fi
}
trap cleanup EXIT

rm -rf "$DATA"
"${RUN[@]}" mkdir -p "$SOCK"
"${RUN[@]}" "$PG_BIN/initdb" -D "$DATA" -U postgres -A trust >/dev/null
"${RUN[@]}" "$PG_BIN/pg_ctl" -D "$DATA" -l "$LOG" -w \
  -o "-p $PORT -k $SOCK -c listen_addresses=''" start >/dev/null

PSQL=("$PG_BIN/psql" -h "$SOCK" -p "$PORT" -U postgres -d postgres -X -v ON_ERROR_STOP=1 -q)

echo "== applying shim"
"${PSQL[@]}" -f "$HERE/00_supabase_shim.sql" >/dev/null

for f in "$ROOT"/migrations/*.sql; do
  echo "== applying $(basename "$f")"
  "${PSQL[@]}" -f "$f" >/dev/null
done

echo "== running tests"
OUT="$WORK/test-output.txt"
set +e
"${PSQL[@]}" -f "$HERE/rls_test.sql" >"$OUT" 2>&1
STATUS=$?
set -e
sed -e 's/^psql:[^:]*:[0-9]*: //' -e 's/^NOTICE:  //' "$OUT"

PASSED=$(grep -c 'ok - ' "$OUT" | tr -d ' ' || true)
FAILED=$(grep -c 'not ok - ' "$OUT" | tr -d ' ' || true)
PASSED=$((PASSED - FAILED))
echo "== passed: $PASSED  failed: $FAILED"
if [[ $STATUS -ne 0 || $FAILED -ne 0 ]] || ! grep -q 'ALL TESTS PASSED' "$OUT"; then
  echo "== FAILED"
  exit 1
fi
