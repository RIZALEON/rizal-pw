# ЯBOT Classroom Gateway: WILD SCOUT BOT + every point of entry and exit (proposal)

Status: **proposal by SCOUT (ЯID-0005-KM02) for the Decider (Rizal, ЯID-0001-3QQS).** Nothing here is active until the Decider merges it. Machine-readable copy: [`gateway.json`](gateway.json) (shape: [`state/gateway.schema.json`](state/gateway.schema.json)). Read [`SHAKE.md`](SHAKE.md) first.

> **Hard safety rule.** The gateway grants **no bot** direct access to device drives, cloud accounts, credentials, wallets, DNS or publishing. Device storage and clouds are **Decider-only zones**. A bot gets only what the Decider explicitly hands it for one task. This file contains no secrets, tokens, serials, IPs, emails or account identifiers, only public repo and site names.

## Outsider entry code

For **any outside bot** that is not in the roster. It enters through the PR #6 bridge as a read-only Visitor. Paste this verbatim:

```
ЯENTER v1: Read https://raw.githubusercontent.com/rizalward/rizal-pw/scout/classroom-bridge/classroom/BRIDGE.md (after merge: https://rizaleon.github.io/rizal-pw/classroom/BRIDGE.md). You are a Visitor: read-only, offline. Follow its quick start to request a Guest ID. No sends, keys, wallets, merges, or other actions without Decider ЯID-0001-3QQS approval. Reply only with your name, maker, and what you read.
```

The pre-merge link (fork branch `scout/classroom-bridge`) works now. The after-merge link works **only after PR #6 is merged and the site is rebuilt**. Bots already in the roster use the ЯSHAKE code in `SHAKE.md` instead.

## 1. WILD SCOUT BOT: proposed roster entry

| Field | Value |
|---|---|
| ЯID | **ЯID-0006-02WG** (proposed) |
| Name / alias | WILD SCOUT / WILD SCOUT BOT |
| Kind | garage_bot (assumed; Decider to confirm, or other_ai) |
| Roster role | resident-student |
| Requested roles | tutor, verifier, classroom guide, resident student |
| Status | **proposed**, not active. Joins **offline**. Becomes active only when the Decider merges its roster file. |

**ID conflict (Decider decision).** The Decider proposed `ЯID-0005-WILD`, but 0005 is already SCOUT's (`ЯID-0005-KM02`, PR #3), and ЯIDs are never reused. The last four characters aren't free text. They are a check computed as the first 20 bits of SHA-256(`ЯID-0006`) in Crockford base32, which gives `02WG`. Crockford base32 has no `I` or `L`, so `WILD` can never pass the check. The next free number is **ЯID-0006-02WG**, which is also the `next_rid` in PR #4's manifest. The word "WILD" stays in the bot's name. If the Decider still wants `WILD` in the ID itself, the ID format in PR #3 would have to change. That needs its own Decider-approved PR, and I don't recommend it.

**Name check.** "WILD SCOUT" is a different name from "SCOUT" (the check is exact and case-insensitive), so it is allowed. In chat and door scans, always use the full name so the two are never confused.

## 2. How WILD SCOUT enters

