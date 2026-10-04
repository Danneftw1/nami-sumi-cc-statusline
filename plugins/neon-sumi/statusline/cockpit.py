#!/usr/bin/env python3
"""Neon Sumi cockpit: the machine-wide view, for a narrow terminal pane.

The status line is per session and has a row budget. Everything that is the
same in every session lives here instead: your 5-hour and weekly limits,
every listening port grouped by who owns it, your open PRs everywhere, the
GitHub inbox, the skills Claude loaded this week and the ones that stayed
silent, your boards, services and docs. Live data first, so a short pane
loses the slow data.
Every block is always there (an empty one says so) and says how old its data
is, so you can trust that nothing is missing.

Same caches and collectors as the status line; opening it keeps them fresh
when no session is running.

    python3 cockpit.py           live, redraws every 2 s (ctrl+c to leave)
    python3 cockpit.py --once    one frame
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REFRESH = 2.0
WORK_TTL = 300
NOTIF_TTL = 60
SKILLS_TTL = 30
SKILLS_ICON = chr(0xF0EB)
LIST_MAX = 8

_spec = importlib.util.spec_from_file_location("neon_sumi_statusline", os.path.join(HERE, "statusline.py"))
sl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sl)

RST, D = sl.RST, sl.DIM
SEP = D + " · " + RST
ALIAS = {"ControlCenter": "AirPlay", "rapportd": "Handoff", "Discord Helper (Renderer)": "Discord"}
RE_ANSI = re.compile(r"\x1b\[[0-9;:]*m|\x1b\]8;;.*?\x1b\\")


def vis(text):
    return len(RE_ANSI.sub("", text))


def keep_fresh(name, ttl, *args):
    """Start a collector when its cache is older than ttl; return the cache."""
    path = os.path.join(sl.CACHE, name)
    cache = sl.read_json(path)
    ttl = max(ttl, int(cache.get("poll_interval") or 0))
    if time.time() - (cache.get("last_attempt") or 0) >= ttl and (cache.get("backoff_until") or 0) <= time.time() \
            and os.path.isfile(sl.GH_POLLER):
        sl.spawn_detached([sys.executable, "-B", sl.GH_POLLER] + list(args))
    return cache


def head(icon, text, colour, note="", fetched=None, ttl=30):
    """A block heading: icon, name, a dim note, and how old the data is. Amber
    only once the data is a minute past its own refresh: stale is trouble."""
    age = ""
    if fetched:
        secs = time.time() - fetched
        age = ("%s · %s ago%s" % (D, sl.fmt_age(secs), RST)) if secs <= max(90, ttl + 60) else \
              ("%s · stale %s%s" % (sl.AMB, sl.fmt_age(secs), RST))
    return "%s%s %s%s%s%s  %s%s%s%s" % (colour, icon, sl.BOLD, sl.PAPER, text, RST, D, note, RST, age)


def unfetched(icon, text, colour, cache):
    """A block whose collector never answered: say so, never draw confident zeros.
    The collector's own error is trouble (amber); waiting for the first pass is not."""
    err = cache.get("error")
    return [head(icon, text, colour, "%s%s%s" % (sl.AMB, sl.cut(err, 40), RST) if err else "not fetched yet")]


def line(label, colour, body, width=12):
    return "  %s%s%s %s" % (colour, label[:width].ljust(width), RST, body)


def word_rows(label, words, width):
    """`label  a · b · c`, wrapped under the first word, dimmed."""
    pad = 2 + len(label) + 2
    rows, cur = [], ""
    for w in words:
        cand = w if not cur else cur + " · " + w
        if cur and pad + len(cand) > width:
            rows.append(cur)
            cur = w
        else:
            cur = cand
    rows.append(cur)
    return ["%s%s%s%s" % (D, ("  %s  " % label) if i == 0 else " " * pad, r, RST) for i, r in enumerate(rows)]


def capped(words):
    return words if len(words) <= LIST_MAX else words[:LIST_MAX] + ["+%d" % (len(words) - LIST_MAX)]


