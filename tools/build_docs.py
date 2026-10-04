#!/usr/bin/env python3
"""Build docs/index.html: the one-pager.

Renders the status line from tools/fixtures.py (a made-up repo, nothing real),
in both editions, as cell data. The page draws it on a canvas the way a
terminal draws it and runs the real ghostty/neon-sumi.glsl over it in WebGL2.

    python3 tools/build_docs.py --font-dir <dir with MapleMono-NF-Regular.ttf, -Bold.ttf>

The font is subset to the glyphs the page uses (needs `pyftsubset` from
fonttools, with brotli) and embedded under the family name "NS Mono".
Maple Mono is SIL OFL 1.1.
"""
import argparse
import base64
import html
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SL = os.path.join(REPO, "plugins", "neon-sumi", "statusline")
SLUG = "Danneftw1/neon-sumi"
REPO_URL = "https://github.com/" + SLUG
SITE_URL = "https://danneftw1.github.io/neon-sumi/"
RE_TOKEN = re.compile(r"\x1b\[([0-9;:]*)m|\x1b\]8;;(.*?)\x1b\\")
sys.path.insert(0, HERE)
import fixtures  # noqa: E402


def rows_from_ansi(text):
    """-> [[{t, c, b, u, uc}]]. Link targets are dropped: the page shows cells, not URLs."""
    rows = []
    for raw in text.rstrip("\n").split("\n"):
        segs, fgc, bold, ul, ulc, pos = [], None, False, False, None, 0

        def emit(chunk):
            if chunk:
                segs.append({"t": chunk, "c": fgc, "b": bold, "u": ul, "uc": ulc})
        for m in RE_TOKEN.finditer(raw):
            emit(raw[pos:m.start()])
            pos = m.end()
            if m.group(0).startswith("\x1b]"):
                continue
            ps = re.split(r"[;:]", m.group(1)) or ["0"]
            i = 0
            while i < len(ps):
                p = ps[i] or "0"
                if p == "0":
                    fgc, bold, ul, ulc = None, False, False, None
                elif p == "1":
                    bold = True
                elif p == "4":
                    ul = True
                elif p == "24":
                    ul = False
                elif p == "59":
                    ulc = None
                elif p in ("38", "58") and i + 4 < len(ps) and ps[i + 1] == "2":
                    rgb = [int(x) for x in ps[i + 2:i + 5]]
                    if p == "38":
                        fgc = rgb
                    else:
                        ulc = rgb
                    i += 4
                i += 1
        emit(raw[pos:])
        rows.append(segs)
    return rows


def prompt_rows(width):
    ink, paper, dim = [84, 74, 70], [232, 220, 198], [146, 134, 120]
    seg = lambda t, c: {"t": t, "c": c, "b": False, "u": False, "uc": None}
    rule = [seg("─" * width, ink)]
    return [rule, [seg("> ", dim), seg("draw the tide tables as tubes, keep the ports quiet", paper)], rule, []]


NARROW = 58   # COLUMNS for the phone view: the line fits itself, the page only shows it


def env_for(root, cfg_path, columns=None):
    env = dict(os.environ, HOME=os.path.join(root, "home"), CLAUDE_CONFIG_DIR=root, NEON_SUMI_CONFIG=cfg_path,
               NEON_SUMI_TMP=os.path.join(root, "tmp"))
    env.pop("COLUMNS", None)
    if columns:
        env["COLUMNS"] = str(columns)
    return env


def render(root, payload, edition, columns=None):
    cfg_path = os.path.join(root, "config.json")
    cfg = json.load(open(cfg_path))
    cfg["edition"] = edition
    json.dump(cfg, open(cfg_path, "w"))
    with open(payload, "rb") as fh:
        out = subprocess.run([sys.executable, "-B", os.path.join(SL, "statusline.py")], stdin=fh,
                             env=env_for(root, cfg_path, columns), capture_output=True, cwd=root).stdout.decode("utf-8")
    return rows_from_ansi(out)


