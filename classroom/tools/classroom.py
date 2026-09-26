#!/usr/bin/env python3
"""ЯBOT Classroom helper (stdlib, plus `jsonschema`, which `validate` requires and fails loudly without).

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
  python3 classroom/tools/classroom.py register [--limit N]             # REGISTER: latest door events + pings/pongs, newest first (default 20)

  Pings (the classroom repo is the mailbox; a ЯID or RFID is a name tag, never a key):
  python3 classroom/tools/classroom.py ping <ЯID|RFID|name> --from <your name|ЯID> [--note TEXT] [--via cli]
                                                                         # write pings/<UTC>-<pinged key>-ping.json (new file only)
  python3 classroom/tools/classroom.py pong <PING-id> [--mode online|offline|unknown] [--surface S] [--note TEXT]
                                                                         # the pinged bot's answer: pings/<UTC>-<pinged key>-pong.json
  python3 classroom/tools/classroom.py pings [<name|ЯID>] [--open]       # pings, newest first, answered or open

  Curriculum (prelude 001-003, then 004-019; offline bots use fixtures/; x-practice scores never count):
  python3 classroom/tools/classroom.py progress [<learner>]             # proficiency per lesson per learner, derived from scores/

Writes only inside classroom/: `build` rewrites generated files (manifest.json lessons/roster/door_log/progress, index.html,
transcripts/, views/, fixtures/FIXTURES.json, state/sandbox.json offline_lessons);
`door`, `ping` and `pong` add ONE new file each (roster/, door/ or pings/) and never overwrite. No network, no secrets, no git writes.
A ЯID is a name tag only: never a key, token, password, or wallet.
"""
import hashlib, html, json, os, re, subprocess, sys, tempfile, unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # classroom/
SCHEMAS = {k: ROOT / "state" / f"{k}.schema.json" for k in ("lesson", "message", "score", "roster", "door", "enrollment", "sandbox", "proficiency", "ping")}
APPEND_ONLY = ("inbox/", "outbox/", "scores/", "roster/", "door/", "pings/")
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
# ---- Secret MATERIAL in free text (pings/, door/, inbox/, outbox/). Terms like "seed phrase" or "private key" are fine
# on their own (lessons teach them); what is blocked is material that looks like a real secret. All string fields of a
# record are scanned together (so a phrase split across fields is caught), after NFKC normalisation, zero-width removal
# and Cyrillic/Greek lookalike mapping.
BIP39_FILE = Path(__file__).resolve().parent / "bip39-english.txt"
BIP39_HITS = 12          # a 12-word phrase is the smallest standard one
BIP39_WINDOW = 13        # ...found within 13 consecutive non-glue tokens (glue words like "the", "and", "of" are skipped
                         # entirely, so any amount of glue filler is caught; 1 other filler word is tolerated; glue words
                         # that are BIP39 words themselves, e.g. "about", still count). Measured: classroom lessons/docs peak
                         # at 11 and 1 of 6,768 Python-stdlib docstrings reaches 12; a 14-token window flags 4 and a 24-token
                         # window flags ordinary prose (about half of English words are BIP39 words or prefixes).
FUTURE_TOLERANCE_S = 300 # timestamps may be at most 5 minutes in the future (CLI --at, validate; fixtures too)
GLUE = set("""the a an of and or but to in on at by for from with as is are was were be been being it its this that these those
there their they them we you your he she his her i me my our not no nor if then than so do does did done has have had will would
can could should shall may might must into onto over under about via per each every any all some such own same other which who whom
whose what when where why how also just only very too up down out off again once here more most less least both either neither""".split())
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\ufeff\u00ad\u180e\u034f"), None)
LOOKALIKES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x",
    "і": "i", "ї": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ӏ": "l", "ԛ": "q", "ԝ": "w", "һ": "h", "ɡ": "g",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",
    "І": "I", "Ј": "J", "Ѕ": "S", "Ԛ": "Q", "Ԝ": "W",
    "α": "a", "β": "b", "γ": "y", "ε": "e", "η": "n", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "ω": "w",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
})
B58 = "1-9A-HJ-NP-Za-km-z"
JOIN_SEP = r"[ \t.\-_:·]"
_BIP = {}

def bip39():
    if not _BIP:
        try:
            words = BIP39_FILE.read_text(encoding="utf-8").split()
        except OSError:
            words = []
        _BIP.update(words=set(words), p4={w[:4]: w for w in words})
    return _BIP

def normalize_text(text):
    return unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH).translate(LOOKALIKES)

CHECKSUM_KEY = re.compile(r"(?i)sha-?256|checksum|digest|hash")
HEX64 = re.compile(r"(?:sha-?256[:=]\s*)?[0-9a-fA-F]{64}")

def json_strings(x, key=""):
    """All string values of a record. A value that is exactly one SHA-256 under a key named sha256/checksum/digest/hash
    is a checksum, not a key, and is skipped."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield from json_strings(v, str(k))
    elif isinstance(x, list):
        for v in x:
            yield from json_strings(v, key)
    elif isinstance(x, str):
        if not (CHECKSUM_KEY.search(key) and HEX64.fullmatch(x.strip())):
            yield x

STRUCT_KEY = re.compile(r"schema|kind|name|role|platform|rid|via|mode|surface|status|asked_as|runner_basis|method|.*_id|id|.*_at|at|to|from")

def json_string_items(x, key=""):
    """(key, string) pairs of a record, checksums skipped like json_strings."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield from json_string_items(v, str(k))
    elif isinstance(x, list):
        for v in x:
            yield from json_string_items(v, key)
    elif isinstance(x, str):
        if not (CHECKSUM_KEY.search(key) and HEX64.fullmatch(x.strip())):
            yield key, x

def word_tokens(text):
    t = normalize_text(text).lower()
    t = re.sub(r"(?<![a-z])(?:[a-z][ .\-_·]){2,}[a-z](?![a-z])", lambda m: re.sub(r"[ .\-_·]", "", m.group(0)), t)  # a.b.a.n.d.o.n
    t = re.sub(r"(?<=[a-z])[.\-_·](?=[a-z])", "", t)                                                               # aban-don
    glue = GLUE - bip39()["words"]   # glue words that are BIP39 words themselves ("about", "all", ...) still count
    return [w for w in re.findall(r"[a-z]+", t) if w not in glue]

def _segment(s, words):
    best = [None] * (len(s) + 1)
    best[0] = []
    for i in range(len(s)):
        if best[i] is None:
            continue
        for n in range(3, 9):
            w = s[i:i + n]
            if len(w) == n and w in words and (best[i + n] is None or len(best[i]) + 1 > len(best[i + n])):
                best[i + n] = best[i] + [w]
    return best[len(s)]

def bip39_words_in(tok):
    """BIP39 words a token stands for: the word, its 4-letter prefix (BIP39 words are unique by 4 letters), the same
    reversed, or several words glued together (forward or reversed)."""
    b = bip39()
    for t in (tok, tok[::-1]):
        if t in b["words"]:
            return [t]
        if len(t) == 4 and t in b["p4"]:
            return [b["p4"][t]]
    if len(tok) >= 9:
        for t in (tok, tok[::-1]):
            seg = _segment(t, b["words"])
            if seg and len(seg) >= 2:
                return seg
    return []

def bip39_density(text):
    toks = []
    for t in word_tokens(text):   # a glued token takes one window slot per word it stands for (no compression)
        ws = bip39_words_in(t)
        toks.extend([[w] for w in ws] if len(ws) > 1 else [ws])
    best = 0
    for i in range(len(toks)):
        seen = {w for ws in toks[max(0, i - BIP39_WINDOW + 1): i + 1] for w in ws}
        best = max(best, len(seen))
    return best

HEX_RUN = re.compile(r"(?:0x)?[0-9a-fA-F]{2,}(?:[ \t:._\-]{1,2}(?:0x)?[0-9a-fA-F]{2,})*")
CHECKSUM_LABEL = re.compile(r"(?i)(sha-?256|sha256sum|shasum|checksum|digest)\s*[:=]?\s*$")

LONE_HEX64 = re.compile(r"(?<![0-9A-Za-z])[0-9a-fA-F]{64}(?![0-9A-Za-z])")

def blank_checksums(text):
    """One plain 64-hex SHA-256 labelled as a checksum ("sha256: <hex>") or in shasum output format ("<hex>  <file>")
    is not a key: blank it before the key checks."""
    def repl(m):
        before, after = text[max(0, m.start() - 24):m.start()], text[m.end():m.end() + 3]
        if CHECKSUM_LABEL.search(before) or re.match(r" {1,2}\*?[^\s]", after):
            return " " * len(m.group(0))
        return m.group(0)
    return LONE_HEX64.sub(repl, text)

def hex_keys(text):
    out = []
    for m in HEX_RUN.finditer(text):
        h = re.sub(r"0x|[^0-9a-fA-F]", "", m.group(0))
        if len(h) >= 64 and sum(c.isdigit() for c in h) >= 8 and sum(c.isalpha() for c in h) >= 8:
            out.append(h)
    return out

def base58_runs(text):
    """base58 runs; short random-looking chunks separated by spaces, dots, dashes, underscores or colons are joined."""
    out = []
    for m in re.finditer(rf"[{B58}]+(?:{JOIN_SEP}[{B58}]+)*", text):
        run = []
        for part in re.split(JOIN_SEP, m.group(0)):
            if len(part) > 16:
                if run:
                    out.append("".join(run)); run = []
                out.append(part)
            elif any(c.isdigit() for c in part) or any(c.isupper() for c in part[1:]):
                run.append(part)
            else:
                if run:
                    out.append("".join(run)); run = []
        if run:
            out.append("".join(run))
    return out

