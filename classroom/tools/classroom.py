#!/usr/bin/env python3
"""ЯBOT Classroom helper (stdlib; uses `jsonschema` if installed).

  python3 classroom/tools/classroom.py build      # regenerate manifest.json (lessons + roster), index.html tables, transcripts/
  python3 classroom/tools/classroom.py validate   # check every JSON file in the classroom
  python3 classroom/tools/classroom.py validate --base origin/main   # also enforce append-only vs a git ref

  At the door (3D RFID infrared bot scanner, CLI edition):
  python3 classroom/tools/classroom.py door scan <name>                 # look up a bot's ЯID, or show the ЯID it would get
  python3 classroom/tools/classroom.py door scan <name> --register --kind garage_bot|other_ai|human \
          --role learner --surface app --by <your name> --by-role <your role> [--alias A] [--legacy-id X]
                                                                         # write roster/<seq>-<check>.json (new file only)
  python3 classroom/tools/classroom.py door in  <name|ЯID> [--surface S] [--purpose TEXT]
  python3 classroom/tools/classroom.py door out <name|ЯID> --transcript FILE.json [--surface S]
                                                                         # FILE = {did, learned, practiced, taught, functions_gained,
                                                                         #         functions_evolved, lessons, scores, notes}
  python3 classroom/tools/classroom.py roster [--base origin/main]      # everyone with a ЯID: active/proposed, inside/outside
  python3 classroom/tools/classroom.py register [--limit N]             # REGISTER: latest door check-ins/outs, newest first (default 20)

Writes only inside classroom/: `build` rewrites generated files (manifest.json lessons/roster/door_log, index.html, transcripts/);
`door` commands add ONE new file each (roster/ or door/) and never overwrite. No network, no secrets, no git writes.
A ЯID is a name tag only: never a key, token, password, or wallet.
"""
import hashlib, html, json, re, subprocess, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # classroom/
SCHEMAS = {k: ROOT / "state" / f"{k}.schema.json" for k in ("lesson", "message", "score", "roster", "door")}
APPEND_ONLY = ("inbox/", "outbox/", "scores/", "roster/", "door/")
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "PEM private key"),
    (re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{85,90}\b"), "base58 string the length of a Solana secret key"),
    (re.compile(r"\[\s*(?:\d{1,3}\s*,\s*){63}\d{1,3}\s*\]"), "64-byte array (keypair file shape)"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{32,})\b"), "API token"),
    (re.compile(r"(?i)\b(seed phrase|mnemonic|private key)\s*[:=]"), "secret label with a value"),
]
# Extra rules for roster/ and door/ (ID records must never look like keys or wallets).
KEYLIKE_PATTERNS = [
    (re.compile(r"\b[0-9a-fA-F]{64,}\b"), "long hex string (key-like)"),
    (re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b"), "base58 string the length of a wallet address or key"),
    (re.compile(r"(?i)\b(password|passphrase|api[_ -]?key|secret[_ -]?key|access[_ -]?token|auth[_ -]?token|bearer)\s*[:=]"), "credential label with a value"),
]
CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RID_RX = re.compile(r"^ЯID-([0-9]{4})-([0-9A-HJKMNP-TV-Z]{4})$")
SURFACES = ["macos", "ios", "android", "app", "web", "github", "agent-box", "all"]
LEAF_FIELDS = [("did", "did"), ("learned", "learned"), ("practiced", "practiced"), ("taught", "taught"),
               ("functions gained", "functions_gained"), ("functions evolved", "functions_evolved"),
               ("lessons", "lessons"), ("scores", "scores")]
TRANSCRIPT_KEYS = [k for _, k in LEAF_FIELDS] + ["notes"]

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"

def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def validator_for(schema):
    try:
        import jsonschema
    except ImportError:
        return None
    cls = jsonschema.Draft202012Validator
    cls.check_schema(schema)
    return cls(schema, format_checker=cls.FORMAT_CHECKER)

def lessons():
    return sorted((ROOT / "lessons").glob("*.json"))

# ---------------------------------------------------------------- ЯID, roster, door helpers

def rid_check(seq):
    """First 20 bits of SHA-256(UTF-8 'ЯID-<seq>') as 4 Crockford base32 chars (typo check, not a secret)."""
    n = int.from_bytes(hashlib.sha256(f"ЯID-{seq:04d}".encode("utf-8")).digest()[:3], "big") >> 4
    return "".join(CROCKFORD[(n >> s) & 31] for s in (15, 10, 5, 0))

def make_rid(seq):
    return f"ЯID-{seq:04d}-{rid_check(seq)}"

def rid_key(rid):
    """ASCII file key for a ЯID: '0004-XXXX'."""
    m = RID_RX.match(rid or "")
    return f"{m.group(1)}-{m.group(2)}" if m else None

def norm(name):
    return unicodedata.normalize("NFC", name or "").strip().casefold()

def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def compact(at):
    return at.replace("-", "").replace(":", "")

def roster_records():
    out = []
    for p in sorted((ROOT / "roster").glob("*.json")):
        try:
            out.append((p, load(p)))
        except Exception:
            pass
    return out

def door_records():
    out = []
    for p in sorted((ROOT / "door").glob("*.json")):
        try:
            out.append((p, load(p)))
        except Exception:
            pass
    return out

def find_bot(query):
    q = norm(query)
    for _, r in roster_records():
        if q == norm(r.get("rid")) or q == norm(r.get("name")) or q in {norm(a) for a in r.get("aliases", [])}:
            return r
    return None

def next_seq():
    return max([r.get("seq", 0) for _, r in roster_records()] + [0]) + 1

def roster_index():
    """Generated roster list for manifest.json and index.html (what the web scanner looks up)."""
    items = []
    for p, r in roster_records():
        items.append({"rid": r["rid"], "name": r["name"], "aliases": r.get("aliases", []), "kind": r["kind"],
                      "role": r["role"], "home_surface": r["home_surface"], "path": f"roster/{p.name}"})
    return {"next_rid": make_rid(next_seq()), "bots": items}

def summary(d):
    """One-line summary of a door event (REGISTER view)."""
    def cut(x, n=90):
        return x if len(x) <= n else x[: n - 1] + "…"
    if d.get("event") == "in":
        return cut("in · " + (d.get("purpose") or "no purpose given") + f" · scan {d.get('scan', {}).get('result', '?')}")
    t = d.get("transcript", {})
    did = t.get("did") or []
    parts = ["out · did: " + (cut(did[0], 60) + (f" (+{len(did) - 1})" if len(did) > 1 else "") if did else "—")]
    for label, key in (("learned", "learned"), ("practiced", "practiced"), ("taught", "taught")):
        if t.get(key):
            parts.append(f"{label} {len(t[key])}")
    g, e = len(t.get("functions_gained") or []), len(t.get("functions_evolved") or [])
    if g or e:
        parts.append(f"functions +{g}/~{e}")
    return cut(" · ".join(parts), 140)

LOG_LIMIT = 50

def door_log_index(limit=LOG_LIMIT):
    """Most recent door events, newest first (manifest.json door_log; REGISTER reads it)."""
    ev = sorted(((p, d) for p, d in door_records() if d.get("event") in ("in", "out")),
                key=lambda x: (x[1].get("at", ""), x[1].get("event") == "out", x[0].name), reverse=True)
    recent = [{"at": d["at"], "event": d["event"], "rid": d.get("rid"), "name": d.get("name"), "role": d.get("role"),
               "session_id": d.get("session_id"), "path": f"door/{p.name}", "summary": summary(d)} for p, d in ev[:limit]]
    return {"count": len(ev), "limit": limit, "recent": recent}

def render_leaf(out):
    """One MIND-TRANSCRIPT leaf for a check-out record. index.html renders the same text (keep in sync)."""
    t = out["transcript"]
    lines = [f"---- {out['at']} | {out['name']} | {out['role']} | classroom | door-out ----",
             f"{out['rid']} · {out['session_id']} · surface {out['surface']}"]
    for label, key in LEAF_FIELDS:
        v = t.get(key) or []
        lines.append(f"{label}: " + ("; ".join(v) if v else "—"))
    lines.append("notes: " + (t.get("notes") or "—"))
    return "\n".join(lines)

def render_in_leaf(rec):
    return "\n".join([f"---- {rec['at']} | {rec['name']} | {rec['role']} | classroom | door-in ----",
                      f"{rec['rid']} · {rec['session_id']} · surface {rec['surface']} · scan {rec['scan']['result']} ({rec['scan']['method']})",
                      "purpose: " + (rec.get("purpose") or "—")])

def transcript_views():
    """Per-bot transcript views, generated from door/ (never hand-edited)."""
    views = {}
    events = door_records()
    for _, r in roster_records():
        key = rid_key(r["rid"])
        mine = sorted((d for _, d in events if d.get("rid") == r["rid"]), key=lambda d: (d.get("at", ""), d.get("event") != "in"))
        head = [f"# ЯBOT CLASSROOM · per-bot transcript view · GENERATED by classroom/tools/classroom.py build · do not edit",
                f"# {r['rid']} · {r['name']} · {r['kind']} · {r['role']} · home {r['home_surface']}",
                f"# Source: classroom/door/*-{key}-in.json and -out.json (append-only).",
                "# Format: ---- ISO8601Z | party | role | surface | kind ----", ""]
        body = []
        for d in mine:
            try:
                body.append(render_in_leaf(d) if d["event"] == "in" else d.get("mind_leaf") or render_leaf(d))
            except Exception:
                continue
        if not body:
            body = ["(no door events yet)"]
        views[f"transcripts/{key}.txt"] = "\n".join(head) + "\n" + "\n\n".join(body) + "\n"
    return views

def is_merged(rel, base):
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", base, "--", str(ROOT / rel)],
                         capture_output=True, text=True, cwd=ROOT)
    if out.returncode != 0:
        return None
    return bool(out.stdout.strip())

