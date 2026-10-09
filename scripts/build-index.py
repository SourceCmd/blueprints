#!/usr/bin/env python3
"""Validate every blueprint and build the catalog's index.json.

The index is the one file a keep verifies (one Ed25519 signature over its
exact bytes) before it stores anything from this catalog. It names every
blueprint, its kind, format and version, a summary for browsing, and the
sha256 of its file, so the signature covers every version number and every
byte: a rollback or a tampered file is detectable.

This script is the catalog's lint and build in one. It applies:

  * the format (SCHEMA.md): kind and format first, then strict fields, so an
    unknown field (a declared risk, a rule, a path, an owner's note) fails
    the build by name;
  * the catalog's rules (README.md, "Curation"): the id's author namespace
    and the file's place in the tree; a persona's "Who you are, and aren't"
    guardrails and "inspired by" summary; a character's "Who you are"; no
    personal data (emails, phone numbers, IP addresses, home-folder paths,
    secrets).

Keeps parse every file again with their own parser before storing it, and
the publish step runs that same parser over this build's output, so the two
can't silently disagree: a file that passes here and fails there stops the
publish.

Deterministic: sorted keys, no timestamp, LF endings, trailing newline.

Usage:
    scripts/build-index.py <catalog_version> [output_path]
    scripts/build-index.py --check            # lint only, no output
"""

import hashlib
import json
import os
import re
import sys

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml (or apt install python3-yaml)")

INDEX_SCHEMA = 1
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLUEPRINTS_DIR = os.path.join(REPO_ROOT, "blueprints")
FILE_NAME = "blueprint.yaml"
MAX_BYTES = 64 << 10

