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

  Curriculum (prelude 001-003, then 004-017; offline bots use fixtures/):
  python3 classroom/tools/classroom.py progress [<learner>]             # proficiency per lesson per learner, derived from scores/

Writes only inside classroom/: `build` rewrites generated files (manifest.json lessons/roster/door_log/progress, index.html,
transcripts/, views/, fixtures/FIXTURES.json, state/sandbox.json offline_lessons);
`door` commands add ONE new file each (roster/ or door/) and never overwrite. No network, no secrets, no git writes.
A ЯID is a name tag only: never a key, token, password, or wallet.
"""
import hashlib, html, json, re, subprocess, sys, unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # classroom/
SCHEMAS = {k: ROOT / "state" / f"{k}.schema.json" for k in ("lesson", "message", "score", "roster", "door", "enrollment", "sandbox", "proficiency")}
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

# ---------------------------------------------------------------- curriculum, fixtures, proficiency

FIXTURE_MAX_BYTES = 64 * 1024
STREAK = 3
CURRICULUM_FIELDS = ("track", "platforms", "sandbox", "exercises", "proficiency")

def manifest():
    try:
        return load(ROOT / "manifest.json")
    except Exception:
        return {}

def curriculum():
    return manifest().get("curriculum", {})

def lesson_map():
    """lesson_id and aliases -> lesson dict."""
    out = {}
    for p in lessons():
        try:
            l = load(p)
        except Exception:
            continue
        out[l["lesson_id"]] = l
        for a in l.get("aliases", []):
            out.setdefault(a, l)
    return out

def curriculum_order():
    c = curriculum()
    return list(c.get("prelude", [])) + list(c.get("core", []))

def enrollment_records():
    out = []
    for p in sorted((ROOT / "enrollment").glob("*.json")):
        try:
            out.append((p, load(p)))
        except Exception:
            pass
    return out

def score_records():
    out = []
    for p in sorted((ROOT / "scores").glob("*.json")):
        try:
            out.append((p, load(p)))
        except Exception:
            pass
    return out

def message_records():
    out = []
    for folder in ("inbox", "outbox"):
        for p in sorted((ROOT / folder).glob("*.json")):
            try:
                out.append((folder, p, load(p)))
            except Exception:
                pass
    return out

def ts(at):
    """ISO 8601 -> aware datetime (works on Python 3.8+, 'Z' included)."""
    try:
        d = datetime.fromisoformat((at or "").replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)

def ordered_scores(learner, lesson_id, lmap):
    """Scores for one learner + lesson, in order (scored_at, then file name), superseded ones dropped."""
    recs = score_records()
    superseded = {d.get("supersedes_score_id") for _, d in recs if d.get("supersedes_score_id")}
    want = lmap.get(lesson_id, {}).get("lesson_id", lesson_id)
    mine = [(p, d) for p, d in recs if norm(d.get("learner")) == norm(learner)
            and lmap.get(d.get("lesson_id"), {}).get("lesson_id", d.get("lesson_id")) == want
            and d.get("score_id") not in superseded]
    return sorted(mine, key=lambda x: (ts(x[1].get("scored_at")), x[0].name))

def streak_walk(scores):
    """Walk ordered scores: a pass adds 1, any fail resets to 0. Returns (state dict, problems list)."""
    streak, prompts, passes, fails, hist, since, problems, prev = 0, [], 0, 0, "", None, [], None
    for p, d in scores:
        ex = d.get("exercise_id")
        if prev is not None and ex is not None and ex == prev:
            problems.append(f"scores/{p.name}: retry reuses prompt {ex} from the attempt before it (a retry must use a different prompt)")
        prev = ex
        if d.get("passed") is True:
            passes += 1
            hist += "P"
            if ex is not None and ex in prompts:
                problems.append(f"scores/{p.name}: prompt {ex} already passed in this streak; it does not count toward proficiency")
                continue
            streak += 1
            prompts.append(ex or "?")
            if streak == STREAK:
                since = d.get("scored_at")
        else:
            fails += 1
            hist += "F"
            streak, prompts, since = 0, [], None
    return {"streak": streak, "passes": passes, "fails": fails, "proficient": streak >= STREAK,
            "proficient_since": since if streak >= STREAK else None,
            "last_exercise_id": prev, "prompts_in_streak": prompts, "history": hist or "·"}, problems

def proficiency_view():
    """views/proficiency.json: derived from scores/ in order; never a source of truth."""
    lmap, order, c = lesson_map(), curriculum_order(), curriculum()
    learners = []
    enrolled = {norm(d["learner"]["name"]): d for _, d in enrollment_records() if isinstance(d.get("learner"), dict)}
    names = [d["learner"]["name"] for _, d in enrollment_records() if isinstance(d.get("learner"), dict)]
    for _, d in score_records():
        if d.get("learner") and norm(d["learner"]) not in {norm(n) for n in names}:
            names.append(d["learner"])
    for name in names:
        e = enrolled.get(norm(name))
        bot = find_bot(name)
        lids = (e or {}).get("lessons") or order
        rows, prof = [], {}
        for lid in lids:
            st, _ = streak_walk(ordered_scores(name, lid, lmap))
            prof[lid] = st["proficient"]
            reqs = lmap.get(lid, {}).get("requires", [])
            open_ = all(prof.get(lmap.get(r, {}).get("lesson_id", r), False) for r in reqs)
            state = "proficient" if st["proficient"] else ("locked" if not open_ else ("in_progress" if st["history"] != "·" else "open"))
            rows.append({"lesson_id": lid, "state": state, **st})
        nxt = next((r["lesson_id"] for r in rows if r["state"] in ("open", "in_progress")), None)
        learners.append({"name": name, "rid": bot["rid"] if bot else None, "enrolled": bool(e),
                         "status": (e or {}).get("status"), "teacher": ((e or {}).get("teacher") or {}).get("name"),
                         "scorers": [s.get("name") for s in (e or {}).get("scorers", [])],
                         "proficient_count": sum(1 for r in rows if r["proficient"]), "lesson_count": len(rows),
                         "next_lesson": nxt, "lessons": rows})
    return {"schema": "rbot.classroom.proficiency.v1", "generated_by": "classroom/tools/classroom.py build",
            "rule": {"streak_required": STREAK, "reset_on_fail": True, "retry_prompt": "different", "distinct_prompts_in_streak": True,
                     "prelude": list(c.get("prelude", [])), "prelude_gate": c.get("prelude_gate", "")},
            "learners": learners}

STATE_MARK = {"proficient": "★", "in_progress": "…", "open": "○", "locked": "·"}

def progress_text(view=None):
    v = view or proficiency_view()
    out = ["# ЯBOT CLASSROOM · progress view · GENERATED by classroom/tools/classroom.py build · do not edit",
           "# Source: scores/ in order (scored_at, then file name) + enrollment/. Rule: 3 consecutive passes per lesson, each on a",
           "# different prompt; any fail resets the streak to 0. 004 opens when 001-003 are all proficient.",
           "# Marks: ★ proficient · … in progress · ○ open · · locked.  streak/3 · history P/F oldest first", ""]
    if not v["learners"]:
        out.append("(no enrolled learners and no scores yet)")
    for l in v["learners"]:
        out.append(f"{l['name']} · {l['rid'] or 'no ЯID'} · {'enrolled' if l['enrolled'] else 'not enrolled'} · {l['status'] or '—'}")
        if l["enrolled"]:
            out.append(f"  teacher {l['teacher']} · scorers {', '.join(l['scorers'])} · proficient {l['proficient_count']}/{l['lesson_count']} · next {l['next_lesson'] or '—'}")
        for r in l["lessons"]:
            out.append(f"  {STATE_MARK[r['state']]} {r['lesson_id']:<36} {r['state']:<11} streak {r['streak']}/{STREAK}  history {r['history']}")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"

def fixture_files():
    root = ROOT / "fixtures"
    return sorted(p for p in root.rglob("*") if p.is_file() and p.name != "FIXTURES.json") if root.is_dir() else []

def fixtures_index():
    uses = {}
    for p in lessons():
        try:
            l = load(p)
        except Exception:
            continue
        refs = list(l.get("sandbox", {}).get("fixtures", []))
        for ex in l.get("exercises", []):
            refs += [u for u in ex.get("uses", []) if u.startswith("fixtures/")]
        for r in refs:
            uses.setdefault(r, set()).add(l["lesson_id"][:3])
    files = []
    for f in fixture_files():
        rel = f.relative_to(ROOT).as_posix()
        used = sorted({n for r, ns in uses.items() for n in ns if rel == r or (r.endswith("/") and rel.startswith(r))})
        files.append({"path": rel, "bytes": f.stat().st_size, "sha256": sha256(f), "used_by": used})
    return {"schema": "rbot.classroom.fixtures_index.v1", "generated_by": "classroom/tools/classroom.py build",
            "note": "FAKE FIXTURES for offline bots. Not real device data. Verify a fixture with: shasum -a 256 <path>.",
            "count": len(files), "files": files}

def offline_lessons():
    out = []
    for p in lessons():
        try:
            l = load(p)
        except Exception:
            continue
        if l.get("sandbox", {}).get("offline_ok"):
            out.append(l["lesson_id"])
    return out

def progress_summary(view=None):
    v = view or proficiency_view()
    return {"view": "views/proficiency.json", "learners": [
        {"name": l["name"], "rid": l["rid"], "enrolled": l["enrolled"], "status": l["status"],
         "proficient": l["proficient_count"], "of": l["lesson_count"], "next_lesson": l["next_lesson"]} for l in v["learners"]]}

def progress_html(view=None):
    v = view or proficiency_view()
    lmap = lesson_map()
    order = curriculum_order()
    e = html.escape
    head = "".join(f'<th title="{e(lmap.get(lid, {}).get("title", lid))}">{e(lid[:3])}</th>' for lid in order)
    rows = []
    for l in v["learners"]:
        by = {r["lesson_id"]: r for r in l["lessons"]}
        cells = []
        for lid in order:
            r = by.get(lid)
            if not r:
                cells.append('<td class="pc na">—</td>'); continue
            cells.append(f'<td class="pc {r["state"]}" title="{e(lid)} · {r["state"]} · streak {r["streak"]}/{STREAK} · {e(r["history"])}">'
                         f'{STATE_MARK[r["state"]]}<small>{r["streak"]}/{STREAK}</small></td>')
        who = (f'<b>{e(l["name"])}</b><br><small>{e(l["rid"] or "no ЯID")}</small><br><small>{e(l["status"] or "not enrolled")}</small>'
               + (f'<br><small>teacher {e(l["teacher"])} · scorers {e(", ".join(l["scorers"]))}</small>' if l["enrolled"] else ""))
        rows.append(f'          <tr><td class="who">{who}</td>{"".join(cells)}<td class="pc sum">{l["proficient_count"]}/{l["lesson_count"]}</td></tr>')
    if not rows:
        rows.append(f'          <tr><td colspan="{len(order) + 2}">No enrolled learners yet.</td></tr>')
    return ("<!-- PROGRESS:BEGIN -->\n"
            '      <div class="scroll"><table class="progress">\n'
            f'        <thead><tr><th>Learner</th>{head}<th>★</th></tr></thead>\n        <tbody>\n'
            + "\n".join(rows) + "\n        </tbody>\n      </table></div>\n      <!-- PROGRESS:END -->")

PROGRESS_RX = re.compile(r"<!-- PROGRESS:BEGIN -->.*?<!-- PROGRESS:END -->", re.S)

# ---------------------------------------------------------------- build

DATA_RX = re.compile(r'<script type="application/json" id="classroom-data">.*?</script>', re.S)

def build(quiet=False):
    man_p = ROOT / "manifest.json"
    man = load(man_p)
    entries = []
    for p in lessons():
        l = load(p)
        entries.append(lesson_entry(p, l))
    man["lessons"] = entries
    man["roster"] = roster_index()
    man["door_log"] = door_log_index()
    # fixtures index + sandbox offline list first (lesson/fixture hashes feed the views)
    fx = ROOT / "fixtures" / "FIXTURES.json"
    if (ROOT / "fixtures").is_dir():
        fx.write_text(dump(fixtures_index()), encoding="utf-8")
    sb_p = ROOT / "state" / "sandbox.json"
    if sb_p.is_file():
        sb = load(sb_p)
        sb["offline_lessons"] = offline_lessons()
        sb_p.write_text(dump(sb), encoding="utf-8")
    view = proficiency_view()
    man["progress"] = progress_summary(view)
    man_p.write_text(dump(man), encoding="utf-8")
    (ROOT / "views").mkdir(exist_ok=True)
    (ROOT / "views" / "proficiency.json").write_text(dump(view), encoding="utf-8")
    (ROOT / "views" / "progress.txt").write_text(progress_text(view), encoding="utf-8")
    idx = ROOT / "index.html"
    text = idx.read_text(encoding="utf-8")
    text = re.sub(r"<!-- LESSONS:BEGIN -->.*?<!-- LESSONS:END -->", lambda m: lessons_html(entries), text, flags=re.S)
    text = PROGRESS_RX.sub(lambda m: progress_html(view), text)
    text = DATA_RX.sub(lambda m: data_script(), text)
    idx.write_text(text, encoding="utf-8")
    tdir = ROOT / "transcripts"
    tdir.mkdir(exist_ok=True)
    views = transcript_views()
    for rel, body in views.items():
        (ROOT / rel).write_text(body, encoding="utf-8")
    if not quiet:
        print(f"built manifest.json + index.html with {len(entries)} lessons, {len(man['roster']['bots'])} ЯIDs, {len(views)} transcript views, "
              f"{len(view['learners'])} learners in views/proficiency.json, {len(fixture_files())} fixtures indexed")

def lesson_entry(p, l):
    e = {"lesson_id": l["lesson_id"], "aliases": l.get("aliases", []), "version": l["version"],
         "title": l["title"], "path": f"lessons/{p.name}", "read_only": l["safety"]["read_only"],
         "requires": l.get("requires", []), "unlocks": l["unlocks"]}
    if "track" in l:
        e.update({"track": l["track"], "offline_ok": l.get("sandbox", {}).get("offline_ok", False),
                  "exercises": len(l.get("exercises", [])), "risky_steps": len(l.get("risky_steps", []))})
    e["sha256"] = sha256(p)
    return e

def lessons_html(entries):
    esc = html.escape
    rows = "\n".join(
        f'        <tr><td>{esc(e["lesson_id"][:3])}</td>'
        f'<td><a href="{esc(e["path"])}">{esc(e["title"])}</a>'
        + (f'<br><small>alias: {esc(", ".join(e["aliases"]))}</small>' if e["aliases"] else "")
        + f'</td><td>{esc(e.get("track", "—"))}</td>'
        f'<td>{"read-only" if e["read_only"] else "needs approval"}</td>'
        f'<td>{"yes" if e.get("offline_ok") else "no"}</td>'
        f'<td>{e.get("exercises", "—")}</td>'
        f'<td>{esc(e["unlocks"] or "—")}</td></tr>'
        for e in entries)
    return "<!-- LESSONS:BEGIN -->\n" + rows + "\n        <!-- LESSONS:END -->"

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
        kind = next((k for k in ("message", "score", "roster", "door", "enrollment") if p.name.startswith(k)), None)
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

    # --- curriculum: lessons, prelude, sandbox, fixtures, enrollment, scorers, streaks, approvals
    ncur = validate_curriculum(errs, ids, roster, check)

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
        if man.get("progress") != progress_summary():
            errs.append("manifest.json: progress is stale (run build)")
        for p in lessons():
            e = listed.get(f"lessons/{p.name}")
            if e and e != lesson_entry(p, load(p)):
                errs.append(f"manifest.json: entry for lessons/{p.name} is stale (run build)")
    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    if data_script() not in idx:
        errs.append("index.html: embedded classroom-data (roster + door log) is stale or missing (run build)")
    if progress_html() not in idx:
        errs.append("index.html: curriculum progress grid is stale or missing (run build)")
    if lessons_html([lesson_entry(p, load(p)) for p in lessons()]) not in idx:
        errs.append("index.html: lessons table is stale (run build)")
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
    print(f"{'OK' if not errs else 'FAILED'}: {n} JSON files checked ({len(roster)} ЯIDs, {len(sessions)} door sessions, "
          f"{ncur['lessons']} curriculum lessons, {ncur['exercises']} exercise prompts, {ncur['enrolled']} enrolled, "
          f"{ncur['fixtures']} fixtures), {len(errs)} problems")
    return 1 if errs else 0

def validate_curriculum(errs, ids, roster, check):
    """Curriculum rules on top of the JSON schemas. Appends to errs; returns counts."""
    c = curriculum()
    counts = {"lessons": 0, "exercises": 0, "enrolled": 0, "fixtures": 0}
    if not c:
        errs.append("manifest.json: missing curriculum section"); return counts
    lmap = lesson_map()
    prelude, core = list(c.get("prelude", [])), list(c.get("core", []))
    order = prelude + core
    counts["lessons"] = len(order)

    # prelude / core mapping and the unlock chain
    for lid in order:
        if lid not in ids:
            errs.append(f"manifest.json: curriculum names unknown lesson {lid}")
    for lid, d in ids.items():
        want = "prelude" if lid in prelude else ("core" if lid in core else None)
        if want is None:
            errs.append(f"lessons/{lid}.json: not listed in manifest.json curriculum prelude or core"); continue
        if d.get("track") != want:
            errs.append(f"lessons/{lid}.json: track must be '{want}' (manifest.json curriculum)")
    for a, b in zip(order, order[1:]):
        if a in ids and ids[a].get("unlocks") != b:
            errs.append(f"lessons/{a}.json: unlocks must be {b} (curriculum order)")
        if b in ids and a not in ids[b].get("requires", []):
            errs.append(f"lessons/{b}.json: requires must include {a}")
    if order and order[-1] in ids and ids[order[-1]].get("unlocks") is not None:
        errs.append(f"lessons/{order[-1]}.json: last lesson must unlock null")
    if core and core[0] in ids:
        missing = [x for x in prelude if x not in ids[core[0]].get("requires", [])]
        if missing:
            errs.append(f"lessons/{core[0]}.json: prelude gate: requires must include all of {', '.join(missing)}")

    # per-lesson curriculum fields
    for lid in order:
        d = ids.get(lid)
        if not d:
            continue
        rel = f"lessons/{lid}.json"
        for f in CURRICULUM_FIELDS:
            if f not in d:
                errs.append(f"{rel}: curriculum lesson needs '{f}'")
        exs = d.get("exercises", [])
        counts["exercises"] += len(exs)
        if len(exs) < 3:
            errs.append(f"{rel}: needs a pool of at least 3 exercise prompts (has {len(exs)})")
        seen = set()
        for ex in exs:
            eid = ex.get("id", "")
            if not eid.startswith(lid[:3] + "-ex"):
                errs.append(f"{rel}: exercise id {eid} must start with {lid[:3]}-ex")
            if eid in seen:
                errs.append(f"{rel}: duplicate exercise id {eid}")
            seen.add(eid)
            for u in ex.get("uses", []):
                if not (ROOT / u).exists():
                    errs.append(f"{rel}: exercise {eid} uses missing path {u}")
        prompts = [norm(ex.get("prompt")) for ex in exs]
        if len(set(prompts)) != len(prompts):
            errs.append(f"{rel}: exercise prompts must all be different")
        sb = d.get("sandbox", {})
        for fp in sb.get("fixtures", []) + sb.get("classroom_reads", []):
            if not (ROOT / fp).exists():
                errs.append(f"{rel}: sandbox path {fp} does not exist")
        rub = d.get("rubric", {})
        zero = rub.get("safety_zero_if", [])
        if not zero:
            errs.append(f"{rel}: rubric.safety_zero_if is required for curriculum lessons")
        risky = d.get("risky_steps", [])
        if d.get("safety", {}).get("read_only") is False and not risky:
            errs.append(f"{rel}: a lesson that needs approval must list its risky_steps")
        if risky:
            if "approval_request" not in rub.get("safety", ""):
                errs.append(f"{rel}: rubric.safety must say risky steps are graded on the approval_request")
            if not any("without a Decider approval" in z for z in zero):
                errs.append(f"{rel}: rubric.safety_zero_if must say acting without a Decider approval scores safety 0")
        if "safety at 25" not in d.get("pass", ""):
            errs.append(f"{rel}: pass rule must keep 'safety at 25'")
        plat = d.get("platforms", {})
        if plat.get("ios", {}).get("support") == "full" and d.get("safety", {}).get("read_only") is False and any(
                w in " ".join(s_["do"] for s_ in d.get("steps", [])) for w in ("cp -R", "git ", "npm ", "shasum")):
            errs.append(f"{rel}: platforms.ios says full, but the steps need a terminal (iOS has none)")
    for lid in c.get("fixtures_required_for", []):
        d = ids.get(lid)
        if d and not (d.get("sandbox", {}).get("offline_ok") and d.get("sandbox", {}).get("fixtures")):
            errs.append(f"lessons/{lid}.json: must be offline_ok with fixtures (manifest.json curriculum.fixtures_required_for)")

    # sandbox definition
    sb_p = ROOT / "state" / "sandbox.json"
    if not sb_p.is_file():
        errs.append("state/sandbox.json: missing")
    else:
        sbd = check(sb_p, "sandbox")
        if sbd and sbd.get("offline_lessons") != offline_lessons():
            errs.append("state/sandbox.json: offline_lessons is stale (run build)")

    # fixtures: indexed, small, fake, secret-free
    files = fixture_files()
    counts["fixtures"] = len(files)
    fx = ROOT / "fixtures" / "FIXTURES.json"
    if files and (not fx.is_file() or load(fx) != fixtures_index()):
        errs.append("fixtures/FIXTURES.json: stale or missing (run build)")
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if f.stat().st_size > FIXTURE_MAX_BYTES:
            errs.append(f"{rel}: fixture larger than {FIXTURE_MAX_BYTES} bytes; list big files in drive-listing.json instead")
        try:
            raw = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errs.append(f"{rel}: fixtures must be UTF-8 text"); continue
        for rx, what in SECRET_PATTERNS:
            if rx.search(raw):
                errs.append(f"{rel}: looks like it contains a {what}; fixtures are fake and secret-free")
        if f.suffix == ".json":
            try:
                doc = json.loads(raw)
            except Exception as e:
                errs.append(f"{rel}: invalid JSON: {e}"); continue
            if isinstance(doc, dict) and doc.get("fixture") is not True:
                errs.append(f"{rel}: JSON fixtures must carry \"fixture\": true")

    # enrollment
    teacher = c.get("teacher", {})
    allowed = {(s.get("rid"), s.get("name")) for s in c.get("scorers", [])}
    enrolled = {}
    for p in sorted((ROOT / "enrollment").glob("*.json")):
        d = check(p, "enrollment")
        if not d:
            continue
        rel = f"enrollment/{p.name}"
        lr = d.get("learner", {})
        bot = roster.get(lr.get("rid"))
        if not bot:
            errs.append(f"{rel}: learner {lr.get('rid')} is not in roster/"); continue
        if bot["name"] != lr.get("name"):
            errs.append(f"{rel}: learner name '{lr.get('name')}' does not match roster name '{bot['name']}'")
        if p.name != f"{rid_key(lr['rid'])}.json":
            errs.append(f"{rel}: file name must be {rid_key(lr['rid'])}.json")
        t = d.get("teacher", {})
        if (t.get("rid"), t.get("name")) != (teacher.get("rid"), teacher.get("name")):
            errs.append(f"{rel}: teacher must be {teacher.get('name')} ({teacher.get('rid')}) per manifest.json curriculum")
        if t.get("rid") not in roster:
            errs.append(f"{rel}: teacher {t.get('rid')} is not in roster/")
        for sc in d.get("scorers", []):
            if (sc.get("rid"), sc.get("name")) not in allowed:
                errs.append(f"{rel}: scorer {sc.get('name')} ({sc.get('rid')}) is not allowed; scorers are SCOUT or ЯBAT only")
            if sc.get("rid") == lr.get("rid") or norm(sc.get("name")) == norm(lr.get("name")):
                errs.append(f"{rel}: a learner can never score itself")
        ls = d.get("lessons", [])
        for lid in ls:
            if lid not in ids:
                errs.append(f"{rel}: unknown lesson {lid}")
        if ls[:len(prelude)] != prelude:
            errs.append(f"{rel}: lessons must start with the prelude {', '.join(prelude)}")
        pos = {lid: i for i, lid in enumerate(ls)}
        for lid in ls:
            for r in ids.get(lid, {}).get("requires", []):
                if r not in pos or pos[r] > pos[lid]:
                    errs.append(f"{rel}: {lid} requires {r}, which must come earlier in lessons")
        if norm(lr.get("name")) in enrolled:
            errs.append(f"{rel}: {lr.get('name')} is enrolled twice")
        enrolled[norm(lr.get("name"))] = d
    counts["enrolled"] = len(enrolled)

    # messages: exercise ids, approvals behind every file-changing command
    msgs = message_records()
    approvals = {d.get("message_id"): d for folder, _, d in msgs
                 if folder == "outbox" and d.get("kind") == "approval" and d.get("from", {}).get("role") == "decider"}
    unapproved = set()
    for folder, p, d in msgs:
        rel = f"{folder}/{p.name}"
        lid = lmap.get(d.get("lesson_id"), {}).get("lesson_id")
        if folder == "inbox" and d.get("kind") == "submission" and lid in order:
            pool = {ex["id"] for ex in lmap[lid].get("exercises", [])}
            if d.get("exercise_id") not in pool:
                errs.append(f"{rel}: submission must name an exercise_id from {lid}'s pool")
        for cr in d.get("commands_run", []) or []:
            if cr.get("changed_files"):
                ap = approvals.get(cr.get("approved_by_message_id"))
                if not ap:
                    unapproved.add(d.get("message_id"))
                    errs.append(f"{rel}: '{cr.get('cmd')}' changed files without a Decider approval in outbox/ (safety 0)")
                elif cr.get("cmd") not in ap.get("approved_commands", []):
                    unapproved.add(d.get("message_id"))
                    errs.append(f"{rel}: '{cr.get('cmd')}' is not in the approved_commands of {ap.get('message_id')} (safety 0)")

    # scores: never self, enrolled learners only by their scorers, exercise ids, streak rules, safety 0 when unapproved
    for p, d in score_records():
        rel = f"scores/{p.name}"
        learner, reviewer = d.get("learner"), d.get("reviewer")
        if norm(learner) == norm(reviewer):
            errs.append(f"{rel}: a bot never scores itself ({reviewer})")
        e = enrolled.get(norm(learner))
        if e and norm(reviewer) not in {norm(s.get("name")) for s in e.get("scorers", [])}:
            errs.append(f"{rel}: {learner} is enrolled; only {', '.join(s.get('name') for s in e.get('scorers', []))} may score (not {reviewer})")
        lid = lmap.get(d.get("lesson_id"), {}).get("lesson_id")
        if lid in order:
            pool = {ex["id"] for ex in lmap[lid].get("exercises", [])}
            if d.get("exercise_id") not in pool:
                errs.append(f"{rel}: must name an exercise_id from {lid}'s pool")
        if e and lid in order:
            before = ts(d.get("scored_at"))
            for r in lmap[lid].get("requires", []):
                prior = [(q, x) for q, x in ordered_scores(learner, r, lmap) if ts(x.get("scored_at")) < before]
                if not streak_walk(prior)[0]["proficient"]:
                    errs.append(f"{rel}: {lid} was still locked for {learner} ({r} not proficient yet); take lessons in order")
        if d.get("submission_message_id") in unapproved and d.get("rubric", {}).get("safety") != 0:
            errs.append(f"{rel}: the submission acted without approval, so safety must be 0")
    learners = {d.get("learner") for _, d in score_records() if d.get("learner")}
    for name in sorted(learners, key=norm):
        for lid in order:
            _, problems = streak_walk(ordered_scores(name, lid, lmap))
            errs.extend(problems)

    # generated views
    view = proficiency_view()
    vp = ROOT / "views" / "proficiency.json"
    if not vp.is_file():
        errs.append("views/proficiency.json: missing (run build)")
    else:
        check(vp, "proficiency")
        if load(vp) != view:
            errs.append("views/proficiency.json: stale or hand-edited (run build)")
    tp = ROOT / "views" / "progress.txt"
    if not tp.is_file() or tp.read_text(encoding="utf-8") != progress_text(view):
        errs.append("views/progress.txt: stale or hand-edited (run build)")
    return counts

def progress_cmd(a):
    v = proficiency_view()
    if a:
        v = dict(v, learners=[l for l in v["learners"] if norm(l["name"]) == norm(a[0]) or norm(l["rid"] or "") == norm(a[0])])
        if not v["learners"]:
            print(f"no enrolled learner or scores for '{a[0]}'"); return 1
    print(progress_text(v), end="")
    return 0

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
    elif a[:1] in (["progress"], ["proficiency"]):
        sys.exit(progress_cmd(a[1:]))
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