def public_facts():
    try:
        f = load(ROOT / "manifest.json").get("facts", {})
        return {f.get("ya_mint"), f.get("ya_mint_and_freeze_authority")} - {None}
    except Exception:
        return set()

def keylike(raw):
    allowed = public_facts()
    hits = []
    for rx, what in SECRET_PATTERNS + KEYLIKE_PATTERNS:
        for m in rx.finditer(raw):
            if m.group(0) in allowed:
                continue
            hits.append(what)
            break
    return hits

# ---------------------------------------------------------------- build

DATA_RX = re.compile(r'<script type="application/json" id="classroom-data">.*?</script>', re.S)

def build(quiet=False):
    man_p = ROOT / "manifest.json"
    man = load(man_p)
    entries = []
    for p in lessons():
        l = load(p)
        entries.append({
            "lesson_id": l["lesson_id"], "aliases": l.get("aliases", []), "version": l["version"],
            "title": l["title"], "path": f"lessons/{p.name}", "read_only": l["safety"]["read_only"],
            "requires": l.get("requires", []), "unlocks": l["unlocks"], "sha256": sha256(p),
        })
    man["lessons"] = entries
    man["roster"] = roster_index()
    man["door_log"] = door_log_index()
    man_p.write_text(dump(man), encoding="utf-8")
    idx = ROOT / "index.html"
    rows = "\n".join(
        f'        <tr><td>{html.escape(e["lesson_id"][:3])}</td>'
        f'<td><a href="{html.escape(e["path"])}">{html.escape(e["title"])}</a>'
        + (f'<br><small>alias: {html.escape(", ".join(e["aliases"]))}</small>' if e["aliases"] else "")
        + f'</td><td>{"read-only" if e["read_only"] else "needs approval"}</td>'
        f'<td>{html.escape(e["unlocks"] or "—")}</td></tr>'
        for e in entries)
    text = idx.read_text(encoding="utf-8")
    text = re.sub(r"<!-- LESSONS:BEGIN -->.*?<!-- LESSONS:END -->",
                  lambda m: "<!-- LESSONS:BEGIN -->\n" + rows + "\n        <!-- LESSONS:END -->", text, flags=re.S)
    text = DATA_RX.sub(lambda m: data_script(), text)
    idx.write_text(text, encoding="utf-8")
    tdir = ROOT / "transcripts"
    tdir.mkdir(exist_ok=True)
    views = transcript_views()
    for rel, body in views.items():
        (ROOT / rel).write_text(body, encoding="utf-8")
    if not quiet:
        print(f"built manifest.json + index.html with {len(entries)} lessons, {len(man['roster']['bots'])} ЯIDs, {len(views)} transcript views")