FORMATS = {"agent": [1]}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}/[a-z0-9][a-z0-9-]{0,63}$")
SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
CATALOG_VERSION_RE = re.compile(r"^[0-9]{1,9}(\.[0-9]{1,9}){0,4}$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
HARNESS_RE = TAG_RE
MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")
SLUG_RE = re.compile(r"^[a-z0-9_][a-z0-9_-]*/[a-z0-9_][a-z0-9_-]*$")
TOOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")
CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
ACTION_RE = re.compile(r"^[a-z0-9_]{1,64}$")

# The agent kind, format 1: every field there is (SCHEMA.md). Anything else
# is refused.
TOP = {"kind", "format", "id", "version", "display_name", "summary", "tags",
       "author", "apps", "min_keep_version", "agent", "personal_hints",
       "runs_on", "skills", "asks", "needs"}
AGENT = {"name", "persona", "job", "instructions"}
RUNS_ON = {"harnesses", "model", "prefer_models"}
SKILL = {"skill", "version"}
ASKS = {"tools", "network", "own_folder", "folders", "manage"}
# Management asks (added to format 1, 2026-10-09): rights over the owner's
# agents, by the keep's entity action. Never pre-ticked at review.
MANAGE = {"action", "why"}
MANAGE_ACTIONS = ["agent.create", "agent.update", "agent.add_to_chat", "agent.sleep", "agent.wake", "agent.retire"]
TOOL = {"tool", "pattern", "why"}
NETWORK = {"open", "host", "category", "why"}
OWN_FOLDER = {"access", "why"}
FOLDER = {"access", "label", "why"}
NEEDS = {"plugins"}
PLUGIN = {"plugin", "actions", "why", "optional"}

PERSONA_SECTION = "Who you are, and aren't"
CHARACTER_SECTION = "Who you are"
PERSONA_GUARDRAILS = [("ai persona", "that it's an AI persona"),
                      ("never claim", "that it never claims to be the person"),
                      ("invent quotes", "that it never invents quotes"),
                      ("endorse", "that it never implies the person's endorsement")]
CHARACTER_GUARDRAILS = [("ai character", "that it's an AI character"),
                        ("never claim", "that it never claims to be a real person")]
PERSONAL_DATA = [
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"), "an email address"),
    (re.compile(r"(^|[^\d.])\d{1,3}(\.\d{1,3}){3}($|[^\d.]|\.($|[^\d]))"), "an IP address"),
    (re.compile(r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"), "a phone number"),
    (re.compile(r"\+\d{1,3}[ .-]?\(?\d{1,4}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}"), "a phone number"),
    (re.compile(r"(/home/|/Users/|~/|[A-Za-z]:\\)"), "a home-folder path"),
    (re.compile(r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{16,}|xox[bp]-|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY)"),
     "something like a secret"),
]


class Problems:
    def __init__(self, where):
        self.where = where
        self.items = []

    def add(self, msg):
        self.items.append(msg)


def check_keys(p, obj, allowed, where):
    if not isinstance(obj, dict):
        p.add("%s must be a mapping" % where)
        return {}
    for k in obj:
        if k not in allowed:
            p.add("unknown field %r in %s" % (k, where))
    return obj


def check_text(p, field, v, cap, required):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        if required:
            p.add("%s is required" % field)
        return
    if not isinstance(v, str):
        p.add("%s must be text" % field)
        return
    if len(v.encode()) > cap:
        p.add("%s is %d bytes; at most %d" % (field, len(v.encode()), cap))
    if any((ord(c) < 0x20 and c not in "\n\t") or ord(c) == 0x7F for c in v):
        p.add("%s holds a control character" % field)


def as_list(p, v, field):
    if v is None:
        return []
    if not isinstance(v, list):
        p.add("%s must be a list" % field)
        return []
    return v


def section(md, title):
    lines = md.split("\n")
    for i, line in enumerate(lines):
        lv, name = heading(line)
        if lv and name.lower() == title.lower():
            body = []
            for m in lines[i + 1:]:
                l2, _ = heading(m)
                if l2 and l2 <= lv:
                    break
                body.append(m)
            return "\n".join(body)
    return None


def heading(line):
    t = line.strip()
    n = len(t) - len(t.lstrip("#"))
    if n == 0 or n > 6 or n >= len(t) or t[n] != " ":
        return 0, ""
    return n, t[n:].strip()


def fold(s):
    return " ".join(s.lower().split())


def validate(doc, p):
    """The format: SCHEMA.md, agent format 1."""
    if not isinstance(doc, dict):
        p.add("not a YAML mapping")
        return None
    kind = doc.get("kind")
    if not kind:
        if "blueprint_schema" in doc or "items" in doc:
            p.add("made for Hearth's old blueprint format, which keeps don't read")
        else:
            p.add("no kind")
        return None
    if kind not in FORMATS:
        p.add("kind %r isn't one keeps read" % kind)
        return None
    fmt = doc.get("format")
    if not isinstance(fmt, int) or isinstance(fmt, bool) or fmt not in FORMATS[kind]:
        p.add("format %r isn't one keeps read for kind %s (%s)" % (fmt, kind, FORMATS[kind]))
        return None

    check_keys(p, doc, TOP, "the file")
    if not isinstance(doc.get("id"), str) or not ID_RE.match(doc["id"]):
        p.add("id must be <author namespace>/<slug>, lowercase (e.g. sourcecmd/researcher)")
    if not isinstance(doc.get("version"), str) or not SEMVER_RE.match(doc["version"]):
        p.add("version must be semver (1.0.0), quoted if YAML would read it as a number")
    check_text(p, "display_name", doc.get("display_name"), 60, True)
    check_text(p, "summary", doc.get("summary"), 300, True)
    check_text(p, "author", doc.get("author"), 60, True)
    tags = as_list(p, doc.get("tags"), "tags")
    if len(tags) > 12:
        p.add("at most 12 tags")
    for i, t in enumerate(tags):
        if not isinstance(t, str) or not TAG_RE.match(t):
            p.add("tags[%d] must be lowercase letters, digits and dashes" % i)
    if len(set(map(str, tags))) != len(tags):
        p.add("a tag is listed twice")
    apps = as_list(p, doc.get("apps"), "apps")
    if not apps:
        p.add("apps must name at least one of loop, hearth")
    for i, a in enumerate(apps):
        if a not in ("loop", "hearth"):
            p.add("apps[%d] must be loop or hearth" % i)
    if len(set(map(str, apps))) != len(apps):
        p.add("an app is listed twice")
    mkv = doc.get("min_keep_version")
    if mkv is not None and (not isinstance(mkv, str) or not SEMVER_RE.match(mkv)):
        p.add("min_keep_version must be semver (0.9.0)")

    agent = check_keys(p, doc.get("agent"), AGENT, "agent")
    check_text(p, "agent.name", agent.get("name"), 60, True)
    check_text(p, "agent.persona", agent.get("persona"), 4 << 10, False)
    check_text(p, "agent.job", agent.get("job"), 120, True)
    check_text(p, "agent.instructions", agent.get("instructions"), 32 << 10, True)

    hints = as_list(p, doc.get("personal_hints"), "personal_hints")
    if len(hints) > 10:
        p.add("at most 10 personal_hints")
    for i, h in enumerate(hints):
        check_text(p, "personal_hints[%d]" % i, h, 200, True)

    runs_on = check_keys(p, doc.get("runs_on") or {}, RUNS_ON, "runs_on")
    hs = as_list(p, runs_on.get("harnesses"), "runs_on.harnesses")
    for i, h in enumerate(hs):
        if not isinstance(h, str) or not HARNESS_RE.match(h):
            p.add("runs_on.harnesses[%d] must be a harness name (claude-code, codex)" % i)
    if runs_on.get("model") not in (None, "", "economical", "capable"):
        p.add("runs_on.model must be economical or capable")
    pm = runs_on.get("prefer_models") or {}
    if not isinstance(pm, dict):
        p.add("runs_on.prefer_models must be a mapping")
        pm = {}
    for h, models in pm.items():
        if not isinstance(h, str) or not HARNESS_RE.match(h):
            p.add("runs_on.prefer_models has a key that isn't a harness name")
        models = as_list(p, models, "runs_on.prefer_models.%s" % h)
        if not models:
            p.add("runs_on.prefer_models.%s must list at least one model" % h)
        for m in models:
            if not isinstance(m, str) or not MODEL_RE.match(m):
                p.add("runs_on.prefer_models.%s has a model that isn't a model name" % h)

    for i, s in enumerate(as_list(p, doc.get("skills"), "skills")):
        s = check_keys(p, s, SKILL, "skills[%d]" % i)
        if not isinstance(s.get("skill"), str) or not SLUG_RE.match(s["skill"]):
            p.add("skills[%d].skill must be a catalog slug (namespace/name)" % i)
        if not isinstance(s.get("version"), str) or not SEMVER_RE.match(s["version"]):
            p.add("skills[%d].version must be semver" % i)

    asks = check_keys(p, doc.get("asks") or {}, ASKS, "asks")
    for i, t in enumerate(as_list(p, asks.get("tools"), "asks.tools")):
        t = check_keys(p, t, TOOL, "asks.tools[%d]" % i)
        if not isinstance(t.get("tool"), str) or not TOOL_RE.match(t["tool"]):
            p.add("asks.tools[%d].tool must be a tool name (WebSearch, Bash)" % i)
        check_text(p, "asks.tools[%d].pattern" % i, t.get("pattern"), 80, False)
        check_text(p, "asks.tools[%d].why" % i, t.get("why"), 300, True)
    for i, n in enumerate(as_list(p, asks.get("network"), "asks.network")):
        n = check_keys(p, n, NETWORK, "asks.network[%d]" % i)
        named = [k for k in ("open", "host", "category") if n.get(k)]
        if len(named) != 1:
            p.add("asks.network[%d] must name exactly one of open, host, category" % i)
        if n.get("open") and n["open"] != "web":
            p.add("asks.network[%d].open must be web" % i)
        if n.get("host") and not (isinstance(n["host"], str) and HOST_RE.match(n["host"])):
            p.add("asks.network[%d].host must be a lowercase host name" % i)
        if n.get("category") and not (isinstance(n["category"], str) and CATEGORY_RE.match(n["category"])):
            p.add("asks.network[%d].category must be a category name" % i)
        check_text(p, "asks.network[%d].why" % i, n.get("why"), 300, True)
    if asks.get("own_folder") is not None:
        f = check_keys(p, asks["own_folder"], OWN_FOLDER, "asks.own_folder")
        if f.get("access") not in ("read", "read-write"):
            p.add("asks.own_folder.access must be read or read-write")
        check_text(p, "asks.own_folder.why", f.get("why"), 300, True)
    for i, f in enumerate(as_list(p, asks.get("folders"), "asks.folders")):
        f = check_keys(p, f, FOLDER, "asks.folders[%d]" % i)
        if f.get("access") not in ("read", "read-write"):
            p.add("asks.folders[%d].access must be read or read-write" % i)
        check_text(p, "asks.folders[%d].label" % i, f.get("label"), 80, True)
        if isinstance(f.get("label"), str) and re.search(r"[/\\~]", f["label"]):
            p.add("asks.folders[%d].label must be a label, never a path" % i)
        check_text(p, "asks.folders[%d].why" % i, f.get("why"), 300, True)

    seen_manage = set()
    for i, m in enumerate(as_list(p, asks.get("manage"), "asks.manage")):
        m = check_keys(p, m, MANAGE, "asks.manage[%d]" % i)
        if m.get("action") not in MANAGE_ACTIONS:
            p.add("asks.manage[%d].action must be one of %s" % (i, ", ".join(MANAGE_ACTIONS)))
        elif m["action"] in seen_manage:
            p.add("asks.manage action %s is listed twice" % m["action"])
        else:
            seen_manage.add(m["action"])
        check_text(p, "asks.manage[%d].why" % i, m.get("why"), 300, True)

    needs = check_keys(p, doc.get("needs") or {}, NEEDS, "needs")
    for i, pl in enumerate(as_list(p, needs.get("plugins"), "needs.plugins")):
        pl = check_keys(p, pl, PLUGIN, "needs.plugins[%d]" % i)
        if not isinstance(pl.get("plugin"), str) or not SLUG_RE.match(pl["plugin"]):
            p.add("needs.plugins[%d].plugin must be a catalog slug (namespace/name)" % i)
        for a in as_list(p, pl.get("actions"), "needs.plugins[%d].actions" % i):
            if not isinstance(a, str) or not ACTION_RE.match(a):
                p.add("needs.plugins[%d].actions must be action names" % i)
                break
        if pl.get("optional") is not None and not isinstance(pl["optional"], bool):
            p.add("needs.plugins[%d].optional must be true or false" % i)
        check_text(p, "needs.plugins[%d].why" % i, pl.get("why"), 300, True)
    return doc


def texts(doc):
    agent = doc.get("agent") or {}
    out = [("display_name", doc.get("display_name")), ("summary", doc.get("summary")),
           ("author", doc.get("author")), ("agent.name", agent.get("name")),
           ("agent.persona", agent.get("persona")), ("agent.job", agent.get("job")),
           ("agent.instructions", agent.get("instructions"))]
    out += [("personal_hints[%d]" % i, h) for i, h in enumerate(doc.get("personal_hints") or [])]
    asks = doc.get("asks") or {}
    for i, t in enumerate(asks.get("tools") or []):
        out += [("asks.tools[%d].pattern" % i, t.get("pattern")), ("asks.tools[%d].why" % i, t.get("why"))]
    for i, n in enumerate(asks.get("network") or []):
        out.append(("asks.network[%d].why" % i, n.get("why")))
    if asks.get("own_folder"):
        out.append(("asks.own_folder.why", asks["own_folder"].get("why")))
    for i, f in enumerate(asks.get("folders") or []):
        out += [("asks.folders[%d].label" % i, f.get("label")), ("asks.folders[%d].why" % i, f.get("why"))]
    for i, m in enumerate(asks.get("manage") or []):
        out.append(("asks.manage[%d].why" % i, m.get("why")))
    for i, pl in enumerate((doc.get("needs") or {}).get("plugins") or []):
        out.append(("needs.plugins[%d].why" % i, pl.get("why")))
    return [(k, v) for k, v in out if isinstance(v, str)]


def lint(doc, rel_path, p):
    """The catalog's rules (README.md, "Curation")."""
    want = "blueprints/%s/%s" % (doc.get("id"), FILE_NAME)
    if rel_path != want:
        p.add("id %s must live at %s" % (doc.get("id"), want))
    tags = doc.get("tags") or []
    instructions = (doc.get("agent") or {}).get("instructions") or ""
    persona, character = "persona" in tags, "character" in tags
    if persona and character:
        p.add("tagged both persona and character: a persona channels a real, public person; a character channels no one")
    elif persona:
        sec = section(instructions, PERSONA_SECTION)
        if sec is None:
            p.add("a persona blueprint needs a %r section in its instructions" % PERSONA_SECTION)
        else:
            for phrase, what in PERSONA_GUARDRAILS:
                if phrase not in fold(sec):
                    p.add("its %r section must say %s (%r)" % (PERSONA_SECTION, what, phrase))
        if "inspired by" not in (doc.get("summary") or "").lower():
            p.add('a persona\'s summary says "inspired by", so a listing never reads as the person\'s own')
    elif character:
        sec = section(instructions, CHARACTER_SECTION)
        if sec is None:
            p.add("a character blueprint needs a %r section in its instructions" % CHARACTER_SECTION)
        else:
            for phrase, what in CHARACTER_GUARDRAILS:
                if phrase not in fold(sec):
                    p.add("its %r section must say %s (%r)" % (CHARACTER_SECTION, what, phrase))
    for field, value in texts(doc):
        for rx, what in PERSONAL_DATA:
            if rx.search(value):
                p.add("%s holds what looks like %s; blueprints carry no personal data" % (field, what))


def ask_report(doc):
    out = []
    asks = doc.get("asks") or {}
    for t in asks.get("tools") or []:
        out.append("tool %s(%s)" % (t["tool"], t["pattern"]) if t.get("pattern") else "tool " + t["tool"])
    for n in asks.get("network") or []:
        out.append("the open web" if n.get("open") else ("host " + n["host"] if n.get("host") else "category " + n["category"]))
    if asks.get("own_folder"):
        out.append("its own folder, " + asks["own_folder"]["access"])
    for f in asks.get("folders") or []:
        out.append("a folder the owner picks (%s), %s" % (f["label"], f["access"]))
    for m in asks.get("manage") or []:
        out.append("manage: " + m["action"])
    for pl in (doc.get("needs") or {}).get("plugins") or []:
        out.append("plugin " + pl["plugin"] + (", optional" if pl.get("optional") else ""))
    return out


def discover():
    if not os.path.isdir(BLUEPRINTS_DIR):
        sys.exit("no blueprints/ directory at %s" % BLUEPRINTS_DIR)
    for ns in sorted(os.listdir(BLUEPRINTS_DIR)):
        ns_dir = os.path.join(BLUEPRINTS_DIR, ns)
        if not os.path.isdir(ns_dir):
            continue
        for slug in sorted(os.listdir(ns_dir)):
            d = os.path.join(ns_dir, slug)
            if not os.path.isdir(d):
                continue
            extra = sorted(set(os.listdir(d)) - {FILE_NAME})
            if extra:
                sys.exit("blueprints/%s/%s holds files other than %s: %s" % (ns, slug, FILE_NAME, ", ".join(extra)))
            yield "blueprints/%s/%s/%s" % (ns, slug, FILE_NAME), os.path.join(d, FILE_NAME)


def main():
    args = sys.argv[1:]
    check_only = args[:1] == ["--check"]
    if not check_only and not args:
        sys.exit(__doc__)
    catalog_version = None if check_only else args[0]
    if catalog_version is not None and not CATALOG_VERSION_RE.match(catalog_version):
        sys.exit("catalog_version must be dotted numbers, e.g. 2026.10.08 or 2026.10.08.1")
    out_path = None if check_only else (args[1] if len(args) > 1 else os.path.join(REPO_ROOT, "index.json"))

    entries, failed = {}, 0
    for rel, path in discover():
        p = Problems(rel)
        with open(path, "rb") as f:
            data = f.read()
        doc = None
        if len(data) > MAX_BYTES:
            p.add("%d bytes; at most %d" % (len(data), MAX_BYTES))
        else:
            try:
                docs = list(yaml.safe_load_all(data))
                if len(docs) != 1:
                    p.add("holds %d YAML documents; one only" % len(docs))
                else:
                    doc = validate(docs[0], p)
            except yaml.YAMLError as e:
                p.add("isn't valid YAML: %s" % str(e).splitlines()[0])
        if doc is not None and not p.items:
            lint(doc, rel, p)
        if p.items:
            failed += 1
            print("FAIL %s" % rel)
            for m in p.items:
                print("     " + m)
            continue
        print("ok   %s %s: %s" % (doc["id"], doc["version"], "; ".join(ask_report(doc)) or "asks for nothing"))
        if doc["id"] in entries:
            sys.exit("id %s appears twice" % doc["id"])
        entries[doc["id"]] = {
            "kind": doc["kind"],
            "format": doc["format"],
            "version": doc["version"],
            "display_name": doc["display_name"],
            "summary": doc["summary"],
            "tags": doc.get("tags") or [],
            "apps": doc["apps"],
            "files": {FILE_NAME: hashlib.sha256(data).hexdigest()},
        }
        if doc.get("min_keep_version"):
            entries[doc["id"]]["min_keep_version"] = doc["min_keep_version"]

    if failed:
        sys.exit("%d blueprint(s) failed" % failed)
    if not entries:
        sys.exit("no blueprints found under %s" % BLUEPRINTS_DIR)
    if check_only:
        print("%d blueprints pass" % len(entries))
        return

    index = {"schema": INDEX_SCHEMA, "catalog_version": catalog_version, "blueprints": entries}
    body = json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with open(out_path, "w", newline="\n", encoding="utf-8") as f:
        f.write(body)
    print("wrote %s (%d blueprints, catalog_version=%s)" % (out_path, len(entries), catalog_version))


if __name__ == "__main__":
    main()
