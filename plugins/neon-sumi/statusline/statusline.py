#!/usr/bin/env python3
"""Neon Sumi -- a Claude Code status line.

Neon tubes mounted on an ink-wash scroll: neon is reserved for what is live
(bar fills, percentages, state, links); everything static is warm ink and paper.

One python process per render, standard library only, Python 3.9+. Claude Code
pipes its status-line JSON on stdin; this prints the rows.

RENDER READS, COLLECTORS FETCH. Nothing on the render path touches the network.
GitHub and port data come from detached collectors (gh_poller.py,
ports_poller.py) that the renderer starts when their cache is old, guarded by
one mkdir lock and one cache shared by every open session.

SECTIONS, one coloured gutter each (no header rows: every row is a chat row lost)
  Claude   model · effort · advisor · cost · guide
           ctx / 5h / wk bars, links and readable files mentioned in the chat
  GitHub   repo · branch · diff, worktree, PR / ticket / issue rows (each with
           its title and state), and where the repo lives online
  Machine  local ports that actually serve a page

EDITIONS: "classic" (any terminal) and "tubes" (Ghostty: heavy box-drawing
tubes, a sparkline of the last hour and a pace projection on the 5h row).
config.json "edition": "auto" picks tubes when TERM_PROGRAM is ghostty.

Every row fails open to "" -- one broken segment never blanks the line.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")
CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")
CONFIG_FILE = os.environ.get("NEON_SUMI_CONFIG") or os.path.join(ROOT, "config.json")
CACHE = os.environ.get("NEON_SUMI_CACHE") or os.path.join(HOME, ".cache", "neon-sumi")
TMP = os.environ.get("NEON_SUMI_TMP") or os.path.join(os.environ.get("TMPDIR") or "/tmp", "neon-sumi")
GH_POLLER = os.path.join(ROOT, "gh_poller.py")
PORTS_POLLER = os.path.join(ROOT, "ports_poller.py")
PORTS_CACHE = os.path.join(CACHE, "ports.json")
REFS_DIR = os.path.join(CACHE, "refs")
HISTORY_FILE = os.path.join(CACHE, "usage-history.json")
RATE_LIMITS_FILE = os.path.join(CACHE, "rate-limits.json")
USAGE_URL = "https://claude.ai/settings/usage"

sys.path.insert(0, ROOT)
try:
    import pathlink
except Exception:
    pathlink = None

TAIL_BYTES = 256 * 1024
GIT_TTL = 2              # seconds between git refreshes (~17 ms for both calls)
GH_TTL = 60              # gh_poller respawn per repo+branch
GH_TTL_CI = 20           # ... while CI is running
PORTS_TTL = 5
REFS_TTL = 300
REFS_RETRY = 5
BAR_WIDTH = 20
LABEL_WIDTH = 6
MAX_LINKS = 6
HISTORY_KEEP = 120       # one sample a minute: two hours

RST = "\033[0m"
BOLD = "\033[1m"
NOW = time.time()


def fg(r, g, b):
    return "\033[38;2;%d;%d;%dm" % (int(r), int(g), int(b))


PAPER = fg(232, 220, 198)     # labels: rice paper
DIM = fg(146, 134, 120)       # secondary text: stone ink
INK = fg(84, 74, 70)          # rules, separators, unlit cells: sumi
SEP = INK + " │ " + RST
DOT = INK + " · " + RST
GRN = fg(64, 255, 170)        # neon mint
RED = fg(255, 56, 100)        # neon red
AMB = fg(255, 190, 40)        # sodium amber
CYN = fg(0, 234, 255)         # neon cyan
TEAL = fg(0, 255, 204)        # neon teal
BLUE = fg(64, 156, 255)       # electric blue
MAUVE = fg(196, 110, 255)     # neon violet
PINK = fg(255, 46, 196)       # neon magenta
UL_ON = "\033[4m\033[58;2;255;46;196m"   # link: underline, magenta where SGR 58 is supported
UL_OFF = "\033[24m\033[59m"

# Every bar keeps its own hue family until it is in trouble (70 % / 85 %).
IDENTITY = {"ctx": ((120, 60, 255), (236, 72, 255)),    # violet -> magenta
            "5h": ((0, 170, 150), (0, 240, 255)),        # deep teal -> cyan
            "wk": ((255, 130, 0), (255, 222, 70))}       # amber -> gold
LABEL_COLOUR = {"5h": TEAL, "wk": AMB}

ICON = {
    "ctx": chr(0xF1C0), "5h": chr(0xF017), "wk": chr(0xF073), "link": chr(0xF0C1), "file": chr(0xF15B),
    "repo": chr(0xF401), "branch": chr(0xE0A0), "wt": chr(0xF07C), "home": chr(0xF015), "pr": chr(0xF407),
    "refs": chr(0xF41B), "board": chr(0xF0DB), "cloud": chr(0xF0C2), "ports": chr(0xF1E6), "github": chr(0xF09B),
    "vercel": "▲", "v0": chr(0xF121), "supabase": chr(0xF1C0), "grafana": chr(0xF201), "guide": chr(0xF02D),
    "ok": chr(0xF00C), "fail": chr(0xF00D), "run": chr(0xF1CE), "review": chr(0xF06E), "local": chr(0xF1E6),
    "services": chr(0xF0E8), "bell": chr(0xF0F3), "task": chr(0xF0AE),
}
GUTTER = {"claude": PINK, "github": BLUE, "machine": TEAL}


# ── helpers ────────────────────────────────────────────────────────────────────
def osc8(url, text):
    """OSC 8 hyperlink, underlined so a clickable thing looks clickable. The
    underline is re-asserted after every reset inside `text`."""
    if not url or not text:
        return text
    return "\033]8;;%s\033\\%s%s%s\033]8;;\033\\" % (url, UL_ON, text.replace(RST, RST + UL_ON), UL_OFF)


def lerp(a, b, t):
    return a + (b - a) * t


def severity(pct):
    return 2 if pct >= 85 else 1 if pct >= 70 else 0


def ramp_stops(sev, kind=None):
    if sev >= 2:
        return (255, 40, 60), (255, 120, 0)
    if sev >= 1:
        return (255, 100, 150), (255, 190, 0)
    return IDENTITY.get(kind, ((255, 0, 255), (0, 255, 255)))


def pct_colour(sev):
    return fg(255, 60, 90) if sev >= 2 else fg(255, 190, 0) if sev >= 1 else fg(0, 255, 255)


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = "%s.tmp.%d" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)
    except Exception:
        pass


def spawn_detached(argv):
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
    except Exception:
        pass


def tail_bytes(path, n=TAIL_BYTES):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - n))
            return fh.read(), size
    except Exception:
        return b"", 0


def fmt_tokens(n):
    return "%.1fk" % (n / 1000) if n >= 1000 else str(int(n))


def fmt_countdown(resets_at, now=None):
    if not resets_at:
        return ""
    s = int(resets_at - (now if now is not None else NOW))
    if s <= 0:
        return "now"
    if s < 3600:
        return "%dm" % max(1, s // 60)
    if s < 86400:
        return "%dh%02dm" % (s // 3600, (s % 3600) // 60)
    return "%dd%dh" % (s // 86400, (s % 86400) // 3600)


def fmt_age(secs):
    secs = max(0, int(secs))
    if secs < 60:
        return "%ds" % secs
    if secs < 3600:
        return "%dm" % (secs // 60)
    if secs < 86400:
        return "%dh" % (secs // 3600)
    return "%dd" % (secs // 86400)


def cut(text, n):
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def bar_label(text, colour, bold=False, icon=""):
    """Icon + label padded to LABEL_WIDTH, so every row's body starts in the
    same column -- that is what makes the rows stack."""
    return "%s%s%s %s%s%s" % (BOLD if bold else "", colour, icon or " ", PAPER,
                              text[:LABEL_WIDTH].ljust(LABEL_WIDTH), RST)


def linked_label(url, text, colour, icon, bold=False):
    """A label that is also a link: the underline stops at the word, the
    padding after it stays plain."""
    text = text[:LABEL_WIDTH]
    return osc8(url, "%s%s%s %s%s%s" % (BOLD if bold else "", colour, icon, PAPER, text, RST)) + \
        " " * (LABEL_WIDTH - len(text))


def labelled(label, colour, body, icon=""):
    return "%s %s" % (bar_label(label, colour, icon=icon), body) if body else ""


def gutter(section, rows):
    col = GUTTER.get(section, DIM)
    out = []
    for r in rows:
        for line in (r or "").split("\n"):
            if line:
                out.append("%s▎%s %s" % (col, RST, line))
    return out


def safe(fn, *args):
    try:
        return fn(*args) or ""
    except Exception:
        return ""


CONFIG = {}


def config():
    return CONFIG


def edition():
    e = str(CONFIG.get("edition") or "auto").lower()
    if e == "auto":
        return "tubes" if os.environ.get("TERM_PROGRAM", "").lower() == "ghostty" else "classic"
    return "tubes" if e == "tubes" else "classic"


# ── bars ───────────────────────────────────────────────────────────────────────
def bar(pct, sev, width=BAR_WIDTH, kind=None):
    """Classic edition: a neon tube of ▰ cells, gradient fill, a white-hot
    leading cell, one cell of halo, unlit sumi glass for the rest."""
    pct = max(0, min(100, pct))
    filled = round(pct * width / 100)
    (r0, g0, b0), (r1, g1, b1) = ramp_stops(sev, kind)
    out = []
    for i in range(width):
        t = i / (width - 1) if width > 1 else 0
        r, g, b = lerp(r0, r1, t), lerp(g0, g1, t), lerp(b0, b1, t)
        if i < filled - 1:
            out.append(BOLD + fg(r, g, b) + "▰")
        elif i == filled - 1:
            out.append(BOLD + fg(lerp(r, 255, 0.55), lerp(g, 255, 0.55), lerp(b, 255, 0.55)) + "▰")
        elif i == filled and filled > 0:
            out.append(fg(r * 0.45, g * 0.45, b * 0.45) + "▰")
        else:
            out.append(fg(58, 50, 54) + "▱")
    return "".join(out) + RST


def tube(pct, sev, width=BAR_WIDTH, kind=None):
    """Tubes edition: heavy strokes on a thin unlit track, half-cell precision.
    Ghostty draws box glyphs itself, edge to edge, so the tube is unbroken."""
    pct = max(0.0, min(100.0, pct))
    full, half = divmod(int(round(pct * width * 2 / 100)), 2)
    (r0, g0, b0), (r1, g1, b1) = ramp_stops(sev, kind)
    out = []
    for i in range(width):
        t = i / (width - 1)
        r, g, b = lerp(r0, r1, t), lerp(g0, g1, t), lerp(b0, b1, t)
        if (i == full - 1 and not half) or (i == full and half):
            r, g, b = lerp(r, 255, 0.55), lerp(g, 255, 0.55), lerp(b, 255, 0.55)
        if i < full:
            out.append(BOLD + fg(r, g, b) + "━")
        elif i == full and half:
            out.append(BOLD + fg(r, g, b) + "╸")
        else:
            out.append(RST + fg(62, 52, 56) + "─")
    return "".join(out) + RST


def draw_bar(pct, sev, kind):
    return tube(pct, sev, kind=kind) if edition() == "tubes" else bar(pct, sev, kind=kind)


# ── Claude section ─────────────────────────────────────────────────────────────
MODEL_TIERS = [("fable", chr(0xF135), (203, 166, 247)), ("opus", chr(0xF005), (249, 226, 175)),
               ("sonnet", chr(0xF013), (137, 180, 250)), ("haiku", chr(0xF06C), (166, 227, 161))]
EFFORT_LEVELS = {"max": (chr(0xF06D), (243, 139, 168)), "xhigh": (chr(0xF0E7), (249, 226, 175)),
                 "high": (chr(0xF0E7), (249, 226, 175)), "medium": (chr(0xF0E7), (148, 226, 213)),
                 "low": (chr(0xF068), (99, 104, 128))}


def model_chip(data):
    m = data.get("model") or {}
    name = m.get("display_name", "") if isinstance(m, dict) else str(m)
    if not name:
        return ""
    name = re.sub(r"\s*\([^)]*context\)\s*$", "", name).strip()
    icon, rgb = chr(0xF128), (166, 173, 200)
    for key, k_icon, k_rgb in MODEL_TIERS:
        if key in name.lower():
            icon, rgb = k_icon, k_rgb
            break
    col = fg(*rgb)
    return "%s%s%s%s %s%s%s%s" % (BOLD, col, icon, RST, BOLD, col, name, RST)


def effort_chip(data):
    level = str((data.get("effort") or {}).get("level") or "").lower().strip()
    if not level:
        return ""
    icon, rgb = EFFORT_LEVELS.get(level, (chr(0xF0E7), (180, 190, 254)))
    col = fg(*rgb)
    return "%s%s%s%s %s%s%s" % (BOLD, col, icon, RST, col, level, RST)


def advisor_chip(data, tail, size):
    """The advisor model stamped on transcript records, plus how often it was
    called (counted incrementally over the whole transcript)."""
    adv = ""
    for line in reversed(tail.split(b"\n")):
        if b'"advisorModel"' not in line:
            continue
        try:
            val = json.loads(line).get("advisorModel")
        except Exception:
            continue
        if isinstance(val, str) and val.strip():
            adv = val.strip()
            break
    if not adv:
        adv = str(read_json(os.path.join(CLAUDE_DIR, "settings.json")).get("advisorModel") or "").strip()
    if not adv:
        return ""
    label = adv
    for tier in ("fable", "opus", "sonnet", "haiku"):
        if tier in adv.lower():
            label = tier
            break
    col = {"fable": MAUVE, "opus": AMB, "sonnet": BLUE, "haiku": GRN}.get(label, fg(250, 179, 135))
    suffix = ""
    tp = data.get("transcript_path")
    if tp and size:
        n = _advisor_count(tp, size, data.get("session_id") or "")
        if n > 0:
            suffix = " %s×%d%s" % (DIM, n, RST)
    return "%s%s %s%s%s" % (col, chr(0xF24E), label, RST, suffix)


def _advisor_count(path, size, sid):
    key = hashlib.sha1((sid or path).encode()).hexdigest()[:12]
    cache_path = os.path.join(TMP, "advisor-%s.json" % key)
    cache = read_json(cache_path)
    seen, count = int(cache.get("size", 0) or 0), int(cache.get("count", 0) or 0)
    if seen > size or cache.get("path") != path:
        seen, count = 0, 0
    if size > seen:
        try:
            with open(path, "rb") as fh:
                fh.seek(seen)
                count += fh.read().count(b'"name":"advisor"')
        except Exception:
            return count
        write_json(cache_path, {"path": path, "size": size, "count": count})
    return count


def cost_chip(data):
    c = (data.get("cost") or {}).get("total_cost_usd")
    if c is None:
        return ""
    col = fg(255, 60, 90) if c >= 8 else fg(255, 190, 0) if c >= 3 else fg(57, 255, 20)
    return "%s$%s%s%.2f%s" % (GRN, RST, col, c, RST)


def guide_chip():
    url = CONFIG.get("guide_url")
    return osc8(url, "%s%s %sguide%s" % (PINK, ICON["guide"], PAPER, RST)) if url else ""


def context_tokens(cw):
    total = cw.get("total_input_tokens")
    if isinstance(total, (int, float)) and not isinstance(total, bool):
        return total
    cu = cw.get("current_usage")
    if isinstance(cu, dict):
        vals = [cu.get(k) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")]
        if any(isinstance(v, (int, float)) for v in vals):
            return sum(v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool))
    return None


def context_gauge(data):
    cw = data.get("context_window") or {}
    size, used = cw.get("context_window_size"), context_tokens(cw)
    if not size or used is None:
        return ""
    pct = cw.get("used_percentage")
    if not isinstance(pct, (int, float)) or isinstance(pct, bool):
        pct = used / size * 100
    sev = max(severity(pct), 2 if used >= 700_000 else 1 if used >= 400_000 else 0)
    return "%s %s %s%3.0f%%%s  %s%s%s" % (bar_label("ctx", MAUVE, icon=ICON["ctx"]), draw_bar(pct, sev, "ctx"),
                                          pct_colour(sev), pct, RST, fg(116, 199, 236), fmt_tokens(used), RST)


def usage_windows(data):
    rl = data.get("rate_limits") or {}
    out = []
    for key, label in (("five_hour", "5h"), ("seven_day", "wk")):
        w = rl.get(key)
        if isinstance(w, dict) and isinstance(w.get("used_percentage"), (int, float)):
            out.append({"label": label, "percent": float(w["used_percentage"]), "resets_at": w.get("resets_at")})
    return out


def record_history(data):
    """One 5h sample a minute, for the tubes edition's sparkline and pace."""
    w = ((data.get("rate_limits") or {}).get("five_hour") or {})
    pct = w.get("used_percentage")
    if not isinstance(pct, (int, float)):
        return
    hist = read_json(HISTORY_FILE)
    samples = hist.get("5h") or []
    if samples and NOW - samples[-1][0] < 60:
        return
    samples.append([NOW, pct])
    write_json(HISTORY_FILE, {"5h": samples[-HISTORY_KEEP:]})


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(samples, n=12, bucket=300):
    vals = []
    for k in range(n):
        lo, hi = NOW - (n - k) * bucket, NOW - (n - k - 1) * bucket
        inb = [p for t, p in samples if lo <= t < hi]
        vals.append(max(inb) if inb else (vals[-1] if vals else None))
    known = [v for v in vals if v is not None]
    if not known:
        return ""
    vmin, span = min(known), max(max(known) - min(known), 10.0)
    out = []
    for i, v in enumerate(vals):
        if v is None:
            out.append(fg(62, 52, 56) + "▁")
            continue
        t = i / (n - 1)
        out.append(fg(0, lerp(150, 240, t), lerp(135, 255, t)) + SPARK[int(round((v - vmin) / span * 7))])
    return "".join(out) + RST