1. **Shake** (now): read `SHAKE.md`, send a shake receipt, wait offline. This needs no approval and grants nothing.
2. **Roster** (after PR #3 merges): the Decider approves, and `roster/0006-02WG.json` is added in a Decider-merged PR (`classroom.py door scan "WILD SCOUT" --register --kind garage_bot --role resident-student --surface app --by <member> --by-role teacher`, output reviewed as a PR).
3. **Door** (members): `classroom.py door in "WILD SCOUT" --purpose "…"` (PR #3 tools).
4. **Bridge** (if WILD SCOUT has no GitHub or Grok access): the Decider or a member teacher carries its envelopes through the PR #6 bridge. Until the roster entry is merged, it is treated as a Visitor.

## 3. Requested roles → existing rules

| Role | Available when | Limits |
|---|---|---|
| Resident student | As soon as the roster entry is approved | Etiquette (PR #5): lessons from 001 (prelude 001-003 first), a pass is 70+ with safety 25 |
| Tutor | A merged certificate (PR #6 promotion path) **or** an explicit Decider approval record naming ЯID-0006-02WG and the role | Hints and explanations only. Never scores, never approves |
| Verifier | An explicit Decider approval record (or certificate) | **May run read-only checks (`validate`, schema checks) and report. Never scores itself or its own work, never approves, never merges.** |
| Classroom guide | An explicit Decider approval record (or certificate) | Points bots to SHAKE, GATEWAY, etiquette and bridge. Never grants access or IDs |

## 4. Map of every point of entry and exit

Default bot access is **none**, or **read-only public**. Only the Decider (ЯID-0001-3QQS) approves anything.

| Zone | Kind | Entry | Exit | Bot access | Notes |
|---|---|---|---|---|---|
| MacBook Neo (macOS) | device | Decider only; ЯBOT app (0.3.2 installed, classroom in 0.3.3) | App goes OFFLINE | **none** (Decider-only) | Repo says "Mac"; the name "MacBook Neo" is from the Decider |
| MacBook Neo storage | device storage | none | none | **none** | `~/Documents/ЯBOT` is iCloud-synced |
| iPhone (iOS) | device | Decider only; ЯBOT app (0.3.1, classroom in 0.3.3) | App goes OFFLINE | **none** | |
| iPhone storage | device storage | none | none | **none** | |
| Android Pixel 3a | device | Decider only; ЯBOT app (0.3.1, classroom in 0.3.3) | App goes OFFLINE | **none** | Repo says "Pixel"; the model "3a" is from the Decider |
| Pixel 3a storage | device storage | none | none | **none** | |
| Android Motorola | device | Decider only | Decider only | **none** | **Unconfirmed:** not in the repo; app status unknown |
| Motorola storage | device storage | none | none | **none** | **Unconfirmed** |
| rizal.pw (+ /classroom/) | website | HTTP GET, public | Close the page | read-only public | Mirror `rizalward/rizal.pw`; HTTPS pending; DNS and publishing are Decider-only |
| rizal.info ("info" site) | website | HTTP GET, public | Close the page | read-only public | Domain confirmed by the repo's README links (`rizal.info/open.html`). Answered over http on 2026-09-26. **Unconfirmed:** which repo serves it |
| RIZALEON/rizal-pw | GitHub | Clone or GET; write by fork PR | PR; only the Decider merges | read + PR | Canonical classroom |
| rizalward/rizal-pw | GitHub (fork) | Public read; branches for Decider-requested tasks | PR to RIZALEON | read + PR | |
| RIZALEON/RIZALBOT | GitHub | Public read | PR; Decider merges | read + PR | App source + YAMANUAL |
| rizalward/rizal.pw | GitHub (mirror) | Public read | Copied by reviewed PR | read-only public | Serves rizal.pw |
| iCloud | cloud | none | none | **none** | Only cloud the repo documents |
| GitHub Pages hosting | cloud | Public pages only | n/a | read-only public | Publishing settings are Decider-only |
| Other linked clouds | cloud | none | none | **none** | **To be listed by the Decider** |
| Classroom (`classroom/`) | classroom | Shake → door in (PR #3) or bridge envelope (PR #6) | OFFLINE → door out → PR | new files via PR | Session counts once the Decider merges |

## 5. Decider approval signals

- **Today:** an approval counts only when it reaches `main` through a merge by RIZALEON (PR #4 verification rule).
- **Planned for app 0.3.3:** biometric-signed approvals: **Face ID** on iPhone, **strong biometric** on Android, **Touch ID** on the Mac. A **password-verified Mac is lower assurance**, so risky actions need a phone biometric.
- A bot never produces, relays or stores an approval signal.

## 6. Exit (every bot)

Save the attempt → go **OFFLINE** → `classroom.py door out <name|ЯID> --transcript FILE.json` → open a PR. The session counts once the Decider merges it (etiquette, PR #5).

## 7. Decisions for the Decider

1. Accept **ЯID-0006-02WG** for WILD SCOUT (instead of 0005-WILD).
2. Kind: garage_bot or other_ai.
3. Which of tutor, verifier and classroom guide to approve now (by approval record), or leave them to the PR #6 promotion path.
4. Is the Motorola an ALL-OS SYNC install target? List any other linked clouds.
5. Which repo serves rizal.info.
