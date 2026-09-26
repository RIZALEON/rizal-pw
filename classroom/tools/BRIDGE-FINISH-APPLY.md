# Bridge finish — Decider apply steps

After checking out `yabat/classroom-bridge-finish`:

```bash
bash classroom/tools/assemble-bridge-md.sh
bash classroom/tools/apply-bridge-wire.sh
patch -p1 < classroom/state/message-tutor-role.patch   # optional; adds role "tutor"

python3 -m venv .venv && . .venv/bin/activate && pip install jsonschema
python3 classroom/tools/classroom.py validate

cp classroom/bridge/examples/submission.example.json \
  /tmp/BR-20260927T150000Z-G0001-M0YB-submission.json
python3 classroom/tools/classroom.py bridge import \
  /tmp/BR-20260927T150000Z-G0001-M0YB-submission.json
```

Readable impl (agent box): `/workspace/rizal-pw-bridge-finish/classroom/tools/bridge_ops_impl.source.py`
(on branch: assemble from `bridge_ops_impl.chunk*.b64` via the assembler in `bridge_ops_impl.py`).

**Do not merge without Decider. Bots never merge.**