def projection(samples, pct, resets_at):
    """Where the window lands at reset at the pace of the last 30 minutes."""
    recent = [(t, p) for t, p in samples if NOW - t <= 1800]
    if len(recent) < 3 or not resets_at:
        return ""
    mt = sum(t for t, _ in recent) / len(recent)
    mp = sum(p for _, p in recent) / len(recent)
    var = sum((t - mt) ** 2 for t, _ in recent)
    slope = sum((t - mt) * (p - mp) for t, p in recent) / var if var else 0.0
    if slope <= 0:
        return "%s→ flat%s" % (DIM, RST)
    at_reset = pct + slope * (resets_at - NOW)
    if at_reset >= 100:
        return "%scap in %s%s" % (RED, fmt_countdown(NOW + (100 - pct) / slope), RST)
    return "%s→ %d %% at reset%s" % (AMB if at_reset >= 70 else DIM, round(at_reset), RST)


def usage_rows(data):
    rows = []
    hist = [(t, p) for t, p in (read_json(HISTORY_FILE).get("5h") or []) if NOW - t <= 3600]
    for w in usage_windows(data):
        pct, sev = w["percent"], severity(w["percent"])
        label = linked_label(USAGE_URL, w["label"], LABEL_COLOUR.get(w["label"], BLUE), ICON[w["label"]])
        row = "%s %s %s%3.0f%% %s" % (label, draw_bar(pct, sev, w["label"]), pct_colour(sev), pct, RST)
        cd = fmt_countdown(w.get("resets_at"))
        if cd:
            row += " %s↻ %s%s" % (DIM, cd, RST)
        if edition() == "tubes" and w["label"] == "5h" and hist:
            row += "  " + sparkline(hist) + "  " + projection(hist, pct, w.get("resets_at"))
        rows.append(row)
    spend = (data.get("rate_limits") or {}).get("spend_limit")
    if isinstance(spend, dict) and isinstance(spend.get("used_percentage"), (int, float)):
        u = float(spend["used_percentage"])
        sev = 2 if u >= 100 else severity(u)
        rows.append("%s %s %s%3.0f%%%s" % (bar_label("spend", AMB, icon=chr(0xF09D)), draw_bar(u, sev, None),
                                          pct_colour(sev), u, RST))
    return "\n".join(rows)