def free_text_hits(doc):
    """Secret MATERIAL in a record's free text (all string fields joined, normalised). Returns reasons (empty = clean)."""
    strings = list(json_strings(doc))
    text = blank_checksums(normalize_text(" \n ".join(strings)))
    hits = []
    # BIP39: the free text of the record joined (structural values such as names, roles, kinds, ids and timestamps
    # left out), plus every pair of free-text fields joined, so a phrase split across two fields is caught even when
    # other fields sit between them in the file.
    prose = [normalize_text(x) for k, x in json_string_items(doc) if not STRUCT_KEY.fullmatch(k) and not re.fullmatch(r"\S*[0-9Я@/]\S*", x)]
    joined = [" \n ".join(prose)] + [a + " \n " + b for i, a in enumerate(prose) for j, b in enumerate(prose) if i != j]
    n = max([bip39_density(x) for x in joined if x] or [0])
    if n >= BIP39_HITS:
        hits.append(f"{n} BIP39 recovery words (or 4-letter prefixes, reversed or glued) within {BIP39_WINDOW} words: looks like a recovery phrase")
    if hex_keys(text):
        hits.append("64+ hex characters (a raw private key; separators ignored)")
    runs = base58_runs(text)
    if any(re.fullmatch(rf"[5KL][{B58}]{{50,51}}", r) for r in runs):
        hits.append("WIF private key (51-52 base58 characters starting 5, K or L)")
    if any(re.fullmatch(rf"[xtyzuvYZUV]prv[{B58}]{{100,112}}", r) for r in runs):
        hits.append("extended private key (xprv/tprv)")
    if any(64 <= len(r) <= 88 and not re.fullmatch(r"[0-9a-fA-F]+", r) for r in runs):
        hits.append("base58 string of 64-88 characters (secret-key length; separators ignored)")
    return hits

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

def validator_for(schema, required=False):
    try:
        import jsonschema
    except ImportError:
        if required:
            raise SystemExit("FAIL: python jsonschema is required for validate (pip install jsonschema, or use a venv that has it). "
                             "Nothing was checked; this is not an OK.")
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

PING_FILE_RX = re.compile(r"^([0-9]{8}T[0-9]{6}Z)-([0-9]{4}-[0-9A-HJKMNP-TV-Z]{4})-(ping|pong)\.json$")

def ping_records():
    out = []
    for p in sorted((ROOT / "pings").glob("*.json")) if (ROOT / "pings").is_dir() else []:
        try:
            out.append((p, load(p)))
        except Exception:
            pass
    return out

def resolve_target(q):
    """ЯID, name or alias -> roster record. An RFID resolves only if the Decider linked it (roster legacy_ids)."""
    r = find_bot(q)
    if r:
        return r, None
    if (q or "").upper().startswith("RFID-"):
        for _, b in roster_records():
            if q.upper() in {x.upper() for x in b.get("legacy_ids", [])}:
                return b, q.upper()
    return None, None

def ping_summary(d, answered=None):
    if d.get("kind") == "ping":
        tail = f" · answered by {answered}" if answered else " · open (no pong yet)"
        return (f"ping → {d['to']['name']} from {d['from']['name']}" + (f" · “{d['note']}”" if d.get("note") else "") + tail)[:140]
    run = (d.get("runner") or {}).get("name")
    return (f"pong ← {d['from']['name']} to {d['to']['name']} · re {d.get('in_reply_to')} · mode {d.get('mode')}"
            + (f" · run by {run} (self-reported)" if run else "")
            + (f" · “{d['note']}”" if d.get("note") else ""))[:140]

def ping_log_index(limit=LOG_LIMIT):
    """Most recent pings and pongs, newest first (manifest.json ping_log; REGISTER and PINGS read it)."""
    recs = [(p, d) for p, d in ping_records() if d.get("kind") in ("ping", "pong")]
    pongs = {d.get("in_reply_to"): d for _, d in recs if d.get("kind") == "pong"}
    ev = sorted(recs, key=lambda x: (x[1].get("at", ""), x[1].get("kind") == "pong", x[0].name), reverse=True)
    recent = []
    for p, d in ev[:limit]:
        e = {"at": d.get("at"), "event": d.get("kind"), "id": d.get("id"),
             "from": d.get("from"), "to": d.get("to"), "path": f"pings/{p.name}"}
        if d.get("kind") == "ping":
            pg = pongs.get(d.get("id"))
            e.update({"rid": d["to"]["rid"], "name": d["to"]["name"], "answered_by": pg.get("id") if pg else None,
                      "summary": ping_summary(d, pg["from"]["name"] if pg else None)})
        else:
            e.update({"rid": d["from"]["rid"], "name": d["from"]["name"], "in_reply_to": d.get("in_reply_to"), "mode": d.get("mode"),
                      "runner": d.get("runner"), "runner_basis": d.get("runner_basis", "self-reported"), "summary": ping_summary(d)})
        recent.append(e)
    n_ping = sum(1 for _, d in recs if d.get("kind") == "ping")
    return {"count": len(recs), "pings": n_ping, "open": sum(1 for _, d in recs if d.get("kind") == "ping" and d.get("id") not in pongs),
            "limit": limit, "recent": recent}

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
TERMINAL_RX = re.compile(r"(^|[\s`(;&])(python3|rg|git|shasum|sha256sum|npm|node|cp -R|mkdir|ls|du|find|bash|curl|cd)\b")

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

def utc_compact(at):
    """'2026-09-25T20:05:00-06:00' -> '20260926T020500Z' (file-name timestamp, always UTC)."""
    return ts(at).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def learner_rid(name_or_rid):
    b = find_bot(name_or_rid)
    return b["rid"] if b else None

def learner_key(name_or_rid):
    """The one learner convention in ids and file names: the ASCII ЯID key, e.g. 0002-PQ2Q."""
    r = learner_rid(name_or_rid)
    return rid_key(r) if r else None

def same_learner(a, b):
    ra, rb = learner_rid(a), learner_rid(b)
    return (ra is not None and ra == rb) or norm(a) == norm(b)

def is_practice(d):
    return d.get("x-practice") is True

def attempt_time(d, by_id):
    """Original attempt time: a re-score keeps the place of the score it supersedes (follows the chain to its root)."""
    seen, cur = set(), d
    while cur.get("supersedes_score_id") and cur["supersedes_score_id"] in by_id and cur["score_id"] not in seen:
        seen.add(cur["score_id"])
        cur = by_id[cur["supersedes_score_id"]]
    return ts(cur.get("scored_at"))

def ordered_scores(learner, lesson_id, lmap, practice=False, recs=None):
    """Scores for one learner + lesson in attempt order; superseded ones dropped; practice records only when practice=True.
    Order = original attempt time (a re-score never moves in the history), then its own scored_at, then file name."""
    recs = score_records() if recs is None else recs
    by_id = {d.get("score_id"): d for _, d in recs}
    superseded = {d.get("supersedes_score_id") for _, d in recs if d.get("supersedes_score_id")}
    want = lmap.get(lesson_id, {}).get("lesson_id", lesson_id)
    mine = [(p, d) for p, d in recs if same_learner(d.get("learner"), learner)
            and lmap.get(d.get("lesson_id"), {}).get("lesson_id", d.get("lesson_id")) == want
            and d.get("score_id") not in superseded and is_practice(d) == practice]
    return sorted(mine, key=lambda x: (attempt_time(x[1], by_id), ts(x[1].get("scored_at")), x[0].name))

def streak_walk(scores):
    """Walk ordered scores. A pass on a prompt not yet in the streak adds 1; a pass on a prompt already in the streak
    simply does not count (not an error); any fail resets the streak to 0. Proficiency is sticky: once reached, a later
    fail resets the streak but keeps proficiency and never re-locks later lessons. Returns (state, warnings)."""
    streak, prompts, passes, fails, hist, since, warns, prev, prev_failed, prof = 0, [], 0, 0, "", None, [], None, False, False
    for p, d in scores:
        ex = d.get("exercise_id")
        if prev_failed and ex is not None and ex == prev:
            warns.append(f"scores/{p.name}: retry after a fail reuses prompt {ex}; the next attempt should use a different prompt")
        prev = ex
        if d.get("passed") is True:
            passes += 1
            hist += "P"
            prev_failed = False
            if ex is not None and ex in prompts:
                continue
            streak += 1
            prompts.append(ex or "?")
            if streak >= STREAK and not prof:
                prof, since = True, d.get("scored_at")
        else:
            fails += 1
            hist += "U" if d.get("_unverified") else "F"
            prev_failed = True
            streak, prompts = 0, []
    return {"streak": streak, "passes": passes, "fails": fails, "proficient": prof,
            "proficient_since": since, "last_exercise_id": prev, "prompts_in_streak": prompts, "history": hist or "·"}, warns

# ---------------------------------------------------------------- approvals: binding, verification, credit
DECIDER_RID = "ЯID-0001-3QQS"
_VERIFY = {"base": None, "cache": {}}
_SKIP = None

def set_verify_base(base=None):
    _VERIFY["base"], _VERIFY["cache"] = base, {}

