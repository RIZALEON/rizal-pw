#!/usr/bin/env python3
"""ЯBOT Classroom helper (stdlib; uses `jsonschema` if installed).

  python3 classroom/tools/classroom.py build      # regenerate manifest.json lesson list + index.html lesson table
  python3 classroom/tools/classroom.py validate   # check every JSON file in the classroom
  python3 classroom/tools/classroom.py validate --base origin/main   # also enforce append-only vs a git ref

Read-only except `build`, which rewrites manifest.json and index.html inside classroom/ only.
No network, no secrets, no git writes.
"""
import hashlib, html, json, re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # classroom/
SCHEMAS = {k: ROOT / "state" / f"{k}.schema.json" for k in ("lesson", "message", "score")}
APPEND_ONLY = ("inbox/", "outbox/", "scores/")
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "PEM private key"),
    (re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{85,90}\b"), "base58 string the length of a Solana secret key"),
    (re.compile(r"\[\s*(?:\d{1,3}\s*,\s*){63}\d{1,3}\s*\]"), "64-byte array (keypair file shape)"),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{32,})\b"), "API token"),
    (re.compile(r"(?i)\b(seed phrase|mnemonic|private key)\s*[:=]"), "secret label with a value"),
]

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

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

def build():
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
    man_p.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
    idx.write_text(text, encoding="utf-8")
    print(f"built manifest.json + index.html with {len(entries)} lessons")

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
        check(p, "message" if "message" in p.name else "score")
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
    for extra in ("manifest.json",):
        man = check(ROOT / extra, None)
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
    print(f"{'OK' if not errs else 'FAILED'}: {n} JSON files checked, {len(errs)} problems")
    return 1 if errs else 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        build()
    elif a[:1] == ["validate"]:
        base = a[a.index("--base") + 1] if "--base" in a else None
        sys.exit(validate(base))
    else:
        print(__doc__)