# ── chat text: user + assistant words only ─────────────────────────────────────
RE_INJECTED = re.compile(r"<(system-reminder|command-[\w-]+|local-command-[\w-]+|pasted_content[^>]*)>.*?</\1\s*>|"
                         r"<(system-reminder|command-[\w-]+|local-command-[\w-]+)>.*?(?=<|\Z)", re.S)
CHAT_KEEP = 64 * 1024
CHAT_FIRST_READ = 8 * 1024 * 1024


def session_chat_text(data, size):
    """Conversation text for this session, kept incrementally: a per-session
    cache holds the last CHAT_KEEP chars and the byte offset read so far."""
    tp = data.get("transcript_path") or ""
    if not tp or not size:
        return ""
    key = hashlib.sha1((data.get("session_id") or tp).encode()).hexdigest()[:12]
    cache_path = os.path.join(TMP, "chat-%s.json" % key)
    cache = read_json(cache_path)
    offset, text = int(cache.get("offset", 0) or 0), cache.get("text") or ""
    if cache.get("path") != tp or offset > size:
        offset, text = max(0, size - CHAT_FIRST_READ), ""
    if size > offset:
        try:
            with open(tp, "rb") as fh:
                fh.seek(offset)
                chunk = fh.read(size - offset)
        except Exception:
            return text
        end = chunk.rfind(b"\n")
        if end >= 0:
            text = (text + "\n" + chat_text(chunk[:end]))[-CHAT_KEEP:]
            offset += end + 1
            write_json(cache_path, {"path": tp, "offset": offset, "text": text})
    return text


