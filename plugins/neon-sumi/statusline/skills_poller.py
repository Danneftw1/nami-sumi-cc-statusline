#!/usr/bin/env python3
"""Neon Sumi skills collector: which skills fired in the last 7 days, for the cockpit.

Reads the session transcripts under the Claude config directory for three records:
a Skill tool call, a slash command that names an installed skill, and a hook
blocking record (a hook refused a stop). A week of transcripts can be a gigabyte,
so the per-file offsets live in skills-state.json and every pass after the first
reads only the bytes appended since. The cockpit starts this detached and reads
skills.json only.

    python3 skills_poller.py
"""
import fcntl
import glob
import json
import mmap
import os
import re
import time
from datetime import datetime

HOME = os.path.expanduser("~")
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")
CACHE = os.environ.get("NEON_SUMI_CACHE") or os.path.join(HOME, ".cache", "neon-sumi")
SUMMARY = os.path.join(CACHE, "skills.json")
STATE = os.path.join(CACHE, "skills-state.json")
WINDOW = 7 * 86400
NEEDLES = (b'"name":"Skill"', b'"hook_blocking_error"', b"<command-name>/")
RE_PR_URL = re.compile(r"https://github\.com/[^/\s]+/([^/\s]+)/(?:pull|issues)/(\d+)")


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json(path, data):
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)


def installed():
    """Every installed skill, plugin:name -> SKILL.md (your own skills have no prefix)."""
    found = {}
    plugins = read_json(os.path.join(CLAUDE_DIR, "plugins", "installed_plugins.json")).get("plugins") or {}
    for key, entries in plugins.items():
        for e in entries or []:
            for p in glob.glob(os.path.join(e.get("installPath") or "", "skills", "*", "SKILL.md")):
                found["%s:%s" % (key.split("@")[0], os.path.basename(os.path.dirname(p)))] = p
    for p in glob.glob(os.path.join(CLAUDE_DIR, "skills", "*", "SKILL.md")):
        found[os.path.basename(os.path.dirname(p))] = p
    return found


def stamp(text):
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def events_in(line, known):
    try:
        rec = json.loads(line)
    except Exception:
        return []
    t = stamp(rec.get("timestamp") or "")
    att = rec.get("attachment") or {}
    if att.get("type") == "hook_blocking_error":
        text = ((att.get("blockingError") or {}).get("blockingError") or "").strip().split("\n")[0]
        return [[t, "hook", RE_PR_URL.sub(r"\1#\2", text.replace(HOME, "~"))[:120]]]
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        return [[t, "skill", c["input"]["skill"]] for c in content
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Skill"
                and isinstance(c.get("input"), dict) and c["input"].get("skill")]
    if isinstance(content, str) and "<command-name>/" in content:
        name = content.split("<command-name>/", 1)[1].split("<", 1)[0].strip()
        return [[t, "skill", name]] if name in known else []
    return []


def scan(path, start, known):
    """Events in the complete lines from byte `start` on, and the offset to resume from."""
    with open(path, "rb") as fh:
        try:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:          # empty file
            return [], 0
        with mm:
            end = mm.rfind(b"\n") + 1
            spans = set()
            for needle in NEEDLES:
                i = mm.find(needle, start, end)
                while i != -1:
                    nl = mm.rfind(b"\n", start, i)
                    a = nl + 1 if nl != -1 else start
                    b = mm.find(b"\n", i, end)
                    spans.add((a, b))
                    i = mm.find(needle, b, end)
            events = []
            for a, b in sorted(spans):
                events += events_in(mm[a:b], known)
            return events, max(end, start)


def main():
    os.makedirs(CACHE, exist_ok=True)
    lock = open(SUMMARY + ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return                      # a pass is already running
    now = time.time()
    summary = read_json(SUMMARY)
    summary["last_attempt"] = now
    write_json(SUMMARY, summary)    # the cockpit stops starting passes while this one runs
    known = installed()
    cutoff = now - WINDOW
    old = read_json(STATE).get("files") or {}
    files = {}
    for path in glob.glob(os.path.join(CLAUDE_DIR, "projects", "**", "*.jsonl"), recursive=True):
        try:
            st = os.stat(path)
        except OSError:
            continue
        if st.st_mtime < cutoff:
            continue
        prev = old.get(path) or {}
        offset, events = prev.get("offset") or 0, prev.get("events") or []
        if st.st_size < offset:     # rewritten: read it again from the top
            offset, events = 0, []
        if st.st_size > offset:
            new, offset = scan(path, offset, known)
            events = events + new
        files[path] = {"offset": offset, "events": [e for e in events if e[0] >= cutoff]}
    seen, fired, refusals = set(), {}, []
    for f in files.values():
        for t, kind, name in f["events"]:
            if (t, kind, name) in seen:     # a resumed session repeats its history
                continue
            seen.add((t, kind, name))
            if kind == "skill":
                c = fired.setdefault(name, [0, 0])
                c[0] += 1
                c[1] = max(c[1], t)
            else:
                refusals.append([t, name])
    write_json(STATE, {"files": files})
    write_json(SUMMARY, {"last_attempt": now, "fetched_at": time.time(), "window": WINDOW,
                         "installed": known, "fired": fired, "refusals": sorted(refusals)[-20:]})


if __name__ == "__main__":
    main()
