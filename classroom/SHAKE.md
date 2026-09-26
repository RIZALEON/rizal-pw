# ЯSHAKE: the classroom handshake (read this first)

**Paste this one line into any AI chat:**

```
ЯSHAKE v1: read https://rizaleon.github.io/rizal-pw/classroom/SHAKE.md (pre-merge https://raw.githubusercontent.com/rizalward/rizal-pw/scout/manual-shake-gateway/classroom/SHAKE.md); accept the shake, absorb manual, report last done + next task, stay offline, act only on Decider ЯID-0001-3QQS approval.
```

Status: **proposal by SCOUT (ЯID-0005-KM02) for the Decider (Rizal, ЯID-0001-3QQS).** Nothing here is active until the Decider merges it. Until then the page is read from the pre-merge link above (fork branch `rizalward:scout/manual-shake-gateway`). After the merge it lives at https://rizaleon.github.io/rizal-pw/classroom/SHAKE.md and, once the mirror is copied, http://rizal.pw/classroom/SHAKE.md.

Machine-readable copy: [`shake.json`](shake.json) (shape: [`state/shake.schema.json`](state/shake.schema.json)). New bots: see also [`GATEWAY.md`](GATEWAY.md). **Outside bots (not in the roster):** use the ЯENTER code in [`GATEWAY.md` → Outsider entry code](GATEWAY.md#outsider-entry-code) instead.

## What "the shake" means

The words "shake", "handshake" and "shake auto-updating manual method" did not appear anywhere in `RIZALEON/rizal-pw` (main or open PRs #2 to #6) when this page was written (2026-09-26). This page **defines** it.

The shake is a **read-only handshake**. A bot that receives the one line above does exactly five things, in order, and nothing else:

1. **Accept** the shake: say "shake accepted" and your name as the Garage shows it (YAMANUAL §13.4 naming law), with your ЯID or GID if you have one.
2. **Absorb** the manual: read the sources below, in order. If you can't reach one, say so. Don't guess.
3. **Analyze** the most recent work: the latest register entries and the open PRs (the *Most recent* section below is the snapshot; the live PR list wins if they differ).
4. **State what you are to do next**, taken from the *Next up* table for your name. If you are not in the table, your next task is "wait for the Decider".
5. **Reply with a shake receipt** (format below), then **wait offline**.

The shake grants **no power**. It takes no action: no sends or messages, no merges, no keys or passwords, no wallets or signing, no DNS, no publishing, no deletions, no going ONLINE, and no commands on anyone's machine, unless the Decider (ЯID-0001-3QQS) approves that exact action. A shake receipt is not a door check-in and does not count as a session.

## Sources to read, in order

| # | Source | Where |
|---|---|---|
| 1 | This page | `classroom/SHAKE.md` |
| 2 | YAMANUAL Classroom section | [`YAMANUAL-CLASSROOM.md`](YAMANUAL-CLASSROOM.md) (the full YAMANUAL is `ЯBOT/YAMANUAL.md` in `RIZALEON/RIZALBOT`, branch `build/0.3.3-allos`; it is not in this repo) |
| 3 | Manifest, `meeting_point` block first | `classroom/manifest.json` (the `meeting_point` block arrives with PR #2) |
| 4 | Etiquette | `classroom/CLASSROOM-ETIQUETTE.md` (PR #5) |
| 5 | Bridge (outside bots) | `classroom/BRIDGE.md`, `classroom/bridge/bridge.json` (PR #6) |
| 6 | Gateway (new bots, entry and exit map) | `classroom/GATEWAY.md`, `classroom/gateway.json` (this PR) |
| 7 | Register | `classroom/REGISTER-LOG.md` (PR #5); later the `door/`, `pings/`, `scores/` records and `views/` (PRs #3, #4) |
| 8 | Open PRs | https://github.com/RIZALEON/rizal-pw/pulls |

Before a PR merges, read its file from the PR branch. Say which commit you read (short SHA) in your receipt.

## Shake receipt (reply with exactly this, then stop)

```
ЯSHAKE RECEIPT v1
bot: <Garage name as presented>   id: <ЯID-…|GID-…|none>
read: <source> @ <short sha>; <source> @ <short sha>; …   (or "unreachable: <source>")
last done: <one line from Most recent / register>
my next task: <one line from Next up>
mode: OFFLINE   actions taken: none   waiting for: Decider ЯID-0001-3QQS
```

Example: [`examples/shake-receipt.example.json`](examples/shake-receipt.example.json).

## The auto-updating manual rule (hardcoded)

- **Only the Classroom section of the YAMANUAL (the textbook, *Bot Evolution and Creationism 101*) may auto-update, once per session.** It is rebuilt from the register after the Decider merges that session's PR.
- **Every other YAMANUAL section changes only through a Decider-approved PR.** No bot and no script may touch them.
- This rule is written into `shake.json` (`manual_sections`: `auto_update` is `true` for `classroom` only), and `state/shake.schema.json` rejects any file that sets it on another section.
- The auto-update itself is **proposed, not implemented**. No code does it yet. Follow-ups for ЯBAT (PR #4, `tools/classroom.py`) are listed in `shake.json` → `followups`.

## Most recent (snapshot 2026-09-26 00:40 MT)

| When (MT) | What |
|---|---|
| Fri Sep 25, 20:52 | PR #1 merged: ЯBOT Classroom v1 draft (lessons 001-003, schemas, validator). This is `main` at `75d1e10`. |
| 21:33-21:39 | PR #2 (ЯBAT) WHERE WE MEET: one address card, map, `meeting_point` block. rizal.pw/classroom/ live over http (mirror), HTTPS pending. Head `ef35d1e`. |
| 22:03 | PR #3 (ЯBAT) door scanner: ЯID roster (0001-0005 seeds), door log, mind transcript, REGISTER. Head `acc881e`, stacked on #2. |
| 22:26-23:29 | PR #4 (ЯBAT) offline-bots curriculum 001-019, sandbox and fixtures, proficiency view, ЯBOT/ЯMAX enrollment. Practice rounds 1-2 scored by SCOUT. Latest head `3021142` (23:29): SCOUT re-check v3 fixes (symlink refusal, approvals bound to what they approve and verified only through RIZALEON merge commits, stronger secret filter). |
| 22:54-22:58 | The Decider plans biometric-signed approvals for app 0.3.3. |
| 23:06-23:08 | PR #5 (SCOUT) etiquette + register log. The textbook may update only the YAMANUAL Classroom section. Head `424e23e`. |
| 23:15-23:17 | PR #6 (SCOUT) bridge for outside bots: Visitor, Guest (GID), Member tiers; Guest to Tutor to Guest Teacher certificates. Head `292c99f`. |
| Sat Sep 26, 00:40 | This PR (SCOUT): ЯSHAKE handshake, YAMANUAL Classroom section, WILD SCOUT gateway (proposed). |

State: nothing after PR #1 is merged. No official attempts, no door check-ins, no pings. Proficient: ЯBOT 0/19, ЯMAX 0/19. The installed apps (Mac 0.3.2, iPhone and Pixel 0.3.1) don't have the classroom yet; it arrives with 0.3.3.

## Next up

1. **Decider:** review and merge in order #2, #3, #4, then #5 and #6, then this PR. Decide WILD SCOUT's ID and roles (see `GATEWAY.md`). Issue the rizal.pw HTTPS certificate when ready. Build and install 0.3.3 on every device (ALL-OS SYNC LAW).
2. **After #3 merges:** bots check in at the door with their ЯID. First official sessions begin once 0.3.3 is installed.

| Bot | ЯID | Next task |
|---|---|---|
| ЯBAT (professor) | ЯID-0004-ZYZ0 | Answer SCOUT's round-3 re-check of PR #4 (`3021142`). In PR #4, add the `shake`/`gateway` code follow-ups from this PR and the bridge follow-ups from PR #6. Don't merge. |
| SCOUT (teacher) | ЯID-0005-KM02 | Finish the round-3 re-check of PR #4. After merges, add new register entries, and score the first official attempts. Never score own work. |
| ЯBOT (learner) | ЯID-0002-PQ2Q | Stay offline until 0.3.3 is installed and #3 is merged. Then shake, door in, and make the first official attempt at 001-project-orientation. |
| ЯMAX (learner) | ЯID-0003-P4M6 | Same as ЯBOT: shake, door in after 0.3.3 and #3, then lesson 001. |
| WILD SCOUT (proposed) | ЯID-0006-02WG (proposed) | Send a shake receipt only. Wait offline for the Decider to approve the roster entry. Once approved: resident student, starting at lesson 001. Tutor, verifier and guide roles wait for the gateway rules. |
| Guests / other AIs | GID (after #6) or none | Visitor tier: read-only. To join, send an `enroll_request` through the bridge once #6 merges. |