def chat_text(blob):
    parts = []
    for line in blob.split(b"\n"):
        if b'"type":"user"' not in line and b'"type":"assistant"' not in line and \
                b'"type": "user"' not in line and b'"type": "assistant"' not in line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("type") not in ("user", "assistant") or rec.get("isMeta") or rec.get("isSidechain"):
            continue
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text") or "")
    return RE_INJECTED.sub(" ", "\n".join(parts))


RE_URL = re.compile(r"https?://github\.com/([\w.-]+)/([\w.-]+)/(issues|pull)/(\d+)")
RE_SLUG = re.compile(r"(?<![\w/.-])([\w.-]+/[\w.-]+)#(\d{1,6})(?!\w)")
RE_KIND = re.compile(r"\b(PR|Issue|Task|Epic|Ticket)\s*#(\d{1,6})(?!\w)", re.I)
RE_BARE = re.compile(r"(?<![\w/#&$\\])#(\d{1,5})(?!\w)")
KIND_NORMAL = {"pr": "PR", "issue": "Issue", "task": "Task", "epic": "Epic", "ticket": "Ticket"}
RE_ANY_URL = re.compile(r"https?://[^\s<>\"'`)\]|\x00-\x1f]+")
RE_PATH = re.compile(r"(?<![\w/.~-])((?:~|/home/[\w.-]+|/Users/[\w.-]+|/mnt/[a-z]|/tmp)(?:/[\w.@%+=,-]+)+/?)(?::(\d+))?")
READABLE = {".md", ".markdown", ".html", ".htm", ".pdf", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".svg",
            ".webp", ".heic", ".csv", ".xlsx", ".docx", ".pptx", ".key", ".mov", ".mp4"}