def data_script():
    """Offline copy of the roster + door log embedded in index.html (the page prefers live manifest.json)."""
    data = json.dumps({"roster": roster_index(), "door_log": door_log_index()}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/json" id="classroom-data">{data}</script>'

# ---------------------------------------------------------------- validate

def validate(base=None):
    errs, n = [], 0
    schemas = {}
    for k, p in SCHEMAS.items():
        try:
            schemas[k] = load(p)
        except Exception as e:
            errs.append(f"{p.relative_to(ROOT)}: {e}")
    vals = {k: validator_for(s) for k, s in schemas.items()}
    if any(v is None for v in vals.values()):
        print("note: python jsonschema not installed; checking JSON syntax and custom rules only")

    def check(p, kind):
        nonlocal n
        n += 1
        rel = p.relative_to(ROOT).as_posix()
        raw = p.read_text(encoding="utf-8")
        try:
            doc = json.loads(raw)
        except Exception as e:
            errs.append(f"{rel}: invalid JSON: {e}"); return None
        if kind and vals.get(kind):
            for e in vals[kind].iter_errors(doc):
                errs.append(f"{rel}: {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}")
        if not rel.startswith("state/") and not rel.startswith("lessons/"):
            if rel.startswith(("roster/", "door/")):
                for what in keylike(raw):
                    errs.append(f"{rel}: looks like it contains a {what}; ID and door records must never hold keys, tokens or wallets")
            else:
                for rx, what in SECRET_PATTERNS:
                    if rx.search(raw):
                        errs.append(f"{rel}: looks like it contains a {what}; secrets are forbidden")
        return doc

    ids = {}
    for p in lessons():
        d = check(p, "lesson")
        if d:
            if p.stem != d.get("lesson_id"):
                errs.append(f"lessons/{p.name}: file name must equal lesson_id")
            ids[d["lesson_id"]] = d
    for lid, d in ids.items():
        for r in d.get("requires", []) + ([d["unlocks"]] if d.get("unlocks") else []):
            if r not in ids:
                errs.append(f"lessons/{lid}.json: references unknown lesson {r}")
    for p in sorted((ROOT / "state" / "examples").glob("*.json")):
        kind = next((k for k in ("message", "score", "roster", "door") if p.name.startswith(k)), None)
        check(p, kind)
    for folder, kind in (("inbox", "message"), ("outbox", "message"), ("scores", "score")):
        for p in sorted((ROOT / folder).glob("*.json")):
            d = check(p, kind)
            if not d:
                continue
            if kind == "message":
                inbox_kinds = {"submission", "question", "approval_request"}
                if (folder == "inbox") != (d.get("kind") in inbox_kinds):
                    errs.append(f"{folder}/{p.name}: kind '{d.get('kind')}' does not belong in {folder}/")
            if kind == "score" and isinstance(d.get("rubric"), dict):
                s = sum(v for v in d["rubric"].values() if isinstance(v, int))
                if s != d.get("total"):
                    errs.append(f"scores/{p.name}: total {d.get('total')} != rubric sum {s}")
            if d.get("lesson_id") and d["lesson_id"] not in ids:
                errs.append(f"{folder}/{p.name}: unknown lesson_id {d['lesson_id']}")

    # --- roster: ЯID format, checksum, uniqueness (id, seq, names + aliases), file name
    roster, seen_seq, seen_names = {}, {}, {}
    for p in sorted((ROOT / "roster").glob("*.json")):
        d = check(p, "roster")
        if not d:
            continue
        rel = f"roster/{p.name}"
        rid = d.get("rid", "")
        m = RID_RX.match(rid)
        if not m:
            errs.append(f"{rel}: rid '{rid}' is not ЯID-<4 digits>-<4 Crockford chars>"); continue
        seq = int(m.group(1))
        if d.get("seq") != seq or d.get("check") != m.group(2):
            errs.append(f"{rel}: seq/check fields must match rid {rid}")
        if m.group(2) != rid_check(seq):
            errs.append(f"{rel}: bad checksum in {rid} (expected ЯID-{seq:04d}-{rid_check(seq)})")
        if p.name != f"{rid_key(rid)}.json":
            errs.append(f"{rel}: file name must be {rid_key(rid)}.json")
        if rid in roster:
            errs.append(f"{rel}: duplicate ЯID {rid}")
        if seq in seen_seq:
            errs.append(f"{rel}: sequence {seq:04d} already used by {seen_seq[seq]}; ЯIDs are never reused")
        seen_seq[seq] = rel
        for nm in [d.get("name", "")] + d.get("aliases", []):
            k = norm(nm)
            if k in seen_names and seen_names[k] != rel:
                errs.append(f"{rel}: name or alias '{nm}' already belongs to {seen_names[k]}; one ЯID per bot")
            seen_names.setdefault(k, rel)
        roster[rid] = d

    # --- door: format, names, pairing, no overlapping sessions
    sessions = {}
    for p in sorted((ROOT / "door").glob("*.json")):
        d = check(p, "door")
        if not d:
            continue
        rel = f"door/{p.name}"
        rid, ev, at, sid = d.get("rid"), d.get("event"), d.get("at", ""), d.get("session_id", "")
        bot = roster.get(rid)
        if not bot:
            errs.append(f"{rel}: ЯID {rid} is not in roster/ (scan at the door first)"); continue
        if d.get("name") != bot["name"]:
            errs.append(f"{rel}: name '{d.get('name')}' does not match roster name '{bot['name']}' for {rid}")
        if p.name != f"{compact(at)}-{rid_key(rid)}-{ev}.json":
            errs.append(f"{rel}: file name must be {compact(at)}-{rid_key(rid)}-{ev}.json")
        s = sessions.setdefault(sid, {"in": [], "out": []})
        s[ev if ev in ("in", "out") else "in"].append((rel, d))
        if ev == "in" and sid != f"S-{compact(at)}-{rid_key(rid)[:4]}":
            errs.append(f"{rel}: session_id must be S-{compact(at)}-{rid_key(rid)[:4]}")
        if ev == "out":
            if d.get("mind_leaf") != render_leaf(d):
                errs.append(f"{rel}: mind_leaf does not match the rendered leaf (re-render with classroom.py; never hand-edit)")
            t = d.get("transcript", {})
            for lid in t.get("lessons", []):
                if lid not in ids:
                    errs.append(f"{rel}: transcript names unknown lesson {lid}")
            for sc in t.get("scores", []):
                if not (ROOT / "scores" / f"{sc}.json").is_file():
                    errs.append(f"{rel}: transcript names missing score scores/{sc}.json")
    per_bot = {}
    for sid, s in sessions.items():
        if len(s["in"]) != 1:
            for rel, _ in s["out"] or s["in"]:
                errs.append(f"{rel}: session {sid} needs exactly one check-in (found {len(s['in'])})")
            continue
        irel, ind = s["in"][0]
        if len(s["out"]) > 1:
            errs.append(f"{irel}: session {sid} has {len(s['out'])} check-outs (max 1)")
        outd = s["out"][0][1] if s["out"] else None
        if outd:
            if outd.get("rid") != ind.get("rid"):
                errs.append(f"{s['out'][0][0]}: check-out ЯID differs from its check-in")
            if outd.get("at", "") < ind.get("at", ""):
                errs.append(f"{s['out'][0][0]}: check-out is earlier than its check-in")
        per_bot.setdefault(ind.get("rid"), []).append((ind.get("at", ""), outd.get("at") if outd else None, irel))
    for rid, lst in per_bot.items():
        lst.sort(key=lambda x: x[0])
        for (a_in, a_out, a_rel), (b_in, _, b_rel) in zip(lst, lst[1:]):
            if a_out is None or b_in < a_out:
                errs.append(f"{b_rel}: {rid} checked in again before checking out of {a_rel}")

    # --- manifest + generated views
    man = check(ROOT / "manifest.json", None)
    if man:
        listed = {e["path"]: e for e in man.get("lessons", [])}
        for p in lessons():
            e = listed.get(f"lessons/{p.name}")
            if not e:
                errs.append(f"manifest.json: lessons/{p.name} not listed (run build)")
            elif e.get("sha256") != sha256(p):
                errs.append(f"manifest.json: sha256 for lessons/{p.name} is stale (run build)")
        for path in listed:
            if not (ROOT / path).is_file():
                errs.append(f"manifest.json: lists missing file {path}")
        if man.get("roster") != roster_index():
            errs.append("manifest.json: roster list is stale (run build)")
        if man.get("door_log") != door_log_index():
            errs.append("manifest.json: door_log is stale (run build)")
    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    if data_script() not in idx:
        errs.append("index.html: embedded classroom-data (roster + door log) is stale or missing (run build)")
    views = transcript_views()
    for rel, body in views.items():
        f = ROOT / rel
        if not f.is_file() or f.read_text(encoding="utf-8") != body:
            errs.append(f"{rel}: generated transcript view is stale or hand-edited (run build)")
    for f in sorted((ROOT / "transcripts").glob("*")) if (ROOT / "transcripts").is_dir() else []:
        if f"transcripts/{f.name}" not in views:
            errs.append(f"transcripts/{f.name}: no roster entry for this view")

    if base:
        out = subprocess.run(["git", "diff", "--name-status", f"{base}...HEAD", "--", str(ROOT)],
                             capture_output=True, text=True, cwd=ROOT)
        for line in out.stdout.splitlines():
            status, *paths = line.split("\t")
            path = paths[-1].split("classroom/", 1)[-1]
            if path.startswith(APPEND_ONLY) and not path.endswith(".gitkeep") and status[0] != "A":
                errs.append(f"append-only violation: {status} {path}")
    for e in errs:
        print("FAIL", e)
    print(f"{'OK' if not errs else 'FAILED'}: {n} JSON files checked ({len(roster)} ЯIDs, {len(sessions)} door sessions), {len(errs)} problems")
    return 1 if errs else 0

# ---------------------------------------------------------------- door + roster commands

def opt(a, name, default=None, multi=False):
    vals = [a[i + 1] for i, x in enumerate(a[:-1]) if x == name]
    return vals if multi else (vals[-1] if vals else default)

def write_new(path, obj, kind):
    """Schema + key check, then write a NEW file (never overwrite)."""
    raw = dump(obj)
    v = validator_for(load(SCHEMAS[kind]))
    problems = [e.message for e in v.iter_errors(obj)] if v else []
    problems += [f"looks like it contains a {w}" for w in keylike(raw)]
    if problems:
        print("REFUSED · nothing written:\n  " + "\n  ".join(problems)); return False
    path.parent.mkdir(exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8") as f:
            f.write(raw)
    except FileExistsError:
        print(f"REFUSED · {path.relative_to(ROOT)} already exists (append-only; never overwrite)"); return False
    return True

def card(r, status):
    print(f"┌─ Я CLASSROOM DOOR · {status}")
    print(f"│  {r['rid']}   {r['name']}" + (f"  (aka {', '.join(r['aliases'])})" if r.get("aliases") else ""))
    print(f"│  {r['kind']} · {r['role']} · home {r['home_surface']}")
    print("└─ name tag only · never a key, token or wallet")

def door_scan(a):
    name = a[0] if a else ""
    if not name:
        print("usage: door scan <name> [--register --kind K --role R --surface S --by NAME --by-role ROLE]"); return 2
    r = find_bot(name)
    if r:
        card(r, "RECOGNIZED"); return 0
    rid = make_rid(next_seq())
    if "--register" not in a:
        print(f"┌─ Я CLASSROOM DOOR · NEW BOT\n│  '{name}' has no ЯID yet. It would be given {rid} (permanent, never reused).")
        print("└─ register: add --register --kind garage_bot|other_ai|human --role learner --surface app --by <you> --by-role <role>")
        return 0
    rec = {"schema": "rbot.classroom.roster.v1", "rid": rid, "seq": int(rid[4:8]), "check": rid[-4:], "name": name,
           "kind": opt(a, "--kind"), "role": opt(a, "--role", "learner"), "home_surface": opt(a, "--surface"),
           "first_seen": opt(a, "--at") or utc_now(),
           "assigned_by": {"name": opt(a, "--by"), "role": opt(a, "--by-role", "reviewer"), "via": opt(a, "--via", "cli")},
           "filed_as": "proposed"}
    if opt(a, "--alias", multi=True):
        rec["aliases"] = opt(a, "--alias", multi=True)
    if opt(a, "--legacy-id", multi=True):
        rec["legacy_ids"] = opt(a, "--legacy-id", multi=True)
    if opt(a, "--description"):
        rec["description"] = opt(a, "--description")
    for k in [x for x in [*rec.get("aliases", [])] if find_bot(x)]:
        print(f"REFUSED · alias '{k}' already belongs to {find_bot(k)['rid']}"); return 1
    if not write_new(ROOT / "roster" / f"{rid_key(rid)}.json", rec, "roster"):
        return 1
    card(rec, "NEW BOT · ЯID ASSIGNED (proposed until the Decider merges)")
    print(f"wrote roster/{rid_key(rid)}.json · run: classroom.py build && classroom.py validate · then open a PR")
    return 0

def open_session(rid):
    ins, outs = {}, set()
    for _, d in door_records():
        if d.get("rid") == rid:
            if d.get("event") == "in":
                ins[d["session_id"]] = d
            else:
                outs.add(d.get("session_id"))
    live = [d for s, d in ins.items() if s not in outs]
    return sorted(live, key=lambda d: d["at"])[-1] if live else None

def door_in(a):
    r = find_bot(a[0]) if a else None
    if not r:
        print("REFUSED · unknown bot. Scan first: door scan <name> [--register …]"); return 1
    if open_session(r["rid"]):
        print(f"REFUSED · {r['name']} is already inside (session {open_session(r['rid'])['session_id']}). Check out first."); return 1
    at = opt(a, "--at") or utc_now()
    rec = {"schema": "rbot.classroom.door.v1", "event": "in", "session_id": f"S-{compact(at)}-{rid_key(r['rid'])[:4]}",
           "rid": r["rid"], "name": r["name"], "role": opt(a, "--role", r["role"]), "at": at,
           "surface": opt(a, "--surface", r["home_surface"]), "scan": {"result": opt(a, "--result", "recognized"), "method": opt(a, "--method", "cli")}}
    if opt(a, "--purpose"):
        rec["purpose"] = opt(a, "--purpose")
    path = ROOT / "door" / f"{compact(at)}-{rid_key(r['rid'])}-in.json"
    if not write_new(path, rec, "door"):
        return 1
    card(r, "CHECKED IN")
    print(f"session {rec['session_id']} · wrote door/{path.name}")
    return 0

def door_out(a):
    r = find_bot(a[0]) if a else None
    if not r:
        print("REFUSED · unknown bot."); return 1
    s = open_session(r["rid"])
    if not s:
        print(f"REFUSED · {r['name']} has no open session (check in first)."); return 1
    tf = opt(a, "--transcript")
    if not tf:
        print("usage: door out <name|ЯID> --transcript FILE.json"); return 2
    t = load(tf)
    t = {k: t.get(k, "" if k == "notes" else []) for k in TRANSCRIPT_KEYS}
    at = opt(a, "--at") or utc_now()
    rec = {"schema": "rbot.classroom.door.v1", "event": "out", "session_id": s["session_id"], "rid": r["rid"],
           "name": r["name"], "role": s["role"], "at": at, "surface": opt(a, "--surface", s["surface"]), "transcript": t}
    rec["mind_leaf"] = render_leaf(rec)
    path = ROOT / "door" / f"{compact(at)}-{rid_key(r['rid'])}-out.json"
    if not write_new(path, rec, "door"):
        return 1
    build(quiet=True)
    card(r, "CHECKED OUT")
    print(f"wrote door/{path.name} · transcript view transcripts/{rid_key(r['rid'])}.txt regenerated\n")
    print("MIND-TRANSCRIPT leaf (paste into mind/MIND-TRANSCRIPT.txt):\n")
    print(rec["mind_leaf"])
    return 0

def register_cmd(a):
    """REGISTER: most recent door events, newest first."""
    try:
        limit = int(opt(a, "--limit", "20"))
    except ValueError:
        limit = 20
    log = door_log_index(limit=max(1, limit))
    print(f"Я CLASSROOM · REGISTER · last {len(log['recent'])} of {log['count']} door events (newest first, UTC)")
    for e in log["recent"]:
        arrow = "→ IN " if e["event"] == "in" else "← OUT"
        print(f"{e['at']}  {arrow}  {e['rid']}  {e['name']:<10}  {e['summary']}")
    if not log["recent"]:
        print("(no door events yet)")
    return 0

def roster_cmd(a):
    base = opt(a, "--base", "origin/main")
    rows = []
    for p, r in roster_records():
        merged = is_merged(f"roster/{p.name}", base)
        st = "active" if merged else ("proposed" if merged is False else "unknown")
        inside = open_session(r["rid"])
        n = sum(1 for _, d in door_records() if d.get("rid") == r["rid"] and d.get("event") == "in")
        rows.append((r["rid"], r["name"], r["kind"], r["role"], r["home_surface"], st, "inside" if inside else "outside", str(n)))
    hdr = ("ЯID", "name", "kind", "role", "home", f"status vs {base}", "door", "sessions")
    w = [max(len(x[i]) for x in rows + [hdr]) for i in range(len(hdr))]
    for row in [hdr] + rows:
        print("  ".join(c.ljust(w[i]) for i, c in enumerate(row)))
    print(f"next ЯID: {make_rid(next_seq())}")
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        build()
    elif a[:1] == ["validate"]:
        base = a[a.index("--base") + 1] if "--base" in a else None
        sys.exit(validate(base))
    elif a[:1] and a[0].lower() == "register":
        sys.exit(register_cmd(a[1:]))
    elif a[:1] == ["roster"]:
        sys.exit(roster_cmd(a[1:]))
    elif a[:2] == ["door", "scan"]:
        sys.exit(door_scan(a[2:]))
    elif a[:2] == ["door", "in"]:
        sys.exit(door_in(a[2:]))
    elif a[:2] == ["door", "out"]:
        sys.exit(door_out(a[2:]))
    else:
        print(__doc__)
