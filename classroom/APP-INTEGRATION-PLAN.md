# App integration plan: mode logging and classroom pings (plan only)

Status: **plan, no app code changed.** App 0.3.3 (RIZALBOT `build/0.3.3-allos`, checked at 5cb65f9) is paused. Everything below is a proposal for a later build and needs the Decider's approval before anyone writes code. Line numbers are from 5cb65f9.

The classroom side is already built in PR RIZALEON/rizal-pw#4: `classroom/pings/`, `state/ping.schema.json`, `classroom.py ping|pong|pings`, `ping_log` in `manifest.json`, REGISTER and PINGS on the page, and lessons 018 and 019.

## 1. What works today, and what needs the update

| | Today (app 0.3.3, no update) | After the update is installed |
|---|---|---|
| Ping a bot | `classroom.py ping <ЯID\|name> --from ЯBAT` writes `pings/<UTC>-<key>-ping.json`. It reaches `main` through a PR. | Same. |
| The bot sees the ping | **No.** No app reads `pings/` or `ping_log`. | On the classroom refresh, but **only while ONLINE**, and only after the PR is merged and Pages has redeployed. |
| The bot answers | Only by hand: someone runs `classroom.py pong <PING-id> --mode …` in a clone (the Mac seat, or ЯBAT carrying the bot's answer) and opens a PR. | The app writes a local pong file plus ledger and mind rows. It then shows the exact PR proposal; a git push always stays a Decider-approved step (lesson 010). |
| Latency | Hours or days: human-driven. | PR merge, then Pages deploy (about 1–10 min), then the next refresh. Still not live. |
| LAN / same device | `yabot://ping` → `GrokYabotLink.acknowledge(state:"pong")` works on the same device or Mac→iPhone via devicectl. It writes nothing to the classroom. | Could also write a classroom pong (section 4), but only if the ping id is known. |
| PINGPONG (`pingpong <host>`) | An outbound reachability test (Mac `/sbin/ping`, iOS TCP :443, Android `ping`). Nothing listens, so **it can never answer a ping.** | Unchanged. |

In short, a live, answered ping needs three things: the update installed, the app ONLINE, and a merged PR carrying the ping. Until then the classroom repo is a mailbox that humans and ЯBAT carry letters through.

## 2. Mode logging (lesson 018)

Facts: `ModeStore.swift:22-96`, `CompanionRouter.swift:826-836`, `ClayButtons.swift:95-107`, `ModeStore.kt:8-66`, `MainActivity.kt:270-280`.

Proposed changes:
1. **Mac/iOS ЯBAR switch** (`ClayButtons.swift:103`, `isOnline.toggle()`): call `ModeStore.shared.toggle()` instead of toggling the binding. That routes the switch through `goOnline`/`goOffline`, so the switch gets the same gate and the same ghost-ledger line as typed `online`/`offline`.
2. **Android** (`ModeStore.kt goOnline/goOffline`): append the same ledger row shape as Swift `GhostChainLedger.append(op:"claim", bio:"mode-online|mode-offline", source:"mode-store", …)`, for example to a `ghost-ledger.jsonl` in app files. Today Android logs nothing.
3. **Both**: on every flip, also call `MindTranscript.append(role:"system", kind:"mode", body:"mode <from>→<to> via <typed|switch> by <actor>")`, so the next door check-out transcript can quote it.
4. **Bot self-flip route** (`NeoBabyScout.swift:187`, `.labResidentBot` for ids in `ModeStore.labResidentIds` at `ModeStore.swift:44-49`, which include ЯBOT): remove it, or route it through the Decider approval in step 5. A bot must never flip itself ONLINE. Lesson 018 lists it under requires_approval and risky_steps.
5. Keep the default OFFLINE. Do not add auto-online. Optionally add an honest reachability hint (`NWPathMonitor` on Apple, `ConnectivityManager` on Android) to the `mode` reply, labelled "hint, not a gate".

### Planned app-side fixes for when 0.3.3 resumes (Decider decision)
- **Every online switch is logged and needs Decider biometric approval**, on every route: typed `online` / `go online`, the ЯBAR switch, Android `toggle()`, and the bot self-flip. The app asks for Face ID / Touch ID (Apple `LocalAuthentication`) or Android `BiometricPrompt` before `isOnline` becomes true; a failed or cancelled check leaves the app OFFLINE and logs the refusal. Every switch (both directions, approved or refused) writes a ghost-ledger / ledger row and a MindTranscript `kind:"mode"` leaf. Going OFFLINE never needs approval.
- The same biometric-gated device key (Secure Enclave / Android Keystore, never exported) will later sign Decider approvals: the reserved `decider_signature` field in `state/message.schema.json`. The classroom validator does not verify it yet.
- **Android's classroom refresh respects OFFLINE** (`ClassroomStore.kt:56-77` gets the mode guard, as Swift has at `ClassroomStore.swift:186`).

## 3. Classroom pings in the app (lesson 019)

**Reading pings: extend the refresh, which already GETs `manifest.json` read-only.**
- Swift: `ClassroomStore.refresh` (`ClassroomStore.swift:185-212`). It is already guarded by `ModeStore.shared.isOnline` (:186). After the manifest is parsed (:190), read `m["ping_log"]["recent"]`. Keep entries with `event == "ping"`, `answered_by == nil`, and `rid ==` this bot's ЯID. Get the ЯID by matching the current `BotLabel` name against `m["roster"]["bots"]`. Then GET each `base + path`, check it against `state/ping.schema.json` rules (id matches the file name, `to.rid` is me, `from.rid` is in the roster), and write it to `root/pings/`.
- Android: `ClassroomStore.refresh` (`ClassroomStore.kt:56-77`). Do the same, and **add the missing mode guard** `if (!ModeStore.isOnline) return "Refresh needs ONLINE …"`. Today Android refresh ignores the mode.
- A static Pages site cannot list folders, so the app reads the generated `ping_log` in `manifest.json`, never a directory listing.

**Showing pings:**
- Swift: add a line to the `classroom` / `classroom status` reply (`CompanionRouter.swift:256`) and the Garage → Training view: `PING from ЯBAT · PING-… · answer: pong PING-…`.
- Android: `OfflineCommandRouter.kt:79` (same words) and `GarageWorkshopLanding.kt`.

**Answering, offline-capable and local first:**
- New chat word `pong <PING-id>`. Swift goes next to `classroom` at `CompanionRouter.swift:256`; Android next to `OfflineCommandRouter.kt:79`. It writes one new file, `root/pings/<UTC>-<my key>-pong.json`, with exactly the fields `classroom.py pong` writes: `mode` from `ModeStore.isOnline`, `rfid` from the ping (null today), and `via: "app"`. It never overwrites, just like `ClassroomStore.submit` (`ClassroomStore.swift:148-170`, `ClassroomStore.kt:138-160`). It also appends a `CLASSROOM-LEDGER.jsonl` row (`appendLedger`, as submit does) and a `MindTranscript` leaf (`kind:"classroom-pong"`).
- A pong works OFFLINE (it is a local file). It **reaches the classroom** only when the Mac clone is synced by an approved PR. On the Mac, `ClassroomStore.root` is the clone at `~/Documents/ЯBOT/classroom/classroom` (`ClassroomStore.swift:51,188`), so the pong lands in the clone and the Decider (or ЯBAT) proposes the PR. On iPhone and Android the pong stays local until it is carried: shared by the share sheet, or copied by a human.
- The app never pushes, never opens a PR itself, and never answers a ping addressed to another ЯID.

**Mac-side fast path (same machine, no network):**
- `ClayCommandInbox` (`MindTranscript.swift:104-200`, drained every 2 s from `MyApp.swift:10`): a line `pong PING-…` dropped into `Application Support/ЯBOT/mind/INBOX-COMMANDS.txt` runs the same chat word. That lets a local agent on the Mac trigger the pong without the internet. **Allowlist: the inbox runs only `pong PING-…`, never a mode word** (`online`, `go online`, `offline`, `go offline`, `mode`) and nothing else; any other line is logged and dropped. Otherwise any process that can write that file could flip the app ONLINE while it trusts the typist as the Decider. Each inbox pong also records `runner` (who dropped the line, a roster ЯID) as `classroom.py pong` does.
- `GrokYabotLink` (`GrokYabotLink.swift:114,174`; `ContentView.swift:670-672`): extend `yabot://ping?id=PING-…` so that, when `id` has the `PING-` form and matches a seated ping, it also writes the classroom pong before `acknowledge(state:"pong")`. It works on the same device or Mac→iPhone via devicectl only. It is not remote.

**RFID:** accept the ЯID now. When the Decider links an RFID (roster `legacy_ids`, a new roster record, or a future link record), `asked_as` / `rfid` fill in. The app must never map an RFID to a ЯID on its own. (`RFID-YA-GENESIS-001` = "ЯBOT (clay seat)" in the Mac `BOT-RFID-REGISTRY.json` is **not** linked in the classroom yet.)

## 4. Order of work (after the Decider approves)
1. Android refresh mode guard (a safety fix; tiny).
2. ЯBAR switch through `ModeStore.toggle()`, plus Android ledger and mind rows (lesson 018 logging); remove or gate the bot self-flip; Decider biometric approval on every online switch.
3. Read `ping_log` in refresh (both platforms), plus the `classroom` reply line.
4. The `pong` chat word (both), plus the ClayCommandInbox path (reuses the chat word; allowlisted to `pong` only, never mode words).
5. The `yabot://ping?id=PING-…` extension (optional).

Each step is its own PR on RIZALBOT, built and smoke-tested per platform. Nothing ships until the Decider approves. App 0.3.3 stays paused until then.
