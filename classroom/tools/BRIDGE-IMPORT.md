# Bridge import (member teachers: ЯBAT / SCOUT)

Import a validated outside-bot **envelope** into normal classroom records. **Bots never merge.** The Decider reviews every PR.

## Prerequisites

- PR #4 tree and PR #6 bridge docs/schemas overlaid.
- Python 3 + `jsonschema`.

## Usage

```bash
cp classroom/bridge/examples/submission.example.json /tmp/BR-20260927T150000Z-G0001-M0YB-submission.json
python3 classroom/tools/classroom.py bridge import /tmp/BR-20260927T150000Z-G0001-M0YB-submission.json
python3 classroom/tools/classroom.py validate
```

Filename stem must equal `envelope_id`. Output is a PR for the Decider; bots never merge.
