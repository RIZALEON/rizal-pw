#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 <<'PY'
import base64, zlib
from pathlib import Path
parts = "".join(Path(f"classroom/BRIDGE.md.chunk{i}.z64").read_text() for i in range(3))
Path("classroom/BRIDGE.md").write_bytes(zlib.decompress(base64.b64decode(parts)))
print("OK: wrote classroom/BRIDGE.md")
PY
