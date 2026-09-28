#!/usr/bin/env python3
"""Neon Sumi cockpit: the machine-wide view, for a narrow terminal pane.

The status line is per session and has a row budget. Everything that is the
same in every session lives here instead: your open PRs everywhere, the GitHub
inbox, every listening port grouped by who owns it, your boards, services and
docs. Every block is always there (an empty one says so) and says how old its
data is, so you can trust that nothing is missing.

Same caches and collectors as the status line; opening it keeps them fresh
when no session is running.

    python3 cockpit.py           live, redraws every 2 s (ctrl+c to leave)
    python3 cockpit.py --once    one frame
"""
import importlib.util
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REFRESH = 2.0
WORK_TTL = 300
NOTIF_TTL = 60

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


def head(icon, text, colour, note="", fetched=None):
    age = ""
    if fetched:
        secs = time.time() - fetched
        age = ("%s · %s ago%s" % (sl.INK, sl.fmt_age(secs), RST)) if secs <= 90 else \
              ("%s · stale %s%s" % (sl.AMB, sl.fmt_age(secs), RST))
    return "%s%s %s%s%s%s  %s%s%s%s" % (colour, icon, sl.BOLD, sl.PAPER, text, RST, D, note, RST, age)


def line(label, colour, body, width=12):
    return "  %s%s%s %s" % (colour, label[:width].ljust(width), RST, body)


def work_rows(width):
    work = keep_fresh("work.json", WORK_TTL, "work")
    prs = sorted(work.get("prs") or [], key=lambda p: p.get("updated") or "", reverse=True)
    rows = [head(sl.ICON["task"], "work", sl.MAUVE, ("%d open PRs" % len(prs)) if prs else "no open PRs",
                 work.get("fetched_at"))]
    owners = []
    for p in prs:
        owner = p["repo"].split("/")[0]
        if owner not in owners:
            owners.append(owner)
    for owner in owners:
        mine = [p for p in prs if p["repo"].startswith(owner + "/")]
        p = mine[0]
        txt = sl.cut("%s #%d %s" % (p["repo"].split("/")[-1], p["number"], p["title"]), max(20, width - 20))
        rows.append(line(sl.cut(owner, 12), sl.BLUE, "%s%2d%s  %s" % (D, len(mine), RST, sl.osc8(p["url"], sl.PAPER + txt + RST))))
    if prs:
        def age(p):
            try:
                return (time.time() - time.mktime(time.strptime(p["updated"][:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
            except (ValueError, KeyError):
                return 0
        stale = [p for p in prs if age(p) > 30]
        if stale:
            o = stale[-1]
            rows.append(line("forgotten", sl.AMB, "%s%2d%s  %s" % (sl.AMB, len(stale), RST, sl.osc8(
                o["url"], "%soldest %s #%d · %d d%s" % (D, sl.cut(o["repo"].split("/")[-1], 16), o["number"], age(o), RST)))))
    return rows


def inbox_rows(width):
    notif = keep_fresh("notifications.json", NOTIF_TTL, "notifications")
    n = notif.get("count") or 0
    rows = [head(sl.ICON["bell"], "inbox", sl.AMB, ("%d unread" % n) if n else "nothing unread", notif.get("fetched_at"))]
    for it in (notif.get("items") or [])[:3]:
        txt = sl.cut("%s %s" % ((it.get("repo") or "").split("/")[-1], it.get("title") or ""), width - 4)
        rows.append("  " + sl.osc8(it.get("url") or "https://github.com/notifications", sl.PAPER + txt + RST))
    return rows


def port_rows(width):
    ports = sl.ports_cache()
    pl = ports.get("ports") or []
    web = [p for p in pl if sl.viewable(p)]
    rows = [head(sl.ICON["ports"], "ports", sl.TEAL, "%d · %d open in a browser" % (len(pl), len(web)),
                 ports.get("fetched_at"))]
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
    for (kind, name, d), ps in sorted(groups.items()):
        if kind == "0repo":
            label = sl.osc8(sl.link_for(d), "%s%-18s%s" % (sl.GRN, sl.cut(name, 18), RST))
        else:
            label = "%s%-18s%s" % (sl.CYN if kind == "1app" else D, name, RST)
        if kind == "2claude":
            body = "%s%d session proxies · not web%s" % (D, len(ps), RST)
        elif kind == "3os":
            body = "%s%s%s" % (D, " ".join(":%d" % p["port"] for p in ps), RST)
        else:
            body = " ".join(sl.osc8("http://localhost:%d" % p["port"], "%s:%d ↗%s" % (
                sl.GRN if kind == "0repo" else sl.CYN, p["port"], RST)) if sl.viewable(p) else "%s:%d%s" % (D, p["port"], RST)
                for p in ps)
        rows.append("  %s %s" % (label, body))
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
    rows.append(head(sl.ICON["board"], "boards", sl.AMB, "" if boards else "none in config.json"))
    rows += chip_rows([sl.osc8(b.get("url"), "%s%s%s" % (sl.PAPER, sl.cut(b.get("label") or "", 22), RST) +
                               ("%s #%d%s" % (sl.AMB, b["number"], RST) if b.get("number") else "")) for b in boards], width)
    rows.append("")
    services = cfg.get("services") or []
    rows.append(head(sl.ICON["services"], "services", sl.TEAL, "" if services else "none in config.json"))
    rows += chip_rows([sl.osc8(e.get("url"), "%s%s%s" % (sl.CYN, e.get("label") or "", RST)) for e in services], width)
    rows.append("")
    res = cfg.get("resources") or []
    rows.append(head(sl.ICON["guide"], "resources", sl.PINK, "" if res else "none in config.json"))
    rows += chip_rows([sl.osc8(e.get("url"), "%s%s%s" % (sl.CYN, e.get("label") or "", RST)) for e in res], width)
    return rows


def frame(width=None):
    width = max(40, width or shutil.get_terminal_size((56, 40)).columns)
    sl.NOW = time.time()
    sl.CONFIG = sl.read_json(sl.CONFIG_FILE)
    rows = ["%s%s neon sumi%s  %s%s%s" % (sl.MAUVE + sl.BOLD, sl.ICON["services"], RST, D, time.strftime("%H:%M:%S"), RST), ""]
    usage = sl.safe(sl.usage_rows, sl.read_json(sl.RATE_LIMITS_FILE))
    if usage:
        rows += usage.split("\n") + [""]
    for block in (work_rows, inbox_rows, port_rows, link_rows):
        got = sl.safe(block, width)
        if got:
            rows += got + [""]
    return rows


def main(argv):
    if "--once" in argv:
        sys.stdout.write("\n".join(frame()) + "\n")
        return
    sys.stdout.write("\033[?25l")
    try:
        while True:
            height = shutil.get_terminal_size((56, 40)).lines
            sys.stdout.write("\033[H\033[2J" + "\n".join(frame()[:height - 1]))
            sys.stdout.flush()
            time.sleep(REFRESH)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h\n")


if __name__ == "__main__":
    main(sys.argv[1:])