def cockpit(root, columns=56):
    out = subprocess.run([sys.executable, "-B", os.path.join(SL, "cockpit.py"), "--once"],
                         env=env_for(root, os.path.join(root, "config.json"), columns), capture_output=True,
                         cwd=root).stdout.decode("utf-8", "replace")
    return rows_from_ansi(re.sub(r"\x1b\[[0-9;]*[HJK]", "", out))


def subset(font_dir, chars, out_dir):
    with open(os.path.join(out_dir, "chars.txt"), "w", encoding="utf-8") as fh:
        fh.write("".join(sorted(chars)))
    fonts = {}
    for w in ("Regular", "Bold"):
        dst = os.path.join(out_dir, "%s.woff2" % w)
        subprocess.run(["pyftsubset", os.path.join(font_dir, "MapleMono-NF-%s.ttf" % w), "--text-file=" +
                        os.path.join(out_dir, "chars.txt"), "--flavor=woff2", "--layout-features=",
                        "--output-file=" + dst], check=True)
        fonts[w] = base64.b64encode(open(dst, "rb").read()).decode()
    return fonts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--font-dir", default=os.path.expanduser("~/Library/Fonts"))
    args = ap.parse_args()
    root = tempfile.mkdtemp(prefix="neon-sumi-docs-")
    payload = fixtures.build(root)
    with open(os.path.join(root, "settings.json"), "w") as fh:
        json.dump({"advisorModel": "opus"}, fh)
    tubes, classic = render(root, payload, "tubes"), render(root, payload, "classic")
    width = max(sum(len(s["t"]) for s in r) for r in tubes)
    narrow = NARROW - 2
    data = {"tubes": prompt_rows(min(width, 110)) + tubes, "classic": prompt_rows(min(width, 110)) + classic,
            "tubes_narrow": prompt_rows(narrow) + render(root, payload, "tubes", NARROW),
            "classic_narrow": prompt_rows(narrow) + render(root, payload, "classic", NARROW),
            "cockpit": cockpit(root)}
    shader = open(os.path.join(SL, "ghostty", "neon-sumi.glsl"), encoding="utf-8").read()
    page = TEMPLATE.replace("__ROWS__", json.dumps(data, ensure_ascii=False)).replace("__SHADER__", shader)
    page = page.replace("__SITE__", SITE_URL).replace("__REPO__", REPO_URL).replace("__SLUG__", SLUG)
    chars = set(re.sub(r"<[^>]+>", "", page)) | set(chr(c) for c in range(32, 127))
    for rows in data.values():
        for r in rows:
            for s in r:
                chars |= set(s["t"])
    fonts = subset(args.font_dir, chars, root)
    page = page.replace("__NS_REGULAR__", fonts["Regular"]).replace("__NS_BOLD__", fonts["Bold"])
    os.makedirs(os.path.join(REPO, "docs"), exist_ok=True)
    with open(os.path.join(REPO, "docs", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    print("docs/index.html", len(page), "bytes")


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Neon Sumi</title>
<meta name="description" content="A status line for Claude Code that tells you where you stand: context, limits, the PR, the ports that are up. Free and open source.">
<link rel="canonical" href="__SITE__">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Neon Sumi">
<meta property="og:title" content="Neon Sumi, a status line for Claude Code">
<meta property="og:description" content="Context, limits, the PR, the ports that are up. One glance below the prompt. Free and open source.">
<meta property="og:url" content="__SITE__">
<meta property="og:image" content="__SITE__og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Neon Sumi: a Claude Code status line lit in neon on an ink-black terminal">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="__SITE__og.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
@font-face { font-family: "NS Mono"; src: url(data:font/woff2;base64,__NS_REGULAR__) format("woff2"); font-weight: 400; }
@font-face { font-family: "NS Mono"; src: url(data:font/woff2;base64,__NS_BOLD__) format("woff2"); font-weight: 700; }
:root {
  color-scheme: dark;
  --deep: #0b090a; --sumi: #0f0c0d; --sumi-hi: #131011; --line: #2c2426; --ink: #544a46; --stone: #928678;
  --soft: #cbbfa9; --paper: #e8dcc6; --bright: #f7efe2; --magenta: #ff2ec4; --violet: #c46eff; --teal: #00ffcc;
  --mono: "NS Mono", ui-monospace, Menlo, monospace;
  --sans: "Zen Kaku Gothic New", "Hiragino Sans", system-ui, sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: var(--sumi); color: var(--paper); font-family: var(--sans); font-size: 16px; line-height: 1.6; }
.wrap { max-width: 1240px; margin: 0 auto; padding-inline: 20px; padding-block: 48px 64px; display: grid; gap: 40px; }
.wrap > *, section > *, header > * { min-width: 0; }
header { display: grid; gap: 12px; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; color: var(--stone); text-transform: uppercase; }
.eyebrow b { color: var(--magenta); font-weight: 400; }
h1 { font-size: clamp(38px, 7vw, 66px); line-height: 1.02; margin: 0; font-weight: 700; }
h1 em { font-style: normal; color: var(--magenta); text-shadow: 0 0 22px rgba(255,46,196,.55), 0 0 4px rgba(255,46,196,.5); }
.lede { max-width: 64ch; color: var(--stone); margin: 0; } .lede b { color: var(--paper); font-weight: 500; }
.facts { display: flex; flex-wrap: wrap; gap: 8px; margin: 0; padding: 0; list-style: none; font-family: var(--mono); font-size: 12px; }
.facts li { border: 1px solid var(--line); border-radius: 999px; padding: 3px 10px; color: var(--soft); }
.cmd { position: relative; max-width: 760px; }
pre { margin: 0; font-family: var(--mono); font-size: 13.5px; line-height: 1.6; background: var(--deep); border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 14px; color: var(--paper); white-space: pre-wrap; overflow-wrap: anywhere; }
pre .c { color: var(--stone); }
.copy { position: absolute; bottom: 9px; right: 9px; font-family: var(--mono); font-size: 13px; color: var(--sumi); background: var(--magenta);
  border: 1px solid var(--magenta); border-radius: 8px; padding: 4px 12px; min-height: 28px; cursor: pointer; box-shadow: 0 0 18px rgba(255,46,196,.45); }
.copy:hover { box-shadow: 0 0 26px rgba(255,46,196,.7); } .copy:focus-visible { outline: 2px solid var(--teal); outline-offset: 2px; }
.small { font-size: 14px; color: var(--stone); margin: 0; max-width: 76ch; }
code { font-family: var(--mono); font-size: .9em; color: var(--paper); }
.cta { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.btn { font-family: var(--mono); font-size: 13px; text-decoration: none; border-radius: 8px; padding: 8px 14px; border: 1px solid var(--line); color: var(--paper); }
.btn:hover { border-color: var(--stone); }
.stage { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: var(--sumi);
  box-shadow: 0 0 0 1px rgba(255,46,196,.14), 0 40px 90px -40px rgba(255,46,196,.45); }
.bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 14px; border-bottom: 1px solid var(--line);
  background: var(--sumi-hi); font-family: var(--mono); font-size: 12px; color: var(--stone); flex-wrap: wrap; }
.dots { display: inline-flex; gap: 6px; } .dots i { width: 10px; height: 10px; border-radius: 50%; background: var(--line); display: block; }
.toggle { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.toggle button { font: inherit; color: var(--stone); background: transparent; border: 0; padding: 5px 12px; min-height: 28px; cursor: pointer; }
.toggle button[aria-pressed="true"] { color: var(--sumi); background: var(--magenta); box-shadow: 0 0 14px rgba(255,46,196,.6); }
.toggle button:focus-visible { outline: 2px solid var(--teal); outline-offset: -2px; }
.canvasbox { position: relative; }
canvas { display: block; width: 100%; height: auto; }
.pin { position: absolute; width: 18px; height: 18px; margin: -9px 0 0 -9px; border-radius: 50%; background: var(--bright); color: var(--sumi);
  font: 700 10.5px/18px var(--mono); text-align: center; box-shadow: 0 0 0 2px var(--magenta), 0 0 10px rgba(255,46,196,.5); pointer-events: none; }
.status { padding: 8px 14px; font-family: var(--mono); font-size: 12px; color: var(--stone); border-top: 1px solid var(--line); }
.legend { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px 28px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); }
.legend li { display: grid; grid-template-columns: 26px 1fr; gap: 10px; align-items: start; color: var(--soft); font-size: 15px; }
.legend i { font: 700 10.5px/18px var(--mono); font-style: normal; width: 18px; height: 18px; margin-top: 3px; border-radius: 50%; text-align: center;
  background: var(--bright); color: var(--sumi); box-shadow: 0 0 0 2px var(--magenta); }
section { display: grid; gap: 14px; }
h2 { font-size: clamp(22px, 3vw, 28px); line-height: 1.2; margin: 0; font-weight: 700; }
.tiles { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
.tile { margin: 0; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: var(--sumi-hi); display: grid; align-content: start; }
.tile img, .tile canvas { display: block; width: 100%; height: auto; background: var(--sumi); }
@media (min-width: 761px) {
  .tile img, .tile canvas { aspect-ratio: 8 / 5; object-fit: cover; object-position: center top; }
  .tile canvas { object-position: left top; -webkit-mask-image: linear-gradient(#000 72%, transparent); mask-image: linear-gradient(#000 72%, transparent); }
}
.tile figcaption { padding: 12px 16px 14px; color: var(--soft); font-size: 15px; border-top: 1px solid var(--line); }
.tile figcaption b { color: var(--paper); font-weight: 700; }
footer { font-family: var(--mono); font-size: 12px; color: var(--stone); letter-spacing: .03em; border-top: 1px solid var(--line); padding-top: 14px; }
footer a { color: var(--stone); text-decoration-color: rgba(255,46,196,.6); text-underline-offset: 3px; display: inline-block; padding: 4px 0; }
a:focus-visible { outline: 2px solid var(--magenta); outline-offset: 2px; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="eyebrow">A status line for Claude Code</div>
  <h1>Neon Sumi, <em>lit</em></h1>
  <p class="lede">Context left, the 5-hour and weekly limits, the branch and its PR, the dev server that is actually up. <b>One glance below the prompt,</b> so you don't have to ask.</p>
  <ul class="facts"><li>free · MIT</li><li>Python standard library only</li><li>~25 ms per render</li><li>no network on the render path</li><li>no telemetry</li><li>fits any width</li></ul>
  <div class="cmd" id="install">
<pre id="cmds"><span class="c"># in Claude Code: add the marketplace, install, let the skill wire it up</span>
/plugin marketplace add __SLUG__
/plugin install neon-sumi@neon-sumi
/neon-sumi:install</pre>
    <button type="button" class="copy" id="copy" aria-label="Copy the install commands">copy</button>
  </div>
  <p class="small">The last step copies the files to <code>~/.claude/neon-sumi/</code>, renders once, and asks before it touches <code>settings.json</code> (with a backup). Needs Python 3.9+, a Nerd Font and <code>git</code>; <code>gh</code> lights up the GitHub rows.</p>
  <div class="cta"><a class="btn" href="__REPO__">Source on GitHub</a></div>
</header>

<div>
<div class="stage" id="stage">
  <div class="bar"><span class="dots"><i></i><i></i><i></i></span><span id="cap">ghostty · neon-sumi.glsl · live</span>
    <span class="toggle" role="group" aria-label="Edition">
      <button type="button" id="b-lit" aria-pressed="true">Ghostty</button><button type="button" id="b-flat" aria-pressed="false">Any terminal</button>
    </span></div>
  <div class="canvasbox" id="box"><canvas id="lit" aria-label="The Neon Sumi status line, rendered from a made-up repo"></canvas></div>
  <div class="status" id="st">loading…</div>
</div>
</div>

<ol class="legend" aria-label="What the numbers point at">
  <li><i>1</i><span>Context, 5-hour and weekly use. Cool at rest, amber at 70 %, red at 85 %.</span></li>
  <li id="lg2"><i>2</i><span>Where the 5-hour window lands at reset, at the current pace.</span></li>
  <li><i>3</i><span>Links and readable files from the chat, clickable.</span></li>
  <li><i>4</i><span>Branch, diff and worktree, then every PR, ticket and issue mentioned, with its title and state.</span></li>
  <li><i>5</i><span>Dev servers that actually serve a page.</span></li>
</ol>

<section id="more">
  <h2>Also in the box</h2>
  <div class="tiles">
    <figure class="tile"><canvas id="ck" aria-label="The cockpit, one frame"></canvas><figcaption><b>The cockpit</b> · what is the same in every session, for a split pane: your PRs, the inbox, every port by owner.</figcaption></figure>
    <figure class="tile"><img src="obsidian.png" width="1800" height="1157" loading="lazy" alt="The Obsidian theme: neon headings and links on an ink-black note"><figcaption><b>Obsidian</b> · the same palette for your notes, and a profile for the Terminal plugin.</figcaption></figure>
    <figure class="tile"><img src="themes.png" width="1600" height="950" loading="lazy" alt="A terminal in the Neon Sumi palette, with the sixteen colours along the bottom"><figcaption><b>Matching themes</b> · Ghostty, iTerm2, Zed and Claude Code's own <code>/theme</code>, from one token file.</figcaption></figure>
  </div>
</section>

<footer><b style="color:var(--magenta);font-weight:400">Neon Sumi</b> · MIT · <a href="__REPO__">source, issues and docs on GitHub</a> · typeset in Maple Mono (SIL OFL 1.1) · icons from Nerd Fonts</footer>
</div>

<script>
document.getElementById("copy").addEventListener("click", function () {
  const b = this, text = document.getElementById("cmds").textContent.split("\n").filter(l => l.startsWith("/")).join("\n");
  navigator.clipboard.writeText(text).then(() => { b.textContent = "copied"; setTimeout(() => { b.textContent = "copy"; }, 1600); },
    () => { b.textContent = "select and copy"; });
});
</script>
<script id="shader-body" type="x-shader/x-fragment">__SHADER__</script>
<script>
(function () {
  const DATA = __ROWS__;
  const DPR = 2, FS = 14 * DPR, LH = Math.round(FS * 1.45), PADL = 40 * DPR, PADR = 16 * DPR, PADY = 12 * DPR;
  const BG = [15, 12, 13], CURSOR = [255, 46, 196];
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const narrowQ = window.matchMedia("(max-width: 760px)");
  const st = document.getElementById("st"), lit = document.getElementById("lit"), box = document.getElementById("box");
  const src = document.createElement("canvas");
  let edition = "tubes", shaderOn = true, cw = 0;
  const PROMPT_ROW = 1, STOPS = [53, 2, 30, 53];
  // pins: [number, row, column] -- row counts the four prompt rows; column -1 is the left margin
  const PINS = [[1, 6, -1], [2, 6, 79], [3, 8, -1], [4, 12, -1], [5, 16, -1]];
  let stop = 0, curCol = STOPS[0], prevCol = STOPS[0], changedAt = -10;
  const rgb = (c, a) => "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + (a == null ? 1 : a) + ")";
  const narrow = () => narrowQ.matches;
  const rowsFor = () => DATA[edition + (narrow() ? "_narrow" : "")];
  const width = rows => Math.max(...rows.map(r => r.reduce((n, s) => n + Array.from(s.t).length, 0)));

  // Terminals like Ghostty draw these as sprites instead of font glyphs.
  function sprite(g, ch, x, y, color) {
    g.fillStyle = color;
    const heavy = Math.max(3, Math.round(LH * 0.11)), light = Math.max(2, Math.round(LH * 0.045)), mid = y + LH / 2;
    const up = "▁▂▃▄▅▆▇█".indexOf(ch);
    if (ch === "━") { g.fillRect(x, mid - heavy / 2, cw + 0.5, heavy); return true; }
    if (ch === "─") { g.fillRect(x, mid - light / 2, cw + 0.5, light); return true; }
    if (ch === "╸") { g.fillRect(x, mid - heavy / 2, cw / 2, heavy); g.fillRect(x + cw / 2, mid - light / 2, cw / 2 + 0.5, light); return true; }
    if (ch === "▎") { g.fillRect(x, y, cw / 4, LH + 0.5); return true; }
    if (ch === "│") { g.fillRect(x + cw / 2 - light / 2, y, light, LH + 0.5); return true; }
    if (up >= 0) { const h = LH * (up + 1) / 8; g.fillRect(x + 1, y + LH - h, cw - 2, h); return true; }
    return false;
  }

  function paint(canvas, rows, cols, padL) {
    const g = canvas.getContext("2d");
    g.font = "400 " + FS + 'px "NS Mono", monospace';
    cw = g.measureText("M").width;
    canvas.width = Math.ceil(padL + PADR + cols * cw);
    canvas.height = Math.ceil(PADY * 2 + rows.length * LH);
    g.fillStyle = rgb(BG); g.fillRect(0, 0, canvas.width, canvas.height);
    rows.forEach(function (row, r) {
      let col = 0; const y = PADY + r * LH, base = y + Math.round(LH * 0.72);
      row.forEach(function (s) {
        const color = rgb(s.c || [232, 220, 198]);
        g.font = (s.b ? "700 " : "400 ") + FS + 'px "NS Mono", monospace';
        Array.from(s.t).forEach(function (ch) {
          const x = padL + col * cw;
          if (!sprite(g, ch, x, y, color) && ch !== " ") { g.fillStyle = color; g.fillText(ch, x, base); }
          if (s.u) { g.fillStyle = rgb(s.uc || s.c || [232, 220, 198]); g.fillRect(x, base + 3 * DPR, cw + 0.5, DPR); }
          col++;
        });
      });
    });
    return g;
  }

  function draw() {
    const rows = rowsFor();
    const g = paint(src, rows, width(narrow() ? rows : DATA.tubes), PADL);
    g.fillStyle = rgb(CURSOR);
    g.fillRect(PADL + curCol * cw, PADY + PROMPT_ROW * LH + LH * 0.1, 2 * DPR, LH * 0.8);
  }

  function pins() {
    box.querySelectorAll(".pin").forEach(p => p.remove());
    const k = lit.clientWidth / src.width, rows = rowsFor();
    document.getElementById("lg2").hidden = narrow();
    PINS.forEach(function ([n, row, col]) {
      if (row >= rows.length || (narrow() && col >= 0)) return;
      const p = document.createElement("span"); p.className = "pin"; p.textContent = n;
      p.style.left = ((col < 0 ? PADL / 2 : PADL + (col + 0.5) * cw) * k) + "px";
      p.style.top = ((PADY + (row + 0.5) * LH) * k) + "px";
      box.appendChild(p);
    });
  }

  function webgl() {
    const gl = lit.getContext("webgl2", { premultipliedAlpha: false, antialias: false, preserveDrawingBuffer: true });
    if (!gl) return null;
    const vs = "#version 300 es\nin vec2 p;\nvoid main(){ gl_Position = vec4(p, 0.0, 1.0); }";
    const fs = "#version 300 es\nprecision highp float;\nprecision highp int;\n" +
      "uniform vec3 iResolution; uniform float iTime; uniform sampler2D iChannel0; uniform vec3 iBackgroundColor;\n" +
      "uniform vec4 iCurrentCursor; uniform vec4 iPreviousCursor; uniform vec4 iCurrentCursorColor; uniform float iTimeCursorChange;\n" +
      "uniform float uOn;\nout vec4 _fragColor;\n" + document.getElementById("shader-body").textContent +
      "\nvoid main(){ vec2 uv = gl_FragCoord.xy / iResolution.xy; if (uOn < 0.5) { _fragColor = texture(iChannel0, uv); return; }" +
      " mainImage(_fragColor, gl_FragCoord.xy); }\n";
    function sh(type, code) {
      const s = gl.createShader(type); gl.shaderSource(s, code); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    }
    const prog = gl.createProgram();
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(prog);
    gl.useProgram(prog);
    const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    const tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
    [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER].forEach(k => gl.texParameteri(gl.TEXTURE_2D, k, gl.LINEAR));
    [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T].forEach(k => gl.texParameteri(gl.TEXTURE_2D, k, gl.CLAMP_TO_EDGE));
    const U = n => gl.getUniformLocation(prog, n);
    return {
      upload: function () { gl.bindTexture(gl.TEXTURE_2D, tex); gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src); },
      frame: function (t) {
        lit.width = src.width; lit.height = src.height; gl.viewport(0, 0, lit.width, lit.height);
        gl.uniform3f(U("iResolution"), lit.width, lit.height, 1); gl.uniform1f(U("iTime"), t); gl.uniform1i(U("iChannel0"), 0);
        gl.uniform1f(U("uOn"), shaderOn ? 1 : 0);
        gl.uniform3f(U("iBackgroundColor"), BG[0] / 255, BG[1] / 255, BG[2] / 255);
        const top = lit.height - (PADY + PROMPT_ROW * LH + LH * 0.1), h = LH * 0.8, w = 2 * DPR;
        gl.uniform4f(U("iCurrentCursor"), PADL + curCol * cw, top, w, h);
        gl.uniform4f(U("iPreviousCursor"), PADL + prevCol * cw, top, w, h);
        gl.uniform4f(U("iCurrentCursorColor"), CURSOR[0] / 255, CURSOR[1] / 255, CURSOR[2] / 255, 1);
        gl.uniform1f(U("iTimeCursorChange"), changedAt);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      }
    };
  }

  document.fonts.load("400 " + FS + 'px "NS Mono"').then(() => document.fonts.load("700 " + FS + 'px "NS Mono"')).then(function () {
    paint(document.getElementById("ck"), DATA.cockpit, width(DATA.cockpit), PADR);
    draw();
    let r = null;
    try { r = webgl(); } catch (e) { r = null; st.textContent = "shader did not compile: " + e.message; }
    const note = () => narrow() ? "the same line at " + (width(rowsFor()) | 0) + " columns: it fits itself to the pane" : null;
    if (!r) {
      const c = lit.getContext("2d");
      const flat = () => { draw(); lit.width = src.width; lit.height = src.height; c.drawImage(src, 0, 0); pins(); };
      flat(); narrowQ.addEventListener("change", flat); window.addEventListener("resize", pins);
      if (!st.textContent.startsWith("shader")) st.textContent = note() || "WebGL2 is off in this browser: showing the flat status line";
      return;
    }
    r.upload();
    function pick(lit_) {
      edition = lit_ ? "tubes" : "classic"; shaderOn = lit_;
      document.getElementById("b-lit").setAttribute("aria-pressed", lit_);
      document.getElementById("b-flat").setAttribute("aria-pressed", !lit_);
      document.getElementById("cap").textContent = lit_ ? "ghostty · neon-sumi.glsl · live" : "iTerm2, Terminal, Windows Terminal · no shader";
      draw(); r.upload(); r.frame(performance.now() / 1000); pins();
    }
    document.getElementById("b-lit").addEventListener("click", () => pick(true));
    document.getElementById("b-flat").addEventListener("click", () => pick(false));
    narrowQ.addEventListener("change", () => pick(shaderOn));
    window.addEventListener("resize", pins);
    const t0 = performance.now();
    if (reduce) { r.frame(1.2); pins(); st.textContent = note() || "still frame · reduced motion is on"; return; }
    r.frame(0); pins();
    st.textContent = note() || "live · the cursor on the prompt shows the comet";
    let visible = true, last = 0;
    new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) requestAnimationFrame(loop); }).observe(lit);
    function loop(now) {
      if (!visible) return;
      const t = (now - t0) / 1000;
      if (t - last > 1.6) { last = t; prevCol = curCol; stop = (stop + 1) % STOPS.length; curCol = STOPS[stop]; changedAt = t; draw(); r.upload(); }
      r.frame(t);
      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
  });
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