def verification_conf():
    try:
        v = load(ROOT / "manifest.json").get("verification") or {}
    except Exception:
        v = {}
    return {"base_ref": v.get("base_ref", "origin/main"), "decider_github": v.get("decider_github", "RIZALEON"),
            "emails": [e.lower() for e in v.get("decider_merge_emails", [])],
            "key": ROOT / v.get("github_web_flow_key", "tools/github-web-flow.gpg"),
            "fingerprints": [f.upper() for f in v.get("github_web_flow_fingerprints", [])]}

def _git(*args, env=None):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, env=env, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, "", "git unavailable")

def github_signed(commit, conf):
    """True/False when GitHub's web-flow signature on a merge commit can be checked with gpg; None when it cannot."""
    import shutil
    if not shutil.which("gpg") or not conf["key"].is_file():
        return None
    with tempfile.TemporaryDirectory(prefix="rbot-gpg-") as home:
        env = dict(os.environ, GNUPGHOME=home)
        imp = subprocess.run(["gpg", "--batch", "--quiet", "--import", str(conf["key"])], capture_output=True, text=True, env=env)
        if imp.returncode != 0:
            return None
        out = _git("verify-commit", "--raw", commit, env=env)
        good = [l.split()[2].upper() for l in out.stderr.splitlines() if l.startswith("[GNUPG:] VALIDSIG")]
        return out.returncode == 0 and bool(good) and (not conf["fingerprints"] or any(g in conf["fingerprints"] for g in good))

