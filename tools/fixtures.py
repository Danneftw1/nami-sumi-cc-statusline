#!/usr/bin/env python3
"""A made-up world to render the docs from: no real repo, person or machine.

Builds, under <root>:
  home/code/tidepool            a real git repo (origin lanternworks/tidepool)
  home/code/tidepool/.claude/worktrees/tide-tables-3f9a21   a linked worktree on
                                claude/42-tide-tables with uncommitted edits
  home/.cache/neon-sumi/...     collector caches: refs, ports, work, inbox, history
  tmp/                          per-repo caches (git facts, the branch's PR)
  transcript.jsonl              a short chat that mentions tickets, a PR, files
  config.json                   links for the repo, boards, services

    python3 tools/fixtures.py <root>   -> prints the payload path
"""
import json
import os
import subprocess
import sys
import time

NOW = time.time()
SLUG = "lanternworks/tidepool"
BOARD = "https://github.com/orgs/lanternworks/projects/3"


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


def git(cwd, *args):
    subprocess.run(["git", "-C", cwd, "-c", "user.name=tidepool", "-c", "user.email=tidepool@example.invalid"] + list(args),
                   check=True, capture_output=True)


def build(root):
    home = os.path.join(root, "home")
    repo = os.path.join(home, "code", "tidepool")
    wt = os.path.join(repo, ".claude", "worktrees", "tide-tables-3f9a21")
    tmp = os.path.join(root, "tmp")
    cache = os.path.join(home, ".cache", "neon-sumi")
    if not os.path.isdir(os.path.join(repo, ".git")):
        os.makedirs(os.path.join(repo, "docs"))
        os.makedirs(os.path.join(repo, "design"))
        with open(os.path.join(repo, "README.md"), "w") as fh:
            fh.write("# tidepool\n")
        git(repo, "init", "-q", "-b", "main")
        git(repo, "remote", "add", "origin", "git@github.com:%s.git" % SLUG)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "Start tidepool")
        for name in ("night-market-8c1d02", "offline-map-b77e10"):
            git(repo, "worktree", "add", "-q", "-b", "claude/" + name, os.path.join(repo, ".claude", "worktrees", name))
        git(repo, "worktree", "add", "-q", "-b", "claude/42-tide-tables", wt)
    os.makedirs(os.path.join(wt, "docs"), exist_ok=True)
    os.makedirs(os.path.join(wt, "design"), exist_ok=True)
    with open(os.path.join(wt, "docs", "harbour-plan.md"), "w") as fh:
        fh.write("# Harbour page\n\nTide tables, sunrise, the ferry.\n" * 3)
    with open(os.path.join(wt, "design", "tides.png"), "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
    with open(os.path.join(wt, "tides.py"), "w") as fh:
        fh.write("def tides():\n    return []\n" * 20)
    with open(os.path.join(wt, "README.md"), "a") as fh:
        fh.write("\nTide tables live on the harbour page.\n")

    write(os.path.join(cache, "refs", "lanternworks__tidepool.json"), {"last_attempt": 4102444800, "items": {
        "37": {"kind": "pr", "title": "Draw the forecast as neon tubes", "state": "MERGED",
               "url": "https://github.com/%s/pull/37" % SLUG, "fetched_at": 4102444800},
        "45": {"kind": "ticket", "title": "Offline mode for the harbour map", "state": "OPEN", "status": "Todo",
               "board": "Tidepool", "board_url": BOARD, "url": "https://github.com/%s/issues/45" % SLUG, "fetched_at": 4102444800},
        "51": {"kind": "issue", "title": "Crash when the forecast is empty", "state": "OPEN",
               "url": "https://github.com/%s/issues/51" % SLUG, "fetched_at": 4102444800}}})
    key = "lanternworks_tidepool-claude_42-tide-tables"
    write(os.path.join(tmp, key + ".gh.json"), {
        "fetched_at": NOW, "last_attempt": 4102444800, "backoff_until": 0, "slug": SLUG, "branch": "claude/42-tide-tables",
        "pr": {"number": 48, "title": "Tide tables for the harbour page", "url": "https://github.com/%s/pull/48" % SLUG,
               "state": "OPEN", "draft": False, "review": "REVIEW_REQUIRED", "ci": {"pass": 7, "run": 2, "fail": 0, "total": 9}},
        "task": {"number": 42, "title": "Tide tables on the harbour page", "url": "https://github.com/%s/issues/42" % SLUG,
                 "state": "OPEN", "status": "In progress", "board": "Tidepool", "board_url": BOARD}, "epic": None})
    ports = [
        {"port": 5173, "service": "node", "project": "tidepool wt:tide-tables-3f9a21", "dir": wt, "http": 200},
        {"port": 8787, "service": "workerd", "project": "tidepool", "dir": repo, "http": 404},
        {"port": 11434, "service": "ollama", "project": "", "dir": "/", "http": 200},
        {"port": 5000, "service": "ControlCenter", "project": "", "dir": "/", "http": 403},
        {"port": 7000, "service": "ControlCenter", "project": "", "dir": "/", "http": 403},
        {"port": 49152, "service": "rapportd", "project": "", "dir": "/", "http": 0},
        {"port": 52811, "service": "2.1.283", "project": "tidepool", "dir": repo, "http": 407},
        {"port": 52934, "service": "2.1.283", "project": "tidepool", "dir": wt, "http": 407},
    ]
    write(os.path.join(cache, "ports.json"), {"fetched_at": NOW - 3, "last_attempt": 4102444800, "ports": ports})
    iso = lambda days: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - days * 86400))
    prs = [("lanternworks/tidepool", 48, "Tide tables for the harbour page", 0.1),
           ("lanternworks/tidepool", 44, "Ferry times from the open data feed", 3),
           ("lanternworks/lighthouse", 12, "Rotate the beam with the sunset", 6),
           ("kelp-studio/field-notes", 7, "Photo grid for the spring walk", 41),
           ("kelp-studio/field-notes", 5, "Tag species in the margin", 64)]
    write(os.path.join(cache, "work.json"), {"fetched_at": NOW - 58, "last_attempt": 4102444800, "prs": [
        {"repo": r, "number": n, "title": t, "url": "https://github.com/%s/pull/%d" % (r, n), "updated": iso(d)} for r, n, t, d in prs]})
    write(os.path.join(cache, "notifications.json"), {"fetched_at": NOW - 41, "last_attempt": 4102444800, "poll_interval": 60,
                                                      "count": 2, "items": [
        {"title": "Review requested: Tide tables for the harbour page", "repo": SLUG, "url": "https://github.com/%s/pull/48" % SLUG},
        {"title": "CI passed on main", "repo": "lanternworks/lighthouse", "url": "https://github.com/lanternworks/lighthouse"}]})
    samples, p = [], 34.0
    for m in range(60, -1, -1):
        if not 28 <= m <= 36:
            p += 0.4 + (0.25 if m % 7 == 0 else 0.0)
        samples.append([NOW - m * 60, round(min(p, 58.0), 1)])
    write(os.path.join(cache, "usage-history.json"), {"5h": samples})
    write(os.path.join(cache, "rate-limits.json"), {"rate_limits": {
        "five_hour": {"used_percentage": 58, "resets_at": NOW + 71 * 60},
        "seven_day": {"used_percentage": 41, "resets_at": NOW + 4 * 86400 + 3600}}})
    write(os.path.join(root, "config.json"), {
        "guide_url": "https://code.claude.com/docs/en/statusline",
        "repos": {SLUG: [{"label": "board #3", "kind": "board", "url": BOARD},
                         {"label": "Vercel", "kind": "vercel", "url": "https://vercel.com/dashboard"},
                         {"label": "v0 chat", "kind": "v0", "url": "https://v0.app/chat"}]},
        "boards": {"lanternworks": [{"label": "Tidepool", "number": 3, "url": BOARD},
                                    {"label": "Lighthouse", "number": 4, "url": "https://github.com/orgs/lanternworks/projects/4"}]},
        "services": [{"label": "GitHub", "url": "https://github.com"}, {"label": "Vercel", "url": "https://vercel.com/dashboard"},
                     {"label": "v0", "url": "https://v0.app/chat"}],
        "resources": [{"label": "status line docs", "url": "https://code.claude.com/docs/en/statusline"},
                      {"label": "CC changelog", "url": "https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md"}]})
    tp = os.path.join(root, "transcript.jsonl")
    chat = [("user", "Pick up #42 in the worktree, and keep #45 in mind."),
            ("assistant", "PR #37 already drew the forecast. I updated %s and %s, refactored %s, and saved %s. "
                          "v0 has the layout: https://v0.app/chat. Docs: https://code.claude.com/docs/en/statusline. "
                          "Filed issue #51 for the empty forecast." % (
                              os.path.join(wt, "README.md"), os.path.join(wt, "docs", "harbour-plan.md"),
                              os.path.join(wt, "tides.py"), os.path.join(wt, "design", "tides.png")))]
    with open(tp, "w", encoding="utf-8") as fh:
        for role, text in chat:
            fh.write(json.dumps({"type": role, "message": {"role": role, "content": [{"type": "text", "text": text}]}}) + "\n")
    payload = {"session_id": "docs-fixture", "transcript_path": tp, "cwd": wt,
               "workspace": {"current_dir": wt, "project_dir": wt,
                             "repo": {"host": "github.com", "owner": "lanternworks", "name": "tidepool"}},
               "model": {"id": "claude-opus", "display_name": "Opus"}, "effort": {"level": "high"},
               "cost": {"total_cost_usd": 4.12},
               "context_window": {"total_input_tokens": 342000, "context_window_size": 1000000, "used_percentage": 34},
               "rate_limits": {"five_hour": {"used_percentage": 58, "resets_at": NOW + 71 * 60},
                               "seven_day": {"used_percentage": 41, "resets_at": NOW + 4 * 86400 + 3600}}}
    path = os.path.join(root, "payload.json")
    write(path, payload)
    return path


if __name__ == "__main__":
    print(build(os.path.abspath(sys.argv[1])))
