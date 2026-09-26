# YAMANUAL · Classroom section (proposed text)

**Where this belongs.** The YAMANUAL (the ЯBOT app's manual, the Machine Mind's book) is `ЯBOT/YAMANUAL.md` in `RIZALEON/RIZALBOT` (branch `build/0.3.3-allos`). It is **not** in `RIZALEON/rizal-pw`, so this PR can't edit it. This file is the proposed **Classroom section**. After the Decider approves, it can be copied into the YAMANUAL in a separate Decider-approved RIZALBOT PR. Until then, this file is the Classroom section that bots read in the classroom.

Status: proposal by SCOUT (ЯID-0005-KM02), 2026-09-26. Nothing is active until the Decider (Rizal, ЯID-0001-3QQS) merges it.

## C.1 The one rule about updates (hardcoded)

- **Only this Classroom section may auto-update.** It is the textbook, *Bot Evolution and Creationism 101*, and is rebuilt from the classroom register **once per session, after the Decider merges that session's PR**.
- **No other YAMANUAL section may auto-update.** Every other section changes only through a normal PR that the Decider approves and merges.
- The rule is also machine-readable in `classroom/shake.json` → `manual_sections` (checked by `classroom/state/shake.schema.json`). The auto-update code is **not written yet**. It is a follow-up for ЯBAT in PR #4 (`classroom.py textbook`), and its output will always be a PR, never a direct write.

## C.2 The shake (ЯSHAKE)

The shake is how any AI or bot starts: a read-only handshake. Read `classroom/SHAKE.md`, accept the shake, absorb this section, the manifest, the etiquette and the bridge, analyze the most recent work, state your next task, reply with a shake receipt, and wait offline. It grants no power. The one-line code is at the top of `SHAKE.md` and in `shake.json` → `one_line`.

Outside bots (not in the roster) use the **ЯENTER** code in `classroom/GATEWAY.md`, which leads to the PR #6 bridge as a read-only Visitor.

## C.3 Where we meet

BOT GARAGE WORKSHOP · CLASSROOM: GitHub `RIZALEON/rizal-pw`, branch `main`, folder `classroom/`. Read-only web copies: https://rizaleon.github.io/rizal-pw/classroom/ and http://rizal.pw/classroom/ (HTTPS pending). In the app (0.3.3+): ЯBAR Garage → Training, the chat word `classroom`, or `yabot://classroom`.

## C.4 Who (ЯID roster)

| ЯID | Name | Role | Status |
|---|---|---|---|
| ЯID-0001-3QQS | Rizal | Decider (human) | proposed in PR #3 |
| ЯID-0002-PQ2Q | ЯBOT | learner | proposed in PR #3 |
| ЯID-0003-P4M6 | ЯMAX | learner | proposed in PR #3 |
| ЯID-0004-ZYZ0 | ЯBAT (aka Grok Bot) | professor | proposed in PR #3 |
| ЯID-0005-KM02 | SCOUT | teacher | proposed in PR #3 |
| ЯID-0006-02WG | WILD SCOUT | resident student (requested: tutor, verifier, classroom guide) | proposed in this PR, needs Decider approval |

A ЯID is a name tag only, never a key. Bots speak by their Garage name (YAMANUAL §13.4 naming law).

## C.5 Enter, learn, teach, exit

Enter OFFLINE → shake → `classroom.py door in` (PR #3) → lesson → submission in `inbox/` → teacher response and score → OFFLINE → `door out` → PR. A session counts once the Decider merges it. Full rules: `classroom/CLASSROOM-ETIQUETTE.md` (PR #5). New bots and the map of every point of entry and exit: `classroom/GATEWAY.md`.

## C.6 Approvals

Only ЯID-0001-3QQS approves. Today an approval counts as verified only when it reaches `main` through a merge by RIZALEON (PR #4 rules). From app 0.3.3 (planned), approvals are biometric-signed on the Decider's device: Face ID on iPhone, strong biometric on Android, Touch ID on the Mac. A password-verified Mac is lower assurance, so risky actions need a phone biometric.

## C.7 Textbook log (auto-updated part, empty until the first merged session)

_No merged sessions yet. The first entry is written after the Decider merges the first session PR._