def skill_rows(width, limit=6):
    """Skills that fired in the last 7 days, most used first, each name linked to
    its SKILL.md; the skills of the same plugins that stayed silent; stops a hook
    refused today. skills_poller.py reads them from the session transcripts."""
    cache = sl.read_json(os.path.join(sl.CACHE, "skills.json"))
    if time.time() - (cache.get("last_attempt") or 0) >= SKILLS_TTL:
        sl.spawn_detached([sys.executable, "-B", os.path.join(HERE, "skills_poller.py")])
    if not cache.get("fetched_at"):
        return [head(SKILLS_ICON, "skills", sl.MAUVE, "reading transcripts…")]
    known = cache.get("installed") or {}
    fired = sorted(((k, n, t) for k, (n, t) in (cache.get("fired") or {}).items()), key=lambda f: (-f[1], -f[2]))
    rows = [head(SKILLS_ICON, "skills", sl.MAUVE, ("%d fired · 7 d" % len(fired)) if fired else "none fired in 7 d",
                 cache.get("fetched_at"), SKILLS_TTL)]
    nw = min(max([len(k) for k, _, _ in fired[:limit]] + [0]), max(width - 14, 8))
    for k, n, t in fired[:limit]:
        name = "%s%-*s%s" % (sl.CYN, nw, sl.cut(k, nw), RST)
        if k in known:
            name = sl.osc8(sl.link_for(known[k]) or "file://" + known[k], name)
        rows.append("  %s %s%3d%s  %s%s%s" % (name, sl.PAPER, n, RST, D, sl.fmt_age(time.time() - t), RST))
    if fired[limit:]:
        rows += word_rows("+%d" % len(fired[limit:]), capped([k for k, _, _ in fired[limit:]]), width)
    group = lambda k: k.split(":", 1)[0] if ":" in k else ""
    used = {group(k) for k, _, _ in fired}
    done = {k for k, _, _ in fired}
    silent = sorted(k for k in known if group(k) in used and k not in done)
    if silent:
        rows += word_rows("silent", capped(silent), width)
    lt = time.localtime()
    today = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    refused = [r for r in cache.get("refusals") or [] if r[0] >= today]
    if refused:
        n = "%d refused today" % len(refused)
        room = width - 2 - 5 - 3 - len(n) - 2
        warm = sl.AMB if time.time() - refused[-1][0] < 3600 else D
        rows.append("  %shooks%s   %s%s%s  %s" % (D, RST, warm, n, RST,
                                                 (D + sl.cut(refused[-1][1], room) + RST) if room > 8 else ""))
    return rows


