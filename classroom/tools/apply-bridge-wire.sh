#!/usr/bin/env bash
# Apply classroom.py bridge wire if not already present.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/classroom/tools/classroom.py"
PATCH="$ROOT/classroom/tools/classroom-bridge-wire.patch"
if grep -q 'import bridge_ops' "$PY" 2>/dev/null; then
  echo "OK: classroom.py already wired for bridge_ops"
  exit 0
fi
patch -p1 -d "$ROOT" < "$PATCH"
echo "OK: applied classroom-bridge-wire.patch"