def extract_refs(text, default_slug):
    """-> [{slug, number, kind, url}], most recent mention first. Bare #N only
    resolves against the current repo; without one it is dropped."""
    found, masked = [], text
    for m in RE_URL.finditer(text):
        found.append((m.start(), "%s/%s" % (m.group(1), m.group(2)), int(m.group(4)), "PR" if m.group(3) == "pull" else ""))
        masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]
    for m in RE_SLUG.finditer(masked):
        found.append((m.start(), m.group(1), int(m.group(2)), ""))
        masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]
    if default_slug:
        for m in RE_KIND.finditer(masked):
            found.append((m.start(), default_slug, int(m.group(2)), KIND_NORMAL[m.group(1).lower()]))
            masked = masked[:m.start()] + " " * (m.end() - m.start()) + masked[m.end():]
        for m in RE_BARE.finditer(masked):
            found.append((m.start(), default_slug, int(m.group(1)), ""))
    found.sort(key=lambda f: -f[0])
    out, seen = [], set()
    for _, slug, num, kind in found:
        if (slug, num) in seen:
            continue
        seen.add((slug, num))
        out.append({"slug": slug, "number": num, "kind": kind,
                    "url": "https://github.com/%s/%s/%d" % (slug, "pull" if kind == "PR" else "issues", num)})
    return out


def extract_web(text, limit=MAX_LINKS):
    out, seen = [], set()
    for m in reversed(list(RE_ANY_URL.finditer(text))):
        url = m.group(0).rstrip(".,;:!?*'\"")
        if RE_URL.match(url) or url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= limit:
            break
    return out


def extract_paths(text, limit=MAX_LINKS):
    """Files meant to be read or looked at (documents, images, video), most
    recent first. No code, no config, no folders."""
    out, seen = [], set()
    for m in reversed(list(RE_PATH.finditer(text))):
        raw = m.group(1).rstrip(".,;:")
        path = pathlink.expand(raw) if pathlink else os.path.expanduser(raw)
        if path in seen:
            continue
        seen.add(path)
        if os.path.splitext(path)[1].lower() in READABLE and os.path.isfile(path):
            out.append((path, m.group(2)))
            if len(out) >= limit:
                break
    return out


HOST_KIND = (("github.com", "github"), ("supabase", "supabase"), ("vercel", "vercel"), ("v0.app", "v0"),
             ("grafana", "grafana"), ("localhost", "local"), ("127.0.0.1", "local"))


def host_kind(url):
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    for key, kind in HOST_KIND:
        if key in host:
            return kind
    return "link"


def web_label(url):
    rest = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")
    host, _, path = rest.partition("/")
    seg = path.split("/")[0] if path else ""
    return cut(host + ("/" + seg if seg and len(seg) <= 14 else ""), 32)


def web_row(text):
    urls = extract_web(text)
    chips = ["%s%s %s%s" % (DIM, ICON.get(host_kind(u), ICON["link"]), RST, osc8(u, CYN + web_label(u) + RST)) for u in urls]
    return labelled("links", MAUVE, DOT.join(chips), ICON["link"]) if chips else ""


def files_row(text):
    if not pathlink:
        return ""
    chips = []
    for path, line in extract_paths(text):
        name = os.path.basename(path) + (":" + line if line else "")
        chips.append(osc8(pathlink.link_for(path), CYN + name + RST))
    return labelled("files", MAUVE, DOT.join(chips), ICON["file"]) if chips else ""


def claude_section(data, tail, size, text):
    head = SEP.join(s for s in (osc8(USAGE_URL, safe(model_chip, data)), safe(effort_chip, data),
                                safe(advisor_chip, data, tail, size), osc8(USAGE_URL, safe(cost_chip, data)),
                                safe(guide_chip)) if s)
    return gutter("claude", [head, safe(context_gauge, data), safe(usage_rows, data), safe(web_row, text),
                             safe(files_row, text)])


# ── git (no forks on the hot path) ─────────────────────────────────────────────
def git_dirs(cwd):
    """(gitdir, commondir, toplevel, is_worktree) by reading .git -- no subprocess."""
    path = os.path.abspath(cwd)
    for _ in range(12):
        dot = os.path.join(path, ".git")
        if os.path.isdir(dot):
            return dot, dot, path, False
        if os.path.isfile(dot):
            try:
                with open(dot, "r", encoding="utf-8") as fh:
                    line = fh.read().strip()
            except OSError:
                return None
            if line.startswith("gitdir:"):
                gitdir = line[7:].strip()
                if not os.path.isabs(gitdir):
                    gitdir = os.path.normpath(os.path.join(path, gitdir))
                common = gitdir
                try:
                    with open(os.path.join(gitdir, "commondir"), "r", encoding="utf-8") as fh:
                        common = os.path.normpath(os.path.join(gitdir, fh.read().strip()))
                except OSError:
                    pass
                return gitdir, common, path, "/worktrees/" in gitdir.replace(os.sep, "/")
            return None
        parent = os.path.dirname(path)
        if parent == path:
            return None
        path = parent
    return None


def git_branch(gitdir):
    try:
        with open(os.path.join(gitdir, "HEAD"), "r", encoding="utf-8") as fh:
            head = fh.read().strip()
    except OSError:
        return ""
    if head.startswith("ref: refs/heads/"):
        return head[len("ref: refs/heads/"):]
    return head[:8] if head else ""