def work_rows(width):
    work = keep_fresh("work.json", WORK_TTL, "work")
    if not work.get("fetched_at"):
        return unfetched(sl.ICON["task"], "work", sl.MAUVE, work)
    prs = sorted(work.get("prs") or [], key=lambda p: p.get("updated") or "", reverse=True)
    rows = [head(sl.ICON["task"], "work", sl.MAUVE, ("%d open PRs" % len(prs)) if prs else "no open PRs",
                 work.get("fetched_at"), WORK_TTL)]
    for p in prs[:LIST_MAX]:
        owner = p["repo"].split("/")[0]
        txt = sl.cut("%s #%d %s" % (p["repo"].split("/")[-1], p["number"], p["title"]), max(20, width - 15))
        rows.append(line(sl.cut(owner, 12), sl.BLUE, sl.osc8(p["url"], sl.PAPER + txt + RST)))
    if prs[LIST_MAX:]:
        rows += word_rows("+%d" % len(prs[LIST_MAX:]), capped(["%s #%d" % (p["repo"].split("/")[-1], p["number"])
                                                              for p in prs[LIST_MAX:]]), width)
    if prs:
        def age(p):
            try:
                return (time.time() - time.mktime(time.strptime(p["updated"][:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
            except (ValueError, KeyError):
                return 0
        stale = [p for p in prs if age(p) > 30]
        if stale:
            o = stale[-1]
            room = min(16, width - 37)
            repo = sl.cut(o["repo"].split("/")[-1], room) if room >= 6 else ""
            rows.append(line("forgotten", sl.AMB, "%s%2d%s  %s" % (sl.AMB, len(stale), RST, sl.osc8(
                o["url"], "%soldest %s#%d · %d d%s" % (D, (repo + " ") if repo else "", o["number"], age(o), RST)))))
    return rows


def inbox_rows(width):
    notif = keep_fresh("notifications.json", NOTIF_TTL, "notifications")
    if not notif.get("fetched_at"):
        return unfetched(sl.ICON["bell"], "inbox", sl.BLUE, notif)
    n = notif.get("count") or 0
    rows = [head(sl.ICON["bell"], "inbox", sl.BLUE, ("%d unread" % n) if n else "nothing unread",
                 notif.get("fetched_at"), NOTIF_TTL)]
    for it in (notif.get("items") or [])[:3]:
        txt = sl.cut("%s %s" % ((it.get("repo") or "").split("/")[-1], it.get("title") or ""), width - 4)
        rows.append("  " + sl.osc8(it.get("url") or "https://github.com/notifications", sl.PAPER + txt + RST))
    return rows


def port_rows(width):
    ports = sl.ports_cache()
    if not ports.get("fetched_at"):
        return unfetched(sl.ICON["ports"], "ports", sl.TEAL, ports)
    pl = ports.get("ports") or []
    web = [p for p in pl if sl.viewable(p)]
    rows = [head(sl.ICON["ports"], "ports", sl.TEAL, "%d · %d in a browser" % (len(pl), len(web)),
                 ports.get("fetched_at"), sl.PORTS_TTL)]
    groups = {}
    for p in pl:
        svc = p.get("service") or ""
        if re.match(r"^\d+\.\d+\.\d+$|^claude$", svc):
            key = ("2claude", "claude code", "")
        elif p.get("project"):
            key = ("0repo", re.sub(r"-[0-9a-f]{6}$", "", p["project"].replace(" wt:", " ⎇ ")), p.get("dir"))
        elif sl.viewable(p):
            key = ("1app", svc.split(" ")[0].lower(), "")
        else:
            key = ("3os", "system", "")
        groups.setdefault(key, []).append(p)
    # The label column fits the longest name, so a worktree's name is not cut while the row has room.
    nw = min(max([len(name) for _, name, _ in groups] + [8]), max(width - 22, 8))
    for (kind, name, d), ps in sorted(groups.items()):
        cell = "%-*s" % (nw, sl.cut(name, nw))
        if kind == "0repo":
            label = sl.osc8(sl.link_for(d), "%s%s%s" % (sl.GRN, cell, RST))
        else:
            label = "%s%s%s" % (sl.CYN if kind == "1app" else D, cell, RST)
        if kind == "2claude":
            chips = ["%s%d proxies · not web%s" % (D, len(ps), RST)]
        elif kind == "3os":
            chips = ["%s:%d%s" % (D, p["port"], RST) for p in ps]
        else:
            chips = [sl.osc8("http://localhost:%d" % p["port"], "%s:%d ↗%s" % (
                sl.GRN if kind == "0repo" else sl.CYN, p["port"], RST)) if sl.viewable(p) else "%s:%d%s" % (D, p["port"], RST)
                for p in ps]
        # Every port stays visible: the chips wrap under the first one rather than run off the pane.
        wrapped = chip_rows(chips, width, indent=2 + nw + 1)
        rows.append("  %s %s" % (label, wrapped[0].lstrip(" ")))
        rows += wrapped[1:]
    if not pl:
        rows.append("  %snothing listening%s" % (D, RST))
    return rows


def chip_rows(chips, width, indent=2):
    rows, cur = [], ""
    for c in chips:
        cand = c if not cur else cur + SEP + c
        if cur and vis(cand) + indent > width:
            rows.append(" " * indent + cur)
            cur = c
        else:
            cur = cand
    if cur:
        rows.append(" " * indent + cur)
    return rows


def link_rows(width):
    cfg = sl.read_json(sl.CONFIG_FILE)
    rows = []
    boards = [b for owner in (cfg.get("boards") or {}).values() for b in owner]
    rows.append(head(sl.ICON["board"], "boards", sl.BLUE, "" if boards else "none in config.json"))
    rows += chip_rows([sl.osc8(b.get("url"), "%s%s%s" % (sl.PAPER, sl.cut(b.get("label") or "", 22), RST) +
                               ("%s #%d%s" % (D, b["number"], RST) if b.get("number") else "")) for b in boards], width)
    rows.append("")
    services = cfg.get("services") or []
    rows.append(head(sl.ICON["services"], "services", sl.TEAL, "" if services else "none in config.json"))
    rows += chip_rows([sl.osc8(e.get("url"), "%s%s%s" % (sl.CYN, e.get("label") or "", RST)) for e in services], width)
    rows.append("")
    res = cfg.get("resources") or []
    rows.append(head(sl.ICON["guide"], "resources", sl.PINK, "" if res else "none in config.json"))
    rows += chip_rows([sl.osc8(e.get("url"), "%s%s%s" % (sl.CYN, e.get("label") or "", RST)) for e in res], width)
    return rows


def usage_block(width):
    """5h and weekly bars. The pane hands over the session's own figures in
    NEON_SUMI_RATE_LIMITS; a terminal cockpit reads what the status line last wrote."""
    given = os.environ.get("NEON_SUMI_RATE_LIMITS")
    try:
        data = json.loads(given) if given else sl.read_json(sl.RATE_LIMITS_FILE)
    except ValueError:
        data = {}
    if not (data.get("rate_limits") or {}):
        return [head(sl.ICON["5h"], "usage", sl.TEAL, "no session has reported limits yet")]
    # The pane's figures are the session's own, live by construction: no age. The file's age is its own stamp.
    fetched = None if given else (data.get("fetched_at") or
                                  (os.path.getmtime(sl.RATE_LIMITS_FILE) if os.path.isfile(sl.RATE_LIMITS_FILE) else None))
    bars = sl.safe(sl.usage_rows, data)
    rows = [head(sl.ICON["5h"], "usage", sl.TEAL, "this session" if given else "", fetched, 60)]
    return rows + (bars.split("\n") if bars else [])


def frame(width=None):
    width = max(40, width or shutil.get_terminal_size((56, 40)).columns)
    sl.NOW = time.time()
    sl.CONFIG = sl.read_json(sl.CONFIG_FILE)
    rows = ["%s%s neon sumi%s  %s%s%s" % (sl.MAUVE + sl.BOLD, sl.ICON["services"], RST, D, time.strftime("%H:%M"), RST), ""]
    # Live data first: when the pane is short, what is lost is the slow data at the bottom.
    for block in (usage_block, port_rows, work_rows, inbox_rows, skill_rows, link_rows):
        got = sl.safe(block, width)
        if got:
            rows += got + [""]
    # No row wider than the pane: a row that would wrap ends in an ellipsis at a chip boundary.
    return [sl.fit(r, width) for r in rows]


def headings_in(rows):
    """The block names among rows, for the mark that says what a short pane cut."""
    names = []
    for r in rows:
        m = re.match(r"^\S+ (\w[\w ]*?)  ", RE_ANSI.sub("", r))
        if m and not r.startswith(" "):
            names.append(m.group(1))
    return names


def main(argv):
    if "--once" in argv:
        sys.stdout.write("\n".join(frame()) + "\n")
        return
    sys.stdout.write("\033[?25l")
    try:
        while True:
            height = shutil.get_terminal_size((56, 40)).lines
            rows = frame()
            if len(rows) > height - 1:
                cut = rows[height - 2:]
                lost = headings_in(cut)
                rows = rows[:height - 2] + ["%s+%d rows%s%s" % (D, len(cut), (" · " + ", ".join(lost)) if lost else "", RST)]
            sys.stdout.write("\033[H\033[2J" + "\n".join(rows))
            sys.stdout.flush()
            time.sleep(REFRESH)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\n")


if __name__ == "__main__":
    main(sys.argv[1:])
