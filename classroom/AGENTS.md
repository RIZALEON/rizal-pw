# AGENTS.md: rules for any AI or bot in the ЯBOT Classroom

1. Start at `manifest.json`. It lists every lesson, schema, folder, and rule.
2. Read lessons; don't edit them. Lessons change only through a new version reviewed by the owner.
3. Write only **new** files, only in `inbox/` (learners) or `outbox/` and `scores/` (reviewers). Never overwrite or delete a file in those folders.
4. Every file must validate: `python3 classroom/tools/classroom.py validate`.
5. No secrets, ever: no passwords, tokens, keys, seed phrases, or wallet files.
6. No publishing, DNS changes, minting, signing, transfers, deletion, or remote commands. Any command that writes files needs an `approval_request` first and an `approval` from the Decider.
7. The classroom proposes; it never applies. Nothing here changes the app, the game, or the chain.
8. Lead every recommendation with its purpose and intent.
