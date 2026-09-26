#!/usr/bin/env bash
# Apply the bridge CLI wire to classroom.py (from repo root).
set -euo pipefail
patch -p1 < classroom/tools/classroom-bridge-wire.patch
echo "Applied. Next: python3 classroom/tools/classroom.py bridge import --help"
