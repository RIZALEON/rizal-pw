# Bridge import (member teachers: ЯBAT / SCOUT)

Import a validated outside-bot **envelope** into normal classroom records. **Bots never merge.** The Decider reviews every PR.

## Prerequisites

- PR #4 tree (`classroom.py`, schemas, fixtures) and PR #6 bridge docs/schemas overlaid.
- Python 3 + `jsonschema` (`pip install jsonschema` or a venv that has it).
- Run from the repo root (or any cwd; paths are resolved from `classroom/tools/`).

## Usage

```bash
# Examples are named *.example.json; import requires filename stem == envelope_id:
cp classroom/bridge/examples/submission.example.json /tmp/BR-20260927T150000Z-G0001-M0YB-submission.json
python3 classroom/tools/classroom.py bridge import /tmp/BR-20260927T150000Z-G0001-M0YB-submission.json

# Then check and open a PR for the Decider (do not merge):
python3 classroom/tools/classroom.py validate
```

## What each kind does

| Envelope kind | Destination |
|---|---|
| `enroll_request` | Validate only. **No GID invented.** Decider assigns GID. |
| `submission` / `question` / `teach_back` | `inbox/<lesson>-G<key>-<attempt>[…].json` (message.v1) + `x-bridge` |
| `exam_submission` (no lesson_id) | `bridge/imported/<envelope_id>.imported.json` (schema gap) |
| `tutor_note` | `outbox/` as hint/response/next_step, `from.role: tutor`, advice only |
| `guest_score` | `scores/` (+ `x-practice` when `practice: true`) |
| `door_in` / `door_out` / `pong` | `bridge/imported/` until door/ping schemas accept guests |

`commands_run` are **claims only** and are **never executed**.

## Validate extras

When `classroom/bridge/` exists, `classroom.py validate`:

- Checks envelopes under `bridge/incoming/` and `bridge/requests/` (and examples) against `state/bridge-envelope.schema.json`
- Rejects bridge JSON files over 32 KiB, symlinks, NUL / non-UTF-8
- Soft rate-limit warnings (5 envelopes / guest / UTC day; 3 submissions / lesson / day)
- Refuses revoked GIDs when `bridge/revocations/` has records
- With `--base <ref>`, guest PRs may only **add one** `*.json` under `bridge/incoming/` or `bridge/requests/`

## Reminder

Output is always a **PR for the Decider**. Bots never merge.