def git_origin(commondir):
    try:
        with open(os.path.join(commondir, "config"), "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    m = re.search(r'\[remote "origin"\](.*?)(?=\n\[|\Z)', text, re.S)
    u = re.search(r"^\s*url\s*=\s*(\S+)", m.group(1), re.M) if m else None
    return u.group(1) if u else ""


def repo_slug(url):
    if not url:
        return ""
    s = re.sub(r"^(git@[^:]+:|ssh://[^/]+/|https?://[^/]+/)", "", url)
    s = re.sub(r"\.git$", "", s).strip("/")
    return s if s.count("/") == 1 else ""


def stdin_slug(data):
    repo = (data.get("workspace") or {}).get("repo") or {}
    if not isinstance(repo, dict):
        return ""
    owner, name = repo.get("owner"), repo.get("name")
    if str(repo.get("host") or "github.com").lower() == "github.com" and owner and name:
        return "%s/%s" % (owner, name)
    return ""


def git_facts(cwd, data=None):
    dirs = git_dirs(cwd)
    if not dirs:
        return None
    gitdir, common, top, is_wt = dirs
    branch = git_branch(gitdir)
    url = git_origin(common)
    # workspace.repo is parsed from an origin remote, so a repo with NO origin
    # that sees one is seeing someone else's (the launch dir's, or one cached
    # before a `git init`); borrowing it would share that repo's cache key.
    slug = repo_slug(url) or (stdin_slug(data or {}) if url else "")
    facts = {"top": top, "branch": branch, "slug": slug, "worktree": is_wt, "name": os.path.basename(top),
             "ahead": 0, "behind": 0, "files": 0, "ins": 0, "del": 0, "area": "", "wts": []}
    key = re.sub(r"[^A-Za-z0-9._-]", "_", "%s-%s" % (slug or top, branch))
    facts["key"] = key
    cache_path = os.path.join(TMP, "git-%s.json" % key)
    cache = read_json(cache_path)
    fields = ("ahead", "behind", "files", "ins", "del", "area", "wts")
    if cache.get("at", 0) + GIT_TTL > NOW and cache.get("top") == top:
        facts.update({k: cache[k] for k in fields if k in cache})
        return facts
    try:
        out = subprocess.run(["git", "-C", top, "diff", "HEAD", "--numstat"], capture_output=True, text=True, timeout=3).stdout
        areas = {}
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            facts["files"] += 1
            facts["ins"] += int(parts[0]) if parts[0].isdigit() else 0
            facts["del"] += int(parts[1]) if parts[1].isdigit() else 0
            segs = parts[2].split("/")
            area = "/".join(segs[:2]) if len(segs) > 1 else segs[0]
            areas[area] = areas.get(area, 0) + 1
        if areas:
            facts["area"] = max(areas.items(), key=lambda kv: kv[1])[0]
    except Exception:
        pass
    try:
        out = subprocess.run(["git", "-C", top, "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                             capture_output=True, text=True, timeout=3)
        if out.returncode == 0:
            a, b = out.stdout.split()
            facts["ahead"], facts["behind"] = int(a), int(b)
    except Exception:
        pass
    wts = cache.get("wts") if cache.get("wts_at", 0) + 10 > NOW else None
    if wts is None:
        wts = safe(worktrees, top) or []
        cache["wts_at"] = NOW
    facts["wts"] = wts
    write_json(cache_path, {"at": NOW, "top": top, "wts_at": cache.get("wts_at", NOW), **{k: facts[k] for k in fields}})
    return facts


def worktrees(top):
    """[{path, branch, prunable}] from `git worktree list --porcelain`."""
    out = subprocess.run(["git", "-C", top, "worktree", "list", "--porcelain"], capture_output=True, text=True,
                         timeout=3).stdout
    wts, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                wts.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[9:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "")
        elif line.startswith("prunable"):
            cur["prunable"] = True
    return wts


def short_wt(path):
    return re.sub(r"-[0-9a-f]{6}$", "", os.path.basename(path.rstrip("/")))


# ── GitHub section ─────────────────────────────────────────────────────────────
def gh_cache(facts):
    if not facts or not facts.get("slug"):
        return {}
    base = os.path.join(TMP, facts["key"])
    cache = read_json(base + ".gh.json")
    ttl = GH_TTL_CI if ((cache.get("pr") or {}).get("ci") or {}).get("run", 0) > 0 else GH_TTL
    if NOW - (cache.get("last_attempt") or 0) >= ttl and (cache.get("backoff_until") or 0) <= NOW \
            and os.path.isfile(GH_POLLER):
        spawn_detached([sys.executable, "-B", GH_POLLER, "repo", facts["top"], base])
    return cache if cache.get("branch") in (None, facts.get("branch")) else {}


def repo_row(facts):
    if not facts:
        return ""
    parts = [osc8("https://github.com/" + facts["slug"], "%s%s%s" % (BLUE, facts["slug"], RST)) if facts["slug"]
             else "%s%s%s" % (BLUE, facts["name"], RST)]
    if facts["branch"]:
        text = facts["branch"]
        if facts["slug"]:
            text = osc8("https://github.com/%s/tree/%s" % (facts["slug"], facts["branch"]), text)
        seg = "%s%s %s%s" % (BLUE, ICON["branch"], text, RST)
        ab = ("↑%d" % facts["ahead"] if facts["ahead"] else "") + ("↓%d" % facts["behind"] if facts["behind"] else "")
        parts.append(seg + (" %s%s%s" % (AMB, ab, RST) if ab else ""))
    if facts["files"]:
        seg = "%sΔ%df%s %s+%d%s/%s−%d%s" % (AMB, facts["files"], RST, GRN, facts["ins"], RST, RED, facts["del"], RST)
        parts.append(seg + (" %s·%s%s" % (DIM, facts["area"], RST) if facts["area"] else ""))
    return labelled("repo", BLUE, SEP.join(parts), ICON["repo"])


def link_for(path):
    return pathlink.link_for(path) if pathlink else ""


def short_path(path, width=48):
    return pathlink.short(path, width) if pathlink else path


def dir_row(facts, cwd):
    """The worktree gets its own row: name, branch, and the rest of the family.
    In the main checkout the row names the agents' worktrees instead."""
    if not facts:
        return labelled("dir", DIM, "%s%s%s" % (DIM, osc8(link_for(cwd), short_path(cwd)), RST), ICON["wt"])
    wts = facts.get("wts") or []
    agents = [w for w in wts[1:] if not w.get("prunable")]
    if facts["worktree"]:
        name = osc8(link_for(facts["top"]), "%s%s%s" % (BOLD + GRN, short_wt(facts["top"]), RST))
        base = os.path.basename(wts[0]["path"]) if wts else ""
        others = len(agents) - 1
        return labelled("wt", GRN, "%s %s%s %s%s %s↳ %s%s%s" % (
            name, DIM, ICON["branch"], BLUE, facts["branch"] or "detached", DIM, base,
            ("  · %d more" % others) if others > 0 else "", RST), ICON["wt"])
    body = "%sMAIN CHECKOUT%s %s%s%s" % (RED, RST, DIM, short_path(facts["top"], 28), RST)
    if agents:
        names = [osc8(link_for(w["path"]), "%s%s%s" % (CYN, short_wt(w["path"]), RST)) for w in agents[:4]]
        more = len(agents) - len(names)
        body += "  %s%d worktrees:%s " % (DIM, len(agents), RST) + DOT.join(names) + \
            ("%s +%d%s" % (DIM, more, RST) if more > 0 else "")
    return labelled("main", RED, body, ICON["home"])


PR_STATE = {"OPEN": (GRN, "open"), "DRAFT": (DIM, "draft"), "MERGED": (MAUVE, "merged"), "CLOSED": (RED, "closed")}


def refs_cache(slug, numbers):
    path = os.path.join(REFS_DIR, slug.replace("/", "__") + ".json")
    cache = read_json(path)
    items = cache.get("items") or {}
    want = [n for n in numbers if NOW - ((items.get(str(n)) or {}).get("fetched_at") or 0) > REFS_TTL]
    if want and NOW - (cache.get("last_attempt") or 0) >= REFS_RETRY \
            and (cache.get("backoff_until") or 0) <= NOW and os.path.isfile(GH_POLLER):
        spawn_detached([sys.executable, "-B", GH_POLLER, "refs", slug, ",".join(str(n) for n in want)])
    return items


def ref_chip(r, info, default_slug, width=34):
    """#N title · state -- what the number IS, not what the chat called it."""
    num = r["number"]
    repo = "" if r["slug"] == default_slug else r["slug"].split("/")[-1] + " "
    title = cut(info.get("title") or "", width)
    url = info.get("url") or r["url"]
    kind, state = info.get("kind"), info.get("state") or ""
    if kind == "pr":
        col, word = PR_STATE.get(state, (GRN, "open"))
        return osc8(url, "%s#%d%s %s%s%s" % (col, num, RST, PAPER, repo + title, RST)) + " %s%s%s" % (col, word, RST)
    closed = state == "CLOSED"
    col = DIM if closed else (AMB if kind == "ticket" else CYN)
    chip = osc8(url, "%s#%d%s %s%s%s" % (col, num, RST, DIM if closed else PAPER, repo + title, RST))
    if kind == "ticket":
        chip += " %s▸%s " % (INK, RST) + osc8(info.get("board_url") or "", "%s%s%s" % (col, info.get("status") or "", RST))
    elif closed:
        chip += "%s closed%s" % (DIM, RST)
    return chip


def pr_body(pr):
    """The branch's own PR, from gh_poller: title, state, CI, review."""
    state = "draft" if pr.get("draft") and pr.get("state") == "OPEN" else (pr.get("state") or "").lower()
    col = GRN if state == "open" else MAUVE if state in ("merged", "closed") else AMB
    head = osc8(pr.get("url") or "", "%s#%d%s %s%s%s" % (col, pr["number"], RST, PAPER, cut(pr.get("title") or "", 40), RST))
    parts = [head + (" %s%s%s" % (col, state, RST) if state else "")]
    ci = pr.get("ci") or {}
    if ci.get("total"):
        if ci.get("fail"):
            parts.append("%s%s %d/%d%s" % (RED, ICON["fail"], ci["fail"], ci["total"], RST))
        elif ci.get("run"):
            parts.append("%s%s %d running%s" % (AMB, ICON["run"], ci["run"], RST))
        else:
            parts.append("%s%s %d/%d%s" % (GRN, ICON["ok"], ci.get("pass", 0), ci["total"], RST))
    review = (pr.get("review") or "").replace("_", " ").lower()
    if review:
        rc = GRN if review == "approved" else RED if "changes" in review else AMB
        parts.append("%s%s %s%s" % (rc, ICON["review"], review, RST))
    return DOT.join(parts)


def stdin_pr(data):
    pr = data.get("pr")
    if not isinstance(pr, dict) or not isinstance(pr.get("number"), int):
        return None
    return {"number": pr["number"], "title": "", "url": str(pr.get("url") or ""), "state": "", "draft": False,
            "review": str(pr.get("review_state") or "").upper(), "ci": {}}


def refs_rows(text, default_slug, gh=None, data=None, limit=2):
    """Three explicit rows: PR, ticket (an issue on a project board, with its
    column) and issue. The branch's own PR / ticket comes first."""
    gh = gh or {}
    here = "%s◂ this branch%s" % (GRN, RST)
    groups = {"pr": [], "ticket": [], "issue": []}
    pr = gh.get("pr") or stdin_pr(data or {})
    if pr and pr.get("number"):
        groups["pr"].append(pr_body(pr) + " " + here)
    for k in ("task", "epic"):
        t = gh.get(k)
        if t and t.get("number"):
            r = {"slug": default_slug, "number": t["number"], "url": t.get("url")}
            groups["ticket" if t.get("status") else "issue"].append(
                ref_chip(r, dict(t, kind="ticket" if t.get("status") else "issue"), default_slug) + " " + here)
    shown = {(gh.get(k) or {}).get("number") for k in ("task", "epic")} | {(pr or {}).get("number")}
    refs = extract_refs(text, default_slug)[:MAX_LINKS * 3]
    by_slug = {}
    for r in refs:
        by_slug.setdefault(r["slug"], []).append(r["number"])
    known = {slug: refs_cache(slug, nums) for slug, nums in by_slug.items()}
    for r in refs:
        info = known.get(r["slug"], {}).get(str(r["number"])) or {}
        kind = info.get("kind") or ""
        if kind in groups and not (r["slug"] == default_slug and r["number"] in shown):
            groups[kind].append(ref_chip(r, info, default_slug))
    rows = []
    for kind, label, col, icon in (("pr", "PR", GRN, ICON["pr"]), ("ticket", "ticket", AMB, ICON["board"]),
                                   ("issue", "issue", CYN, ICON["refs"])):
        if groups[kind]:
            more = len(groups[kind]) - limit
            rows.append(labelled(label, col, DOT.join(groups[kind][:limit]) +
                                 ("%s  +%d%s" % (DIM, more, RST) if more > 0 else ""), icon))
    return rows


def online_row(slug):
    """Where this repo lives online: GitHub always, the rest from config.json."""
    chips = [osc8("https://github.com/" + slug, "%s%s %sGitHub%s" % (DIM, ICON["github"], CYN, RST))]
    for e in (CONFIG.get("repos") or {}).get(slug) or []:
        if isinstance(e, dict) and e.get("url"):
            chips.append(osc8(e["url"], "%s%s %s%s%s" % (DIM, ICON.get(e.get("kind"), ICON["link"]), CYN,
                                                         e.get("label") or e["url"], RST)))
    return labelled("online", BLUE, DOT.join(chips), ICON["cloud"])


def github_section(facts, cwd, text, data):
    gh = safe(gh_cache, facts) or {}
    slug = (facts["slug"] if facts else "") or stdin_slug(data)
    rows = [safe(repo_row, facts), safe(dir_row, facts, cwd), *(safe(refs_rows, text, slug, gh, data) or [])]
    if slug:
        rows.append(safe(online_row, slug))
    return gutter("github", rows)


# ── Machine section: ports that serve a page ───────────────────────────────────
def ports_cache():
    cache = read_json(PORTS_CACHE)
    if NOW - (cache.get("last_attempt") or 0) >= PORTS_TTL and os.path.isfile(PORTS_POLLER):
        spawn_detached([sys.executable, "-B", PORTS_POLLER])
    return cache


def viewable(p):
    """ports_poller asked the listener for its front page: 2xx or 3xx is a page."""
    try:
        return 200 <= int(p.get("http") or 0) < 400
    except (TypeError, ValueError):
        return False


def mine(port, facts):
    if not facts:
        return False
    d = port.get("dir") or ""
    return bool(d and (d == facts["top"] or d.startswith(facts["top"] + os.sep)))


def ports_row(cache, facts, limit=3):
    ports = cache.get("ports") or []
    web = sorted([p for p in ports if viewable(p)], key=lambda p: (not mine(p, facts), p.get("port", 0)))
    chips = []
    for p in web[:limit]:
        svc = (p.get("service") or "").split(" ")[0].lower()[:10]
        col = GRN if mine(p, facts) else CYN
        chips.append(osc8("http://localhost:%d" % p["port"], "%s:%d%s %s%s ↗%s" % (col, p["port"], RST, DIM, svc, RST)))
    rest = len(ports) - len(chips)
    if not chips and not rest:
        return ""
    body = DOT.join(chips) + ("%s%s+%d not web%s" % (DIM, "  " if chips else "", rest, RST) if rest else "")
    return labelled("ports", TEAL, body, ICON["ports"])


def machine_section(facts):
    return gutter("machine", [safe(ports_row, safe(ports_cache) or {}, facts)])


# ── main ───────────────────────────────────────────────────────────────────────
def session_cwd(data):
    for path in (data.get("cwd"), (data.get("workspace") or {}).get("current_dir")):
        if path and os.path.isdir(path):
            return path
    return os.getcwd()


def render(data, out=sys.stdout):
    global CONFIG
    CONFIG = read_json(CONFIG_FILE)
    if pathlink:
        safe(pathlink.configure, CONFIG.get("vaults") or [])
    os.makedirs(TMP, exist_ok=True)
    cwd = session_cwd(data)
    tp = data.get("transcript_path") or ""
    tail, size = tail_bytes(tp) if tp else (b"", 0)
    text = safe(session_chat_text, data, size)
    if data.get("rate_limits"):
        safe(record_history, data)
        if read_json(RATE_LIMITS_FILE).get("rate_limits") != data["rate_limits"]:
            write_json(RATE_LIMITS_FILE, {"rate_limits": data["rate_limits"]})   # the cockpit's 5h / wk
    facts = safe(git_facts, cwd, data) or None
    rows = []
    rows += safe(claude_section, data, tail, size, text) or []
    rows += safe(github_section, facts, cwd, text, data) or []
    rows += safe(machine_section, facts) or []
    for r in rows:
        out.write(r + "\n")
    out.flush()


def main():
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    render(data)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    finally:
        try:
            sys.stdout.flush()
        except Exception:
            pass
        sys.exit(0)
