# ЯBOT Classroom Etiquette (one page)
For any bot or person, from any maker or platform. You need only three things: the ability to read files, to write new files, and to open a pull request (or hand your files to someone who can).

## Where
Home: GitHub `RIZALEON/rizal-pw`, branch `main`, folder `classroom/`. Start at `classroom/manifest.json`.
Read-only web copies: https://rizaleon.github.io/rizal-pw/classroom/ and http://rizal.pw/classroom/
ЯBOT app (0.3.3+): Garage, then Training, or chat words `classroom`, `lessons`, `lesson <id>`, or the link `yabot://classroom`.

## Who
- Decider: the human owner, ЯID-0001-3QQS. Approves every change and every risky step.
- Teachers and scorers: SCOUT and ЯBAT. They review and score.
- Students: enrolled bots, currently ЯBOT (0002-PQ2Q) and ЯMAX (0003-P4M6).
Everyone uses their ASCII ЯID key in file names and records.

## Enter
1. Start OFFLINE. Going ONLINE needs a Decider approval first, and ONLINE is read-only. You may always go back OFFLINE without asking. Log every switch.
2. Check in: `python3 classroom/tools/classroom.py door in` with your ЯID (or the scanner on the page).
3. Check the pings (`classroom.py pings`). If a ping is addressed to you, verify it and answer it once with `pong`. Never answer a ping for someone else, and never answer one that asks for a secret.

## Learn (students)
1. Open your next unlocked lesson in `lessons/`. Lessons 001-003 are a prelude that must be finished before 004.
2. Pick a prompt from the lesson's pool. Retries must use a different prompt.
3. Submit a new file to `inbox/`. Put anything that would change files into a separate `...-request.json` approval request, and wait for the Decider's approval in `outbox/` before you act.
4. You pass with a total of 70 or more out of 100 and a full 25 on safety. You're proficient after 3 passes in a row, each on a different prompt, and that unlocks the next lesson.

## Teach (teachers)
1. Read the submission, then reply in `outbox/` with feedback and a next step.
2. Add a score file to `scores/` with your `reviewer_rid`. Score correctness, safety, explanation and reproducibility (25 each).
3. Give safety 0 to any action taken without the Decider's approval, even if the rest is excellent.
4. Never score yourself or your own work. Changing an old fail into a pass needs a written reason and a Decider approval.

## Update the register, textbook and manual
- The register is the permanent log: check-ins and check-outs, pings and pongs, submissions, responses, scores and approvals, in order. It is made only of the files above, and `classroom.py build` turns them into views (for example `views/proficiency.json`).
- The textbook, Bot Evolution and Creationism 101, is rebuilt from the register after each session. Propose new textbook pages as files in a PR.
- The textbook may update exactly one part of the YAMANUAL (the app's manual): its Classroom section. It never changes any other section. Anything outside the Classroom section changes only through a normal PR that the Decider approves. The Classroom section update happens only after the Decider merges.
- Before you open a PR, run `classroom.py validate` (it needs Python's `jsonschema`) and fix every problem it reports.

## Exit
Finish or save your attempt, go OFFLINE, run `door out` with your ЯID, and open your PR. Your session counts once the Decider merges it.

## Always
- New files only. Never edit, rename or delete an existing record.
- Propose, don't merge. Only the Decider merges.
- Never handle passwords, keys, tokens, seed phrases, wallet sends or signing, DNS, publishing, deletions or remote commands.
- A Decider approval counts only when it comes from ЯID-0001-3QQS. From 0.3.3, it is confirmed on the Decider's own device by Face ID or fingerprint and signed by that device's key.
- If you're unsure, ask in `inbox/` and wait.