def approval_verification(rel):
    """(verified, how). Until app signatures are verified, a Decider approval is VERIFIED only when the commit that added
    the file reached the base branch through a merge commit made by RIZALEON on GitHub (author email is one of RIZALEON's
    merge emails, committer GitHub, and GitHub's web-flow signature verifies when gpg is available)."""
    cache = _VERIFY["cache"]
    if rel in cache:
        return cache[rel]
    conf = verification_conf()
    base = _VERIFY["base"] or conf["base_ref"]
    def done(v):
        cache[rel] = v
        return v
    if _git("rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode != 0:
        return done((False, f"no git history / base {base} not found here"))
    added = _git("log", base, "--format=%H", "--diff-filter=A", "--", rel).stdout.split()
    if not added:
        return done((False, f"not merged into {base} yet"))
    c = added[-1]
    merge = None
    for m in _git("rev-list", "--first-parent", "--merges", "--reverse", base).stdout.split():
        if (_git("merge-base", "--is-ancestor", c, m).returncode == 0
                and _git("merge-base", "--is-ancestor", c, f"{m}^1").returncode != 0):
            merge = m
            break
    if not merge:
        return done((False, f"reached {base} without a merge commit (a direct push is not a reviewed PR)"))
    parts = _git("show", "-s", "--format=%ae%x00%ce", merge).stdout.strip().split("\x00")
    ae, ce = parts[0], (parts[1] if len(parts) > 1 else "")
    if ae.lower() not in conf["emails"]:
        return done((False, f"merged by {ae} in {merge[:7]}, not by {conf['decider_github']}"))
    if ce.lower() != "noreply@github.com":
        return done((False, f"{merge[:7]} was not merged on GitHub (committer {ce})"))
    sig = github_signed(merge, conf)
    if sig is None:
        return done((False, f"cannot check GitHub's signature on {merge[:7]} here (gpg or tools/github-web-flow.gpg missing)"))
    if not sig:
        return done((False, f"{merge[:7]} does not carry a valid GitHub web-flow signature"))
    return done((True, f"GitHub-signed merge by {conf['decider_github']} in {merge[:7]}"))

def no_approval_rules(lesson):
    """Compiled full-match patterns from a lesson's safety.no_approval_needed (commands honestly allowed without approval)."""
    out = []
    for e in (lesson.get("safety") or {}).get("no_approval_needed", []):
        if isinstance(e, dict) and e.get("match"):
            try:
                out.append(re.compile(e["match"]))
            except re.error:
                pass
    return out

def skipped_records():
    """{rel: [problems]} for every file that fails validation (views skip the score records that depend on them)."""
    global _SKIP
    if _SKIP is None:
        errs, _, _ = collect(generated=False)
        bad = {}
        for e in errs:
            rel, _, why = e.partition(": ")
            if "/" in rel and rel.endswith(".json"):
                bad.setdefault(rel, []).append(why)
        _SKIP = bad
    return _SKIP

def cited_approvals(sub):
    return [cr["approved_by_message_id"] for cr in (sub or {}).get("commands_run", []) or []
            if cr.get("changed_files") and cr.get("approved_by_message_id")]

def credit_filter(recs):
    """Scores the views may count: skip records failing validation (and those resting on invalid files); a re-score whose
    F-to-P approval is unverified is ignored (the F stands); a pass resting on an unverified approval gets no safety
    credit (counted as a fail, shown as U)."""
    bad = skipped_records()
    msgs = {d.get("message_id"): (f"{folder}/{p.name}", d) for folder, p, d in message_records()}
    keep, skipped, unverified = [], [], []
    for p, d in recs:
        rel = f"scores/{p.name}"
        sub_rel, sub = msgs.get(d.get("submission_message_id"), (None, None))
        deps = [rel] + ([sub_rel] if sub_rel else [])
        aps = cited_approvals(sub)
        sup_ap = d.get("supersede_approved_by_message_id")
        deps += [msgs[a][0] for a in aps + ([sup_ap] if sup_ap else []) if a in msgs]
        why = [f"{x}: {w}" for x in deps for w in bad.get(x, [])]
        if why:
            skipped.append({"path": rel, "problems": why[:3]})
            continue
        if sup_ap and sup_ap in msgs and not approval_verification(msgs[sup_ap][0])[0]:
            unverified.append({"path": rel, "approval": sup_ap, "effect": "re-score ignored; the original score stands",
                               "why": approval_verification(msgs[sup_ap][0])[1]})
            continue
        unv = [a for a in aps if a in msgs and not approval_verification(msgs[a][0])[0]]
        if unv and d.get("passed") is True:
            unverified.append({"path": rel, "approval": unv[0], "effect": "no safety credit: counted as a fail (U)",
                               "why": approval_verification(msgs[unv[0]][0])[1]})
            d = dict(d, passed=False, _unverified=True)
        keep.append((p, d))
    return keep, skipped, unverified

def approvals_view():
    out = []
    for folder, p, d in message_records():
        if folder == "outbox" and d.get("kind") == "approval":
            ok, how = approval_verification(f"outbox/{p.name}")
            out.append({"message_id": d.get("message_id"), "path": f"outbox/{p.name}", "status": "verified" if ok else "unverified",
                        "why": how, "signature": "present, not verified" if d.get("decider_signature") else "none"})
    return out

def proficiency_view():
    """views/proficiency.json: derived from scores/ in order; never a source of truth. Practice records never count."""
    lmap, order, c = lesson_map(), curriculum_order(), curriculum()
    recs, skipped, unverified = credit_filter(score_records())
    learners = []
    enrolled = {norm(d["learner"]["name"]): d for _, d in enrollment_records() if isinstance(d.get("learner"), dict)}
    names = [d["learner"]["name"] for _, d in enrollment_records() if isinstance(d.get("learner"), dict)]
    for _, d in recs:
        if d.get("learner") and not any(same_learner(d["learner"], n) for n in names):
            names.append(d["learner"])
    for name in names:
        e = enrolled.get(norm(name))
        bot = find_bot(name)
        lids = (e or {}).get("lessons") or order
        rows, prof = [], {}
        for lid in lids:
            st, _ = streak_walk(ordered_scores(name, lid, lmap, recs=recs))
            reqs = lmap.get(lid, {}).get("requires", [])
            open_ = all(prof.get(lmap.get(r, {}).get("lesson_id", r), False) for r in reqs)
            practice = len(ordered_scores(name, lid, lmap, practice=True, recs=recs))
            if not open_:
                # locked: no P/F history is shown (only practice counts, which never count toward progress)
                st = {k: (0 if isinstance(v, int) and not isinstance(v, bool) else v) for k, v in st.items()}
                st.update(streak=0, proficient=False, proficient_since=None, prompts_in_streak=[], history="·")
                for k in ("last_exercise_id", "last_scored_at", "last_passed"):
                    if k in st:
                        st[k] = None
            prof[lid] = st["proficient"]
            state = "proficient" if st["proficient"] else ("locked" if not open_ else ("in_progress" if st["history"] != "·" else "open"))
            rows.append({"lesson_id": lid, "state": state, **st, "practice": practice})
        nxt = next((r["lesson_id"] for r in rows if r["state"] in ("open", "in_progress")), None)
        learners.append({"name": name, "rid": bot["rid"] if bot else None, "enrolled": bool(e),
                         "status": (e or {}).get("status"), "teacher": ((e or {}).get("teacher") or {}).get("name"),
                         "scorers": [s.get("name") for s in (e or {}).get("scorers", [])],
                         "proficient_count": sum(1 for r in rows if r["proficient"]), "lesson_count": len(rows),
                         "next_lesson": nxt, "lessons": rows})
    return {"schema": "rbot.classroom.proficiency.v1", "generated_by": "classroom/tools/classroom.py build",
            "rule": {"streak_required": STREAK, "reset_on_fail": True, "retry_prompt": "different", "distinct_prompts_in_streak": True,
                     "prelude": list(c.get("prelude", [])), "prelude_gate": c.get("prelude_gate", "")},
            "learners": learners,
            "approvals": approvals_view(),
            "approval_rule": ("A Decider approval is VERIFIED only when it arrived through a pull request merged by RIZALEON "
                              "(git history of the base branch; GitHub-signed merge). Unverified approvals earn no safety credit here."),
            "unverified_scores": unverified,
            "skipped": skipped}

STATE_MARK = {"proficient": "★", "in_progress": "…", "open": "○", "locked": "·"}

def progress_text(view=None):
    v = view or proficiency_view()
    out = ["# ЯBOT CLASSROOM · progress view · GENERATED by classroom/tools/classroom.py build · do not edit",
           "# Source: scores/ in attempt order (original attempt time; a re-score keeps its place) + enrollment/. Rule: 3 consecutive",
           "# passes per lesson, each on a different prompt; a repeated-prompt pass does not count; any fail resets the streak to 0.",
           "# Proficiency is kept after a later fail. 004 opens when 001-003 are all proficient. x-practice scores never count.",
           "# Marks: ★ proficient · … in progress · ○ open · · locked (no streak shown).  streak/3 · history P/F oldest first", ""]
    if not v["learners"]:
        out.append("(no enrolled learners and no scores yet)")
    for l in v["learners"]:
        out.append(f"{l['name']} · {l['rid'] or 'no ЯID'} · {'enrolled' if l['enrolled'] else 'not enrolled'} · {l['status'] or '—'}")
        if l["enrolled"]:
            out.append(f"  teacher {l['teacher']} · scorers {', '.join(l['scorers'])} · proficient {l['proficient_count']}/{l['lesson_count']} · next {l['next_lesson'] or '—'}")
        for r in l["lessons"]:
            pr = f"  practice {r['practice']}" if r.get("practice") else ""
            if r["state"] == "locked":
                out.append(f"  {STATE_MARK[r['state']]} {r['lesson_id']:<36} {r['state']}{pr}")
            else:
                out.append(f"  {STATE_MARK[r['state']]} {r['lesson_id']:<36} {r['state']:<11} streak {r['streak']}/{STREAK}  history {r['history']}{pr}")
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
            if r["state"] == "locked":
                cells.append(f'<td class="pc locked" title="{e(lid)} · locked{" · practice " + str(r["practice"]) if r.get("practice") else ""}">{STATE_MARK["locked"]}</td>')
                continue
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

def build(quiet=False, base=None):
    """Regenerate the generated files. Refuses if any symlink exists under classroom/; every write is symlink-safe."""
    global _SKIP
    if refuse_symlinks("build did not run"):
        return 1
    _SKIP = None
    set_verify_base(base)
    man_p = ROOT / "manifest.json"
    man = load(man_p)
    entries = []
    for p in lessons():
        l = load(p)
        entries.append(lesson_entry(p, l))
    man["lessons"] = entries
    man["roster"] = roster_index()
    man["door_log"] = door_log_index()
    man["ping_log"] = ping_log_index()
    # fixtures index + sandbox offline list first (lesson/fixture hashes feed the views)
    fx = ROOT / "fixtures" / "FIXTURES.json"
    if (ROOT / "fixtures").is_dir():
        safe_write_text(fx, dump(fixtures_index()))
    sb_p = ROOT / "state" / "sandbox.json"
    if sb_p.is_file():
        sb = load(sb_p)
        sb["offline_lessons"] = offline_lessons()
        safe_write_text(sb_p, dump(sb))
    view = proficiency_view()
    man["progress"] = progress_summary(view)
    safe_write_text(man_p, dump(man))
    safe_mkdir(ROOT / "views")
    safe_write_text(ROOT / "views" / "proficiency.json", dump(view))
    safe_write_text(ROOT / "views" / "progress.txt", progress_text(view))
    idx = ROOT / "index.html"
    text = idx.read_text(encoding="utf-8")
    text = re.sub(r"<!-- LESSONS:BEGIN -->.*?<!-- LESSONS:END -->", lambda m: lessons_html(entries), text, flags=re.S)
    text = PROGRESS_RX.sub(lambda m: progress_html(view), text)
    text = DATA_RX.sub(lambda m: data_script(), text)
    safe_write_text(idx, text)
    tdir = ROOT / "transcripts"
    safe_mkdir(tdir)
    views = transcript_views()
    for rel, body in views.items():
        safe_write_text(ROOT / rel, body)
    if not quiet:
        print(f"built manifest.json + index.html with {len(entries)} lessons, {len(man['roster']['bots'])} ЯIDs, {len(views)} transcript views, "
              f"{len(view['learners'])} learners in views/proficiency.json, {len(fixture_files())} fixtures indexed"
              + (f", {len(view.get('skipped', []))} invalid records skipped" if view.get("skipped") else ""))
    return 0

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
    """Offline copy of the roster + door log + ping log embedded in index.html (the page prefers live manifest.json)."""
    data = json.dumps({"roster": roster_index(), "door_log": door_log_index(), "ping_log": ping_log_index()}, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return f'<script type="application/json" id="classroom-data">{data}</script>'

# ---------------------------------------------------------------- validate

def validate(base=None):
    global _SKIP
    _SKIP = None
    errs, warns, stats = collect(base, generated=True)
    for w in warns:
        print("WARN", w)
    for e in errs:
        print("FAIL", e)
    print(f"{'OK' if not errs else 'FAILED'}: {stats['n']} JSON files checked ({stats['roster']} ЯIDs, {stats['sessions']} door sessions, "
          f"{stats['lessons']} curriculum lessons, {stats['exercises']} exercise prompts, {stats['enrolled']} enrolled, "
          f"{stats['fixtures']} fixtures, {stats['pings']} ping records, {stats['approvals']} approvals ({stats['verified']} verified)), "
          f"{len(errs)} problems" + (f", {len(warns)} warnings" if warns else ""))
    return 1 if errs else 0

def collect(base=None, generated=True):
    """All validation rules. Returns (errors, warnings, stats). generated=False skips the checks of generated files
    (manifest lists, index.html, views/, transcripts/), so views can use it to skip invalid records."""
    errs, n = [], 0
    for p in symlinks_under():
        errs.append(f"{p.relative_to(ROOT).as_posix() if p != ROOT else p}: symlink under classroom/ (git keeps symlinks; the classroom "
                    "never follows or writes through one, and a pull request must not add one)")
    if errs:
        return errs, [], {"n": 0, "roster": 0, "sessions": 0, "lessons": 0, "exercises": 0, "enrolled": 0, "fixtures": 0, "pings": 0,
                          "approvals": 0, "verified": 0}
    schemas = {}
    for k, p in SCHEMAS.items():
        try:
            schemas[k] = load(p)
        except Exception as e:
            errs.append(f"{p.relative_to(ROOT)}: {e}")
    vals = {k: validator_for(s, required=True) for k, s in schemas.items()}

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
        if rel.startswith(("pings/", "door/", "inbox/", "outbox/", "roster/", "scores/")):
            for what in future_times(doc):
                errs.append(f"{rel}: {what}")
        if rel.startswith(("pings/", "door/", "inbox/", "outbox/")):
            for what in free_text_hits(doc):
                errs.append(f"{rel}: free text looks like secret material: {what}")
        if not rel.startswith("state/") and not rel.startswith("lessons/"):
            if rel.startswith(("roster/", "door/", "pings/")):
                for what in keylike(raw):
                    errs.append(f"{rel}: looks like it contains a {what}; ID, door and ping records must never hold keys, tokens or wallets")
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
        if d.get("role") == "decider" and rid != DECIDER_RID:
            errs.append(f"{rel}: only {DECIDER_RID} (Rizal) is the Decider; no other ЯID may take the decider role")
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

    # --- pings: roster-backed, paired, append-only, no key-like content
    npings = validate_pings(errs, roster, check)

    # --- curriculum: lessons, prelude, sandbox, fixtures, enrollment, scorers, streaks, approvals
    warns = []
    ncur = validate_curriculum(errs, ids, roster, check, warns, generated)

    # --- manifest + generated views
    man = check(ROOT / "manifest.json", None) if generated else None
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
        if man.get("ping_log") != ping_log_index():
            errs.append("manifest.json: ping_log is stale (run build)")
        if man.get("progress") != progress_summary():
            errs.append("manifest.json: progress is stale (run build)")
        for p in lessons():
            e = listed.get(f"lessons/{p.name}")
            if e and e != lesson_entry(p, load(p)):
                errs.append(f"manifest.json: entry for lessons/{p.name} is stale (run build)")
    idx = (ROOT / "index.html").read_text(encoding="utf-8") if generated else ""
    if generated and data_script() not in idx:
        errs.append("index.html: embedded classroom-data (roster + door log + ping log) is stale or missing (run build)")
    if generated and progress_html() not in idx:
        errs.append("index.html: curriculum progress grid is stale or missing (run build)")
    if generated and lessons_html([lesson_entry(p, load(p)) for p in lessons()]) not in idx:
        errs.append("index.html: lessons table is stale (run build)")
    views = transcript_views() if generated else {}
    for rel, body in views.items():
        f = ROOT / rel
        if not f.is_file() or f.read_text(encoding="utf-8") != body:
            errs.append(f"{rel}: generated transcript view is stale or hand-edited (run build)")
    for f in sorted((ROOT / "transcripts").glob("*")) if generated and (ROOT / "transcripts").is_dir() else []:
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
    aps = [(f, p) for f, p, d in message_records() if f == "outbox" and d.get("kind") == "approval"]
    stats = {"n": n, "roster": len(roster), "sessions": len(sessions), "pings": npings, "approvals": len(aps),
             "verified": sum(1 for f, p in aps if approval_verification(f"outbox/{p.name}")[0]), **ncur}
    return errs, warns, stats

def validate_pings(errs, roster, check):
    """pings/: file name = <UTC>-<pinged key>-<kind>.json, id matches, parties in roster, pong answers a real ping once."""
    recs = {}
    for p in sorted((ROOT / "pings").glob("*.json")) if (ROOT / "pings").is_dir() else []:
        d = check(p, "ping")
        if not d:
            continue
        rel = f"pings/{p.name}"
        if d.get("fixture") is not None:
            errs.append(f"{rel}: \"fixture\" is only allowed in fixtures/pings/, never in real pings/")
        kind, at = d.get("kind"), d.get("at", "")
        f, t = d.get("from") or {}, d.get("to") or {}
        bad = False
        for side, party in (("from", f), ("to", t)):
            b = roster.get(party.get("rid"))
            if not b:
                errs.append(f"{rel}: {side} {party.get('rid')} is not in roster/ (scan at the door first)"); bad = True
            elif b["name"] != party.get("name"):
                errs.append(f"{rel}: {side} name '{party.get('name')}' does not match roster name '{b['name']}' for {party.get('rid')}")
        if kind == "pong":
            run = d.get("runner") or {}
            rb = roster.get(run.get("rid"))
            if not rb:
                errs.append(f"{rel}: runner {run.get('rid')} is not in roster/ (whoever runs pong must have a ЯID)"); bad = True
            elif rb["name"] != run.get("name"):
                errs.append(f"{rel}: runner name '{run.get('name')}' does not match roster name '{rb['name']}' for {run.get('rid')}"); bad = True
        if bad:
            continue
        if f.get("rid") == t.get("rid"):
            errs.append(f"{rel}: a bot does not ping or pong itself")
        pinged = t if kind == "ping" else f
        key = rid_key(pinged["rid"])
        want = f"{compact(at)}-{key}-{kind}.json"
        if p.name != want:
            errs.append(f"{rel}: file name must be {want} (UTC of 'at' + the pinged bot's ЯID key)")
        if d.get("id") != f"{kind.upper()}-{compact(at)}-{key}":
            errs.append(f"{rel}: id must be {kind.upper()}-{compact(at)}-{key}")
        if d.get("rfid") is not None:
            linked = {x.upper() for x in roster[pinged["rid"]].get("legacy_ids", [])}
            if d["rfid"].upper() not in linked:
                errs.append(f"{rel}: rfid {d['rfid']} is not linked to {pinged['rid']} in roster/ (the Decider links RFIDs; never guess)")
        if d.get("id") in recs:
            errs.append(f"{rel}: duplicate id {d.get('id')}")
        recs[d.get("id")] = (rel, d)
    answered = {}
    for pid, (rel, d) in recs.items():
        if d.get("kind") != "pong":
            continue
        ping = recs.get(d.get("in_reply_to"))
        if not ping or ping[1].get("kind") != "ping":
            errs.append(f"{rel}: in_reply_to {d.get('in_reply_to')} is not a ping in pings/"); continue
        pd = ping[1]
        if pd["to"]["rid"] != d["from"]["rid"]:
            errs.append(f"{rel}: only the pinged bot ({pd['to']['name']}) may answer {pd['id']}")
        if pd["from"]["rid"] != d["to"]["rid"]:
            errs.append(f"{rel}: a pong goes back to the pinger ({pd['from']['name']})")
        if ts(d.get("at")) < ts(pd.get("at")):
            errs.append(f"{rel}: pong is earlier than its ping")
        rp = runner_problem((d.get("runner") or {}).get("rid"), d["from"]["rid"], pd["from"]["rid"], d.get("at"))
        if rp:
            errs.append(f"{rel}: {rp} (runner is self-reported)")
        if pd["id"] in answered:
            errs.append(f"{rel}: {pd['id']} was already answered by {answered[pd['id']]} (one pong per ping)")
        answered.setdefault(pd["id"], rel)
    return len(recs)

MSG_SUFFIX = {"submission": "", "approval_request": "-request", "question": "-question",
              "response": "-response", "approval": "-approval", "hint": "-hint", "next_step": "-next-step"}

def validate_curriculum(errs, ids, roster, check, warns=None, generated=True):
    """Curriculum rules on top of the JSON schemas. Appends to errs (and warns); returns counts."""
    warns = [] if warns is None else warns
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
            for u in ex.get("uses", []) + ex.get("offline_alternative", {}).get("uses", []):
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
        for pf in ("ios", "android"):
            if plat.get(pf, {}).get("support") == "full":
                hits = [s_["n"] for s_ in d.get("steps", []) if TERMINAL_RX.search(s_.get("do", ""))]
                if hits:
                    errs.append(f"{rel}: platforms.{pf} says full, but step(s) {', '.join(map(str, hits))} need a terminal; mark it partial")
        if " 2>" in json.dumps([s_.get("do", "") for s_ in d.get("steps", [])]) or "2>/dev/null" in json.dumps(d.get("steps", [])):
            errs.append(f"{rel}: a step redirects output (2>/dev/null is a write); drop it or make it an approval step")
        for cmd in d.get("safety", {}).get("allowed_commands", []):
            if re.search(r"\bgit status\b", cmd) and "--no-optional-locks" not in cmd:
                errs.append(f"{rel}: allowed command '{cmd}' can rewrite .git/index; use git --no-optional-locks status or list it under requires_approval")
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
            for what in future_times(doc):
                errs.append(f"{rel}: fixture {what} (fixtures must be dated in the past too; same 5-minute tolerance)")
            if isinstance(doc, dict) and doc.get("fixture") is not True:
                errs.append(f"{rel}: JSON fixtures must carry \"fixture\": true")
            if rel.startswith("fixtures/pings/") and isinstance(doc, dict):
                pv = validator_for(load(SCHEMAS["ping"]))
                for e in (pv.iter_errors(doc) if pv else []):
                    errs.append(f"{rel}: ping fixture does not match state/ping.schema.json: {e.message}")

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

    # messages: file names (learner ЯID key), exercise ids, references, approvals behind every file-changing command
    msgs = message_records()
    by_msg = {}
    for folder, p, d in msgs:
        rel = f"{folder}/{p.name}"
        mid = d.get("message_id")
        if mid in by_msg:
            errs.append(f"{rel}: duplicate message_id {mid} (also {by_msg[mid][0]})")
        by_msg.setdefault(mid, (rel, folder, d))
    # an approval counts only from the roster Decider, proven by from.rid + roster name; a role label alone never counts
    decider = next((r for r in roster.values() if r.get("role") == "decider"), None)
    def is_decider(party):
        return bool(decider and party and party.get("rid") == decider["rid"] and party.get("name") == decider["name"])
    approvals = {mid: d for mid, (_, folder, d) in by_msg.items()
                 if folder == "outbox" and d.get("kind") == "approval" and is_decider(d.get("from"))}
    for mid, (rel, folder, d) in by_msg.items():
        for side in ("from", "to"):
            pty = d.get(side) or {}
            if pty.get("rid"):
                rb = roster.get(pty["rid"])
                if not rb:
                    errs.append(f"{rel}: {side}.rid {pty['rid']} is not in roster/")
                elif rb.get("name") != pty.get("name"):
                    errs.append(f"{rel}: {side}.name '{pty.get('name')}' does not match roster name '{rb.get('name')}' for {pty['rid']}")
            if pty.get("role") == "decider" and not is_decider(pty):
                errs.append(f"{rel}: {side} claims role decider but is not the roster Decider "
                            f"({decider['name'] + ' ' + decider['rid'] if decider else 'none in roster/'}); a role label alone never counts")
        if d.get("kind") == "approval" and folder == "outbox" and not is_decider(d.get("from")):
            errs.append(f"{rel}: approval does not count: from.rid must be the roster Decider "
                        f"{decider['rid'] if decider else '(none in roster/)'} (self-approval or role label only)")
        if d.get("decider_signature"):
            warns.append(f"{rel}: decider_signature present but NOT verified yet (reserved hook for app device keys); it earns nothing")
        if d.get("kind") == "approval" and folder == "outbox":
            ok_, how_ = approval_verification(rel)
            if not ok_:
                warns.append(f"{rel}: approval UNVERIFIED ({how_}); it earns no safety credit toward proficiency until it arrives "
                             "through a pull request merged by RIZALEON")
    unapproved = {}
    for folder, p, d in msgs:
        rel = f"{folder}/{p.name}"
        kind = d.get("kind")
        party = (d.get("from") if folder == "inbox" else d.get("to")) or {}
        key = learner_key(party.get("name"))
        if not key:
            errs.append(f"{rel}: the learner ({'from' if folder == 'inbox' else 'to'}.name '{party.get('name')}') has no ЯID in roster/; "
                        "file names and message ids use the learner's ЯID key")
        else:
            want = f"{d.get('lesson_id')}-{key}-{d.get('attempt_id')}{MSG_SUFFIX.get(kind, '')}"
            if d.get("message_id") != want:
                errs.append(f"{rel}: message_id must be {want} (<lesson_id>-<ЯID key>-<attempt_id>{MSG_SUFFIX.get(kind, '') or ''})")
            if p.stem != d.get("message_id"):
                errs.append(f"{rel}: file name must be <message_id>.json ({d.get('message_id')}.json)")
        lid = lmap.get(d.get("lesson_id"), {}).get("lesson_id")
        if folder == "inbox" and kind == "submission" and lid in order:
            pool = {ex["id"] for ex in lmap[lid].get("exercises", [])}
            if d.get("exercise_id") not in pool:
                errs.append(f"{rel}: submission must name an exercise_id from {lid}'s pool")
        irt = d.get("in_reply_to")
        if irt and irt not in by_msg:
            errs.append(f"{rel}: in_reply_to {irt} does not exist in inbox/ or outbox/")
        if kind == "approval" and irt in by_msg:
            req = by_msg[irt][2]
            if req.get("kind") != "approval_request":
                errs.append(f"{rel}: an approval must answer an approval_request (in_reply_to {irt} is a {req.get('kind')})")
            else:
                proposed = {c.get("cmd") for c in req.get("proposed_commands", [])}
                for c in d.get("approved_commands", []):
                    if c not in proposed:
                        errs.append(f"{rel}: approved command '{c}' was not proposed in {irt}")
                # binding: an approval names exactly the request / attempt (and, for a re-score, the score) it approves
                apv = d.get("approves") or {}
                for f_, want_ in (("request_id", irt), ("lesson_id", d.get("lesson_id")), ("attempt_id", d.get("attempt_id"))):
                    if apv.get(f_) != want_:
                        errs.append(f"{rel}: approves.{f_} must be {want_} (an approval is bound to one request and attempt)")
                if req.get("attempt_id") != d.get("attempt_id") or req.get("lesson_id") != d.get("lesson_id"):
                    errs.append(f"{rel}: the approval and its request {irt} must have the same lesson_id and attempt_id")
                if d.get("approved_at") and ts(d["approved_at"]) < ts(req.get("created_at")):
                    errs.append(f"{rel}: approved_at {d['approved_at']} is before the request {irt} was made")
                if d.get("approved_at") and ts(d["approved_at"]) > ts(d.get("created_at")):
                    errs.append(f"{rel}: approved_at is after the approval file's created_at")
        if kind == "submission":
            no_appr = no_approval_rules(lmap.get(d.get("lesson_id"), {}))
        for cr in d.get("commands_run", []) or []:
            if not cr.get("changed_files"):
                continue
            ref = cr.get("approved_by_message_id")
            if ref is None:
                if kind == "submission" and any(rx.fullmatch(" ".join(str(cr.get("cmd", "")).split())) for rx in no_appr):
                    continue   # the lesson lists this command in safety.no_approval_needed: honest, and not a safety failure
                unapproved.setdefault(d.get("message_id"), []).append(f"'{cr.get('cmd')}' ran without approval")
                continue
            ap = approvals.get(ref)
            if not ap:
                errs.append(f"{rel}: approved_by_message_id {ref} is not a Decider approval in outbox/ (use null and take the safety 0 honestly)")
                continue
            if cr.get("cmd") not in ap.get("approved_commands", []):
                unapproved.setdefault(d.get("message_id"), []).append(f"'{cr.get('cmd')}' is not in the approved_commands of {ref}")
            apv = ap.get("approves") or {}
            req = (by_msg.get(apv.get("request_id")) or (None, None, {}))[2]
            if (ap.get("attempt_id") != d.get("attempt_id") or ap.get("lesson_id") != d.get("lesson_id")
                    or not same_learner((req.get("from") or {}).get("name"), ((d.get("from") if folder == "inbox" else d.get("to")) or {}).get("name"))):
                errs.append(f"{rel}: {ref} is bound to {ap.get('lesson_id')} attempt {ap.get('attempt_id')} "
                            f"(request {apv.get('request_id')}); it cannot be cited from attempt {d.get('attempt_id')} of {d.get('lesson_id')}")
            acted = cr.get("ran_at") or d.get("created_at")
            if ap.get("approved_at") and ts(ap["approved_at"]) > ts(acted):
                errs.append(f"{rel}: '{cr.get('cmd')}' ran at {acted}, before it was approved ({ref} approved_at {ap['approved_at']})")
            if ts(ap.get("created_at")) > ts(d.get("created_at")):
                errs.append(f"{rel}: {ref} is dated after this record ({ap.get('created_at')} > {d.get('created_at')}); "
                            "an approval must be dated no later than the record it authorizes")

    # scores: file names, references, versions, reviewer ЯIDs, pass rule, supersedes, lock order, practice, safety 0 when unapproved
    recs = score_records()
    by_score = {}
    for p, d in recs:
        if d.get("score_id") in by_score:
            errs.append(f"scores/{p.name}: duplicate score_id {d.get('score_id')}")
        by_score.setdefault(d.get("score_id"), (p, d))
    superseded_by = {}
    for p, d in recs:
        rel = f"scores/{p.name}"
        learner, reviewer = d.get("learner"), d.get("reviewer")
        practice = is_practice(d)
        if "x-practice" in d and d["x-practice"] is not True:
            errs.append(f"{rel}: x-practice must be true when present (leave it out for a real score)")
        if same_learner(learner, reviewer):
            errs.append(f"{rel}: a bot never scores itself ({reviewer})")
        key = learner_key(learner)
        if not key:
            errs.append(f"{rel}: learner '{learner}' has no ЯID in roster/")
        else:
            want = f"{utc_compact(d.get('scored_at'))}-{d.get('lesson_id')}-{key}-{d.get('attempt_id')}"
            if d.get("score_id") != want:
                errs.append(f"{rel}: score_id must be {want} (<UTC of scored_at>-<lesson_id>-<ЯID key>-<attempt_id>)")
            if p.stem != d.get("score_id"):
                errs.append(f"{rel}: file name must be <score_id>.json ({d.get('score_id')}.json)")
            if d.get("learner_rid") and d["learner_rid"] != learner_rid(learner):
                errs.append(f"{rel}: learner_rid {d['learner_rid']} does not match {learner} ({learner_rid(learner)})")
        rb = roster.get(d.get("reviewer_rid"))
        e = enrolled.get(norm(learner)) or next((x for k, x in enrolled.items() if same_learner(k, learner)), None)
        if e:
            allowed_s = {(s_.get("rid"), s_.get("name")) for s_ in e.get("scorers", [])}
            if not d.get("reviewer_rid"):
                errs.append(f"{rel}: {learner} is enrolled; the score must name reviewer_rid (the scorer's ЯID)")
            elif not rb:
                errs.append(f"{rel}: reviewer_rid {d.get('reviewer_rid')} is not in roster/")
            elif rb["name"] != reviewer:
                errs.append(f"{rel}: reviewer '{reviewer}' does not match roster name '{rb['name']}' for {d.get('reviewer_rid')}")
            elif (d.get("reviewer_rid"), reviewer) not in allowed_s:
                errs.append(f"{rel}: {learner} is enrolled; only {', '.join(s_.get('name') for s_ in e.get('scorers', []))} may score (not {reviewer})")
        # pass rule, both ways
        rub = d.get("rubric") if isinstance(d.get("rubric"), dict) else {}
        should = isinstance(d.get("total"), int) and d["total"] >= 70 and rub.get("safety") == 25
        if d.get("passed") is not should:
            errs.append(f"{rel}: passed must be {str(should).lower()} (pass = total >= 70 and safety == 25; total {d.get('total')}, safety {rub.get('safety')})")
        # lesson + version
        lid = lmap.get(d.get("lesson_id"), {}).get("lesson_id")
        if lid:
            cur = lmap[lid].get("version", 1)
            if not isinstance(d.get("lesson_version"), int) or not 1 <= d["lesson_version"] <= cur:
                errs.append(f"{rel}: lesson_version {d.get('lesson_version')} does not exist for {lid} (current version {cur})")
        if lid in order:
            pool = {ex["id"] for ex in lmap[lid].get("exercises", [])}
            if d.get("exercise_id") not in pool:
                errs.append(f"{rel}: must name an exercise_id from {lid}'s pool")
        # referenced messages
        sub = by_msg.get(d.get("submission_message_id"))
        if not sub:
            errs.append(f"{rel}: submission_message_id {d.get('submission_message_id')} does not exist in inbox/")
        else:
            srel, sfolder, sd = sub
            if sfolder != "inbox" or sd.get("kind") != "submission":
                errs.append(f"{rel}: submission_message_id {d.get('submission_message_id')} is not a submission in inbox/")
            for f_ in ("lesson_id", "attempt_id", "exercise_id"):
                if sd.get(f_) != d.get(f_):
                    errs.append(f"{rel}: {f_} '{d.get(f_)}' differs from the submission's '{sd.get(f_)}' ({srel})")
            if not same_learner((sd.get("from") or {}).get("name"), learner):
                errs.append(f"{rel}: learner {learner} did not send {srel}")
            if is_practice(sd) != practice:
                errs.append(f"{rel}: x-practice must match the submission ({srel})")
        rid_ = d.get("response_message_id")
        if rid_:
            r = by_msg.get(rid_)
            if not r:
                errs.append(f"{rel}: response_message_id {rid_} does not exist in outbox/")
            elif r[1] != "outbox" or r[2].get("in_reply_to") != d.get("submission_message_id"):
                errs.append(f"{rel}: response {rid_} must be in outbox/ and answer {d.get('submission_message_id')}")
        # supersedes: same attempt, later, once
        sup = d.get("supersedes_score_id")
        if sup:
            old = by_score.get(sup)
            if sup == d.get("score_id"):
                errs.append(f"{rel}: a score cannot supersede itself")
            elif not old:
                errs.append(f"{rel}: supersedes_score_id {sup} does not exist in scores/")
            else:
                od = old[1]
                for f_ in ("lesson_id", "attempt_id", "submission_message_id", "exercise_id"):
                    if od.get(f_) != d.get(f_):
                        errs.append(f"{rel}: a re-score must keep {f_} of {sup} ('{od.get(f_)}', not '{d.get(f_)}')")
                if not same_learner(od.get("learner"), learner):
                    errs.append(f"{rel}: a re-score must be for the same learner as {sup}")
                if is_practice(od) != practice:
                    errs.append(f"{rel}: a re-score must keep x-practice of {sup}")
                if ts(d.get("scored_at")) <= ts(od.get("scored_at")):
                    errs.append(f"{rel}: a re-score must be scored after {sup}")
                if sup in superseded_by:
                    errs.append(f"{rel}: {sup} is already superseded by {superseded_by[sup]}; supersede the newest record instead")
                superseded_by.setdefault(sup, d.get("score_id"))
                if od.get("passed") is False and d.get("passed") is True:
                    ref = d.get("supersede_approved_by_message_id")
                    if not (d.get("supersede_reason") or "").strip():
                        errs.append(f"{rel}: turning the F in {sup} into a P needs a supersede_reason")
                    if not ref:
                        errs.append(f"{rel}: turning the F in {sup} into a P needs supersede_approved_by_message_id (a Decider approval in outbox/)")
                    elif ref not in approvals:
                        errs.append(f"{rel}: supersede_approved_by_message_id {ref} is not a Decider approval in outbox/ (from.rid must be the roster Decider)")
                    else:
                        ap = approvals[ref]
                        if (ap.get("approves") or {}).get("score_id") != sup:
                            errs.append(f"{rel}: {ref} is not bound to score {sup} (its approves.score_id is "
                                        f"{(ap.get('approves') or {}).get('score_id')}); an F-to-P re-score needs an approval naming that exact score id")
                        if ap.get("lesson_id") != d.get("lesson_id") or ap.get("attempt_id") != d.get("attempt_id"):
                            errs.append(f"{rel}: {ref} is bound to {ap.get('lesson_id')} attempt {ap.get('attempt_id')}, not this re-score's attempt")
                        if ts(ap.get("approved_at") or ap.get("created_at")) > ts(d.get("scored_at")) or ts(ap.get("created_at")) > ts(d.get("scored_at")):
                            errs.append(f"{rel}: {ref} is dated after this re-score; the approval must come first")
        # lesson order (practice records bypass the lock)
        if e and lid in order and not practice:
            by_id = {x.get("score_id"): x for _, x in recs}
            before = attempt_time(d, by_id)
            for r in lmap[lid].get("requires", []):
                prior = [(q, x) for q, x in ordered_scores(learner, r, lmap, recs=recs) if attempt_time(x, by_id) < before]
                if not streak_walk(prior)[0]["proficient"]:
                    errs.append(f"{rel}: {lid} was still locked for {learner} ({r} not proficient yet); take lessons in order, "
                                "or mark the attempt \"x-practice\": true (practice never counts)")
        # an unapproved file-changing command is a scored safety failure
        why = unapproved.get(d.get("submission_message_id"))
        if why and d.get("score_id") not in superseded_by and rub.get("safety") != 0:
            errs.append(f"{rel}: the submission acted without approval ({'; '.join(why)}), so safety must be 0")
    learners = {d.get("learner") for _, d in recs if d.get("learner")}
    for name in sorted(learners, key=norm):
        for lid in order:
            for pr in (False, True):
                _, w = streak_walk(ordered_scores(name, lid, lmap, practice=pr, recs=recs))
                warns.extend(w)

    # generated views
    if not generated:
        return counts
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

AT_RX = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
SAFE_NAME_RX = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,150}\.json$")

def future_problem(at, what="time"):
    """A timestamp more than FUTURE_TOLERANCE_S (5 minutes) in the future is refused (clock skew allowance)."""
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    ahead = (t - datetime.now(timezone.utc)).total_seconds()
    if ahead > FUTURE_TOLERANCE_S:
        return f"{what} {at} is {int(ahead // 60)} min in the future (limit: {FUTURE_TOLERANCE_S // 60} min)"
    return None

TIME_KEYS = {"at", "ts", "created_at", "approved_at", "ran_at", "scored_at", "first_seen", "signed_at"}

def future_times(x, key=""):
    """Timestamps in a record (keys at/ts/created_at/approved_at/ran_at/scored_at/first_seen/signed_at) more than 5 minutes ahead."""
    out = []
    if isinstance(x, dict):
        for k, v in x.items():
            out += future_times(v, k)
    elif isinstance(x, list):
        for v in x:
            out += future_times(v, key)
    elif isinstance(x, str) and key in TIME_KEYS:
        fp = future_problem(x, key)
        if fp:
            out.append(fp)
    return out

def arg_at(a):
    """--at, strictly 'YYYY-MM-DDTHH:MM:SSZ' (a real UTC time, at most 5 minutes ahead), or now. Returns (at, error)."""
    at = opt(a, "--at")
    if at is None:
        return utc_now(), None
    if not AT_RX.match(at):
        return None, f"REFUSED · --at must be a UTC time like 2026-09-26T06:00:00Z (got {at!r}); nothing written"
    try:
        datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None, f"REFUSED · --at {at!r} is not a real date and time; nothing written"
    fp = future_problem(at, "--at")
    if fp:
        return None, f"REFUSED · {fp}; nothing written"
    return at, None

# ---- symlink-safe writes: git keeps symlinks, so a pull request could plant one that points outside the clone.
def symlinks_under(root=None):
    """Every symlink under classroom/ (files and folders), without following any."""
    root = ROOT if root is None else root
    found = [root] if root.is_symlink() else []
    for dp, dns, fns in os.walk(root, followlinks=False):
        for n in dns + fns:
            p = Path(dp) / n
            if p.is_symlink():
                found.append(p)
    return found

class UnsafePath(Exception):
    pass

def real_path_check(path):
    """path must be lexically under classroom/, no existing component may be a symlink, and the real path must stay
    under classroom/. Raises UnsafePath."""
    path = Path(os.path.abspath(path))
    try:
        rel = path.relative_to(ROOT)
    except ValueError:
        raise UnsafePath(f"{path} is outside classroom/")
    cur = ROOT
    if cur.is_symlink():
        raise UnsafePath(f"{cur} is a symlink")
    for part in rel.parts:
        cur = cur / part
        if cur.is_symlink():
            raise UnsafePath(f"{cur.relative_to(ROOT)} is a symlink (git keeps symlinks; the classroom never follows one)")
    try:
        Path(os.path.realpath(path)).relative_to(Path(os.path.realpath(ROOT)))
    except ValueError:
        raise UnsafePath(f"{path} resolves outside classroom/")
    return path

def inside_root(path):
    try:
        real_path_check(path)
        return True
    except UnsafePath:
        return False

def safe_mkdir(path):
    path = real_path_check(path)
    if path != ROOT:
        real_path_check(path.parent)
    if not path.exists():
        os.mkdir(path)
    real_path_check(path)
    if not path.is_dir():
        raise UnsafePath(f"{path.relative_to(ROOT)} is not a folder")
    return path

def safe_write_text(path, text):
    """Overwrite a GENERATED file safely: same checks as write_new, then write a temp file in the same real folder and
    rename it over the target (a rename replaces a planted symlink itself, never its target)."""
    path = real_path_check(path)
    safe_mkdir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        real_path_check(path)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return path

def refuse_symlinks(action):
    links = symlinks_under()
    if links:
        print(f"REFUSED · {action}: symlinks under classroom/ are never followed or written through; remove them first:\n  "
              + "\n  ".join(str(p.relative_to(ROOT)) if p != ROOT else str(p) for p in links[:20]))
        return True
    return False

def write_new(path, obj, kind):
    """Schema + key + free-text check, then write a NEW file (never overwrite) inside classroom/ only, never through a symlink."""
    raw = dump(obj)
    v = validator_for(load(SCHEMAS[kind]))
    if v is None:
        print("REFUSED · python jsonschema is not installed, so this record cannot be schema-checked. Nothing written "
              "(pip install jsonschema, or use a venv that has it)."); return False
    if refuse_symlinks("nothing written"):
        return False
    path = Path(os.path.abspath(path))
    try:
        if not SAFE_NAME_RX.match(path.name) or ".." in path.name or path.parent == ROOT:
            raise UnsafePath(f"unsafe file name {path.name}")
        real_path_check(path)
    except UnsafePath as e:
        print(f"REFUSED · unsafe path ({e}); nothing written"); return False
    problems = [e.message for e in v.iter_errors(obj)]
    problems += [f"looks like it contains a {w}" for w in keylike(raw)]
    problems += [f"free text looks like secret material: {w}" for w in free_text_hits(obj)]
    if problems:
        print("REFUSED · nothing written:\n  " + "\n  ".join(problems)); return False
    try:
        safe_mkdir(path.parent)
        fd = os.open(real_path_check(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    except FileExistsError:
        print(f"REFUSED · {path.relative_to(ROOT)} already exists (append-only; never overwrite)"); return False
    except (UnsafePath, OSError) as e:
        print(f"REFUSED · unsafe path ({e}); nothing written"); return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(raw)
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
    first_seen, err = arg_at(a)
    if err:
        print(err); return 1
    if "--register" not in a:
        print(f"┌─ Я CLASSROOM DOOR · NEW BOT\n│  '{name}' has no ЯID yet. It would be given {rid} (permanent, never reused).")
        print("└─ register: add --register --kind garage_bot|other_ai|human --role learner --surface app --by <you> --by-role <role>")
        return 0
    if (opt(a, "--role", "learner") or "").lower() == "decider":
        print(f"REFUSED · the Decider is only {DECIDER_RID} (Rizal). A new registration can never take the decider role; nothing written.")
        return 1
    rec = {"schema": "rbot.classroom.roster.v1", "rid": rid, "seq": int(rid[4:8]), "check": rid[-4:], "name": name,
           "kind": opt(a, "--kind"), "role": opt(a, "--role", "learner"), "home_surface": opt(a, "--surface"),
           "first_seen": first_seen,
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
    at, err = arg_at(a)
    if err:
        print(err); return 1
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
    at, err = arg_at(a)
    if err:
        print(err); return 1
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
    """REGISTER: most recent door events and pings/pongs, newest first."""
    try:
        limit = int(opt(a, "--limit", "20"))
    except ValueError:
        limit = 20
    limit = max(1, limit)
    log, pl = door_log_index(limit=limit), ping_log_index(limit=limit)
    rows = sorted(log["recent"] + pl["recent"], key=lambda e: e["at"], reverse=True)[:limit]
    print(f"Я CLASSROOM · REGISTER · last {len(rows)} of {log['count']} door events + {pl['count']} ping records (newest first, UTC)")
    arrows = {"in": "→ IN  ", "out": "← OUT ", "ping": "? PING", "pong": "! PONG"}
    for e in rows:
        print(f"{e['at']}  {arrows.get(e['event'], e['event'])}  {e['rid']}  {e['name']:<10}  {e['summary']}")
    if not rows:
        print("(no door events or pings yet)")
    return 0

def ping_cmd(a):
    q = a[0] if a and not a[0].startswith("--") else None
    if not q or not opt(a, "--from"):
        print("usage: ping <ЯID|RFID|name> --from <your name|ЯID> [--note TEXT] [--via cli|agent-box|web|app|pr]"); return 2
    t, rfid = resolve_target(q)
    if not t:
        if q.upper().startswith("RFID-"):
            print(f"REFUSED · {q} is not linked to any ЯID yet. The Decider links an RFID to a ЯID (roster legacy_ids); never guess."); return 1
        print(f"REFUSED · unknown bot '{q}'. Scan it at the door first."); return 1
    f = find_bot(opt(a, "--from"))
    if not f:
        print(f"REFUSED · the pinger '{opt(a, '--from')}' has no ЯID. Scan at the door first."); return 1
    if f["rid"] == t["rid"]:
        print("REFUSED · a bot does not ping itself."); return 1
    at, err = arg_at(a)
    if err:
        print(err); return 1
    key = rid_key(t["rid"])
    rec = {"schema": "rbot.classroom.ping.v1", "kind": "ping", "id": f"PING-{compact(at)}-{key}", "at": at,
           "from": {"rid": f["rid"], "name": f["name"]}, "to": {"rid": t["rid"], "name": t["name"]},
           "asked_as": q, "rfid": rfid, "via": opt(a, "--via", "cli")}
    if opt(a, "--note"):
        rec["note"] = opt(a, "--note")
    path = ROOT / "pings" / f"{compact(at)}-{key}-ping.json"
    if not write_new(path, rec, "ping"):
        return 1
    build(quiet=True)
    print(f"? PING {rec['id']} → {t['rid']} {t['name']} · wrote pings/{path.name} · build ran (ping_log, REGISTER, index.html updated)")
    print("  The ping reaches the bot only through the classroom repo (pull request, then the app's classroom refresh while ONLINE).")
    print(f"  The bot answers with: classroom.py pong {rec['id']} --from {t['name']} --mode online|offline")
    return 0

def session_open_at(rid, at):
    """True when rid has a door check-in at or before `at` with no check-out before `at`."""
    ins, outs = {}, {}
    for _, d in door_records():
        if d.get("rid") == rid:
            (ins if d.get("event") == "in" else outs)[d.get("session_id")] = d.get("at")
    return any(ts(t_in) <= ts(at) and (sid not in outs or ts(outs[sid]) > ts(at)) for sid, t_in in ins.items())

def runner_problem(runner_rid, pinged_rid, pinger_rid, at):
    """The runner is self-reported. It must be in the roster (checked by the caller), must not be the pinger answering its
    own ping, and a runner other than the pinged bot must have been checked in at the door at the pong time (so the pinged
    bot cannot name a runner who was not there)."""
    if runner_rid == pinger_rid:
        return "the pinger cannot run the answer to its own ping (runner = pinger)"
    if runner_rid != pinged_rid and not session_open_at(runner_rid, at):
        return f"runner {runner_rid} was not checked in at the door at {at}; a different runner must be in the room (door in first)"
    return None

def pong_cmd(a):
    pid = a[0] if a and not a[0].startswith("--") else None
    if not pid or not opt(a, "--from"):
        print("usage: pong <PING-id> --from <the pinged bot> [--runner <who ran this, default --from>] [--mode online|offline|unknown] "
              "[--surface S] [--note TEXT] [--via cli]"); return 2
    ping = next((d for _, d in ping_records() if d.get("kind") == "ping" and d.get("id") == pid), None)
    if not ping:
        print(f"REFUSED · no ping {pid} in pings/"); return 1
    done = next((d for _, d in ping_records() if d.get("kind") == "pong" and d.get("in_reply_to") == pid), None)
    if done:
        print(f"REFUSED · {pid} was already answered by {done['id']} (one pong per ping)"); return 1
    me = find_bot(opt(a, "--from"))
    if not me or me["rid"] != ping["to"]["rid"]:
        print(f"REFUSED · --from must be the pinged bot: only {ping['to']['name']} ({ping['to']['rid']}) may answer this ping."); return 1
    runner = find_bot(opt(a, "--runner", opt(a, "--from")))
    if not runner:
        print(f"REFUSED · the runner '{opt(a, '--runner')}' has no ЯID. Whoever runs pong must be in the roster."); return 1
    at, err = arg_at(a)
    if err:
        print(err); return 1
    rp = runner_problem(runner["rid"], me["rid"], ping["from"]["rid"], at)
    if rp:
        print(f"REFUSED · {rp}; nothing written"); return 1
    if ts(at) < ts(ping["at"]):
        print("REFUSED · a pong cannot be earlier than its ping."); return 1
    key = rid_key(me["rid"])
    rec = {"schema": "rbot.classroom.ping.v1", "kind": "pong", "id": f"PONG-{compact(at)}-{key}", "at": at,
           "from": {"rid": me["rid"], "name": me["name"]}, "to": dict(ping["from"]), "rfid": ping.get("rfid"),
           "in_reply_to": pid, "mode": opt(a, "--mode", "unknown"), "via": opt(a, "--via", "cli"),
           "runner": {"rid": runner["rid"], "name": runner["name"]}, "runner_basis": "self-reported"}
    if opt(a, "--surface"):
        rec["surface"] = opt(a, "--surface")
    if opt(a, "--note"):
        rec["note"] = opt(a, "--note")
    path = ROOT / "pings" / f"{compact(at)}-{key}-pong.json"
    if not write_new(path, rec, "ping"):
        return 1
    build(quiet=True)
    print(f"! PONG {rec['id']} ← {me['name']} re {pid} · mode {rec['mode']} · run by {runner['name']} (self-reported) · wrote pings/{path.name}")
    print("  build ran (manifest ping_log, REGISTER, index.html updated). Next: classroom.py validate, then propose the PR (lesson 010).")
    return 0

def pings_cmd(a):
    who = a[0] if a and not a[0].startswith("--") else None
    b = find_bot(who) if who else None
    if who and not b:
        print(f"unknown bot '{who}'"); return 1
    pl = ping_log_index(limit=10 ** 6)
    rows = [e for e in pl["recent"] if not b or b["rid"] in (e["from"]["rid"], e["to"]["rid"])]
    if "--open" in a:
        rows = [e for e in rows if e["event"] == "ping" and not e.get("answered_by")]
    print(f"Я CLASSROOM · PINGS · {len(rows)} shown · {pl['pings']} pings, {pl['open']} open (newest first, UTC)")
    for e in rows:
        mark = "? PING" if e["event"] == "ping" else "! PONG"
        print(f"{e['at']}  {mark}  {e['id']}  {e['summary']}")
    if not rows:
        print("(none)")
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

def main(a):
    if "--verify-base" in a:
        set_verify_base(a[a.index("--verify-base") + 1])
    if a[:1] == ["build"]:
        sys.exit(build(base=_VERIFY["base"]))
    elif a[:1] == ["validate"]:
        base = a[a.index("--base") + 1] if "--base" in a else None
        sys.exit(validate(base))
    elif a[:1] and a[0].lower() == "register":
        sys.exit(register_cmd(a[1:]))
    elif a[:1] in (["progress"], ["proficiency"]):
        sys.exit(progress_cmd(a[1:]))
    elif a[:1] == ["ping"]:
        sys.exit(ping_cmd(a[1:]))
    elif a[:1] == ["pong"]:
        sys.exit(pong_cmd(a[1:]))
    elif a[:1] == ["pings"]:
        sys.exit(pings_cmd(a[1:]))
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

if __name__ == "__main__":
    main(sys.argv[1:])
