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
SLUG = "Danneftw1/nami-sumi-cc-statusline"
REPO_URL = "https://github.com/" + SLUG
SITE_URL = "https://danneftw1.github.io/nami-sumi-cc-statusline/"
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


def render(root, payload, edition):
    cfg_path = os.path.join(root, "config.json")
    cfg = json.load(open(cfg_path))
    cfg["edition"] = edition
    json.dump(cfg, open(cfg_path, "w"))
    env = dict(os.environ, HOME=os.path.join(root, "home"), CLAUDE_CONFIG_DIR=root, NEON_SUMI_CONFIG=cfg_path,
               NEON_SUMI_TMP=os.path.join(root, "tmp"))
    with open(payload, "rb") as fh:
        out = subprocess.run([sys.executable, "-B", os.path.join(SL, "statusline.py")], stdin=fh, env=env,
                             capture_output=True, cwd=root).stdout.decode("utf-8")
    return rows_from_ansi(out)


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
    data = {"tubes": prompt_rows(min(width, 110)) + tubes, "classic": prompt_rows(min(width, 110)) + classic}
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
<meta property="og:title" content="Neon Sumi, a status line for Claude Code">
<meta property="og:description" content="Context, limits, the PR, the ports that are up. One glance below the prompt. Free and open source.">
<meta property="og:url" content="__SITE__">
<meta property="og:image" content="__SITE__neon-sumi.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
@font-face { font-family: "NS Mono"; src: url(data:font/woff2;base64,__NS_REGULAR__) format("woff2"); font-weight: 400; }
@font-face { font-family: "NS Mono"; src: url(data:font/woff2;base64,__NS_BOLD__) format("woff2"); font-weight: 700; }
:root {
  color-scheme: dark;
  --sumi: #0f0c0d; --line: #2c2426; --ink: #544a46; --stone: #928678; --paper: #e8dcc6; --soft: #cbbfa9;
  --magenta: #ff2ec4; --teal: #00ffcc;
  --mono: "NS Mono", ui-monospace, Menlo, monospace;
  --sans: "Zen Kaku Gothic New", "Hiragino Sans", system-ui, sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: var(--sumi); color: var(--paper); font-family: var(--sans); font-size: 16px; line-height: 1.6; }
.wrap { max-width: 1240px; margin: 0 auto; padding-inline: 20px; padding-block: 48px 64px; display: grid; gap: 40px; }
header { display: grid; gap: 10px; }
.eyebrow { font-family: var(--mono); font-size: 12px; letter-spacing: .08em; color: var(--stone); text-transform: uppercase; }
h1 { font-size: clamp(38px, 7vw, 66px); line-height: 1.02; margin: 0; font-weight: 700; }
h1 em { font-style: normal; color: var(--magenta); text-shadow: 0 0 22px rgba(255,46,196,.55), 0 0 4px rgba(255,46,196,.5); }
.lede { max-width: 64ch; color: var(--stone); margin: 0; } .lede b { color: var(--paper); font-weight: 500; }
.stage { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; background: #0f0c0d;
  box-shadow: 0 0 0 1px rgba(255,46,196,.14), 0 40px 90px -40px rgba(255,46,196,.45); }
.bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 14px; border-bottom: 1px solid var(--line);
  background: #120f10; font-family: var(--mono); font-size: 12px; color: var(--stone); flex-wrap: wrap; }
.dots { display: inline-flex; gap: 6px; } .dots i { width: 10px; height: 10px; border-radius: 50%; background: var(--line); display: block; }
.toggle { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.toggle button { font: inherit; color: var(--stone); background: transparent; border: 0; padding: 5px 12px; cursor: pointer; }
.toggle button[aria-pressed="true"] { color: var(--sumi); background: var(--magenta); box-shadow: 0 0 14px rgba(255,46,196,.6); }
.toggle button:focus-visible { outline: 2px solid var(--teal); outline-offset: -2px; }
.canvasbox { overflow-x: auto; }
canvas { display: block; width: 100%; min-width: 760px; height: auto; }
.status { padding: 8px 14px; font-family: var(--mono); font-size: 12px; color: var(--stone); border-top: 1px solid var(--line); }
.facts { display: flex; flex-wrap: wrap; gap: 8px; margin: 4px 0 0; padding: 0; list-style: none; font-family: var(--mono); font-size: 12px; }
.facts li { border: 1px solid var(--line); border-radius: 999px; padding: 3px 10px; color: var(--soft); }
.cta { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-top: 6px; }
.btn { font-family: var(--mono); font-size: 13px; text-decoration: none; border-radius: 8px; padding: 8px 14px; border: 1px solid var(--line); color: var(--paper); }
.btn.primary { color: var(--sumi); background: var(--magenta); border-color: var(--magenta); box-shadow: 0 0 18px rgba(255,46,196,.45); }
.btn:hover { border-color: var(--stone); } .btn.primary:hover { box-shadow: 0 0 26px rgba(255,46,196,.7); }
section { display: grid; gap: 14px; }
h2 { font-size: clamp(22px, 3vw, 28px); line-height: 1.2; margin: 0; font-weight: 700; }
h3 { font-size: 16px; margin: 0; font-weight: 700; color: var(--paper); }
.sub { margin: 0; color: var(--stone); max-width: 64ch; }
.grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.card { border: 1px solid var(--line); border-radius: 10px; padding: 16px 18px; background: #120f10; display: grid; gap: 6px; align-content: start; }
.card p { margin: 0; color: var(--soft); font-size: 15px; }
.card .k { font-family: var(--mono); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--teal); }
code { font-family: var(--mono); font-size: .9em; color: var(--paper); }
.install { max-width: 760px; }
.cmd { position: relative; }
.copy { position: absolute; top: 8px; right: 8px; font-family: var(--mono); font-size: 12px; color: var(--stone); background: #120f10;
  border: 1px solid var(--line); border-radius: 6px; padding: 3px 9px; cursor: pointer; }
.copy:hover { color: var(--paper); } .copy:focus-visible { outline: 2px solid var(--teal); outline-offset: 1px; }
pre { margin: 0; font-family: var(--mono); font-size: 13.5px; line-height: 1.6; background: #0b090a; border: 1px solid var(--line);
  border-radius: 8px; padding: 12px 14px; overflow: auto; color: var(--paper); }
pre .c { color: var(--ink); }
.small { font-size: 14px; color: var(--stone); margin: 0; }
footer { font-family: var(--mono); font-size: 12px; color: var(--stone); letter-spacing: .03em; border-top: 1px solid var(--line); padding-top: 18px; }
footer a { color: var(--stone); text-decoration-color: rgba(255,46,196,.6); text-underline-offset: 3px; }
a:focus-visible { outline: 2px solid var(--magenta); outline-offset: 2px; }
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="eyebrow">A status line for Claude Code</div>
  <h1>Neon Sumi, <em>lit</em></h1>
  <p class="lede">Context left, the 5-hour and weekly limits, the branch and its PR, the dev server that is actually up. <b>One glance below the prompt,</b> so you don't have to ask.</p>
  <ul class="facts"><li>free · MIT</li><li>Python standard library only</li><li>~25 ms per render</li><li>no telemetry</li></ul>
  <div class="cta"><a class="btn primary" href="#install">Install in three commands</a><a class="btn" href="__REPO__">Source on GitHub</a></div>
</header>

<div class="stage" id="stage">
  <div class="bar"><span class="dots"><i></i><i></i><i></i></span><span id="cap">ghostty · neon-sumi.glsl · live</span>
    <span class="toggle" role="group" aria-label="Edition">
      <button type="button" id="b-lit" aria-pressed="true">Ghostty</button><button type="button" id="b-flat" aria-pressed="false">Any terminal</button>
    </span></div>
  <div class="canvasbox"><canvas id="lit" aria-label="Neon Sumi status line"></canvas></div>
  <div class="status" id="st">loading…</div>
</div>

<p class="small">Above: the real status line, rendered from a made-up repo, with the real Ghostty shader running over it in your browser. The repo, tickets and ports are invented.</p>

<section>
  <h2>Why you might want it</h2>
  <div class="grid">
    <div class="card"><h3>You stop asking</h3><p>How much context is left, whether CI passed, which port the app is on. The answers are already on screen, refreshed every second.</p></div>
    <div class="card"><h3>It stays out of the way</h3><p>One Python process per render, about 25 ms. Nothing on the render path touches the network: GitHub and ports are collected in the background and shared by every open session.</p></div>
    <div class="card"><h3>Colour means something</h3><p>Neon only for what is live: fills, percentages, state, links. Everything static is ink and paper. Bars turn amber at 70 % and red at 85 %.</p></div>
    <div class="card"><h3>Nothing to take on trust</h3><p>No pip install, no account, no telemetry. It talks to your own <code>localhost</code> and, through your own <code>gh</code>, to GitHub. About 2,000 lines you can read in an afternoon.</p></div>
  </div>
</section>

<section>
  <h2>What it shows</h2>
  <div class="grid">
    <div class="card"><span class="k">Claude</span><p>Model, effort, advisor, session cost. Context, 5-hour and weekly usage as three bars. Links and readable files from the conversation, as clickable chips.</p></div>
    <div class="card"><span class="k">GitHub</span><p>Branch, ahead/behind, the uncommitted diff, your worktrees. The branch's PR with CI and review state, then every PR, ticket and issue mentioned in the chat, with its title and state.</p></div>
    <div class="card"><span class="k">Machine</span><p>Local ports that actually serve a page, as links. Ports that only answer with an error are counted, not linked.</p></div>
  </div>
</section>

<section>
  <h2>Also in the box</h2>
  <div class="grid">
    <div class="card"><h3>The cockpit</h3><p>Everything that is the same in every session, in a narrow split pane: the skills Claude loaded this week, all your open PRs, the GitHub inbox, every port by owner, your boards. Each block says how old its data is.</p></div>
    <div class="card"><h3>Ghostty edition</h3><p>Bars drawn as tubes, a sparkline of the last hour, and where you will land at reset at the current pace. Plus the shader you see above. Every other terminal gets the classic edition.</p></div>
    <div class="card"><h3>Obsidian theme</h3><p>A matching theme and a Terminal plugin profile, so a terminal inside Obsidian gets the same colours.</p></div>
  </div>
</section>

<section class="install" id="install">
  <h2>Install, from inside Claude Code</h2>
  <div class="cmd">
<pre id="cmds"><span class="c"># add the marketplace, install, then let the skill wire it up</span>
/plugin marketplace add __SLUG__
/plugin install neon-sumi@neon-sumi
/neon-sumi:install</pre>
    <button type="button" class="copy" id="copy" aria-label="Copy the install commands">copy</button>
  </div>
  <p class="small">The last step copies the files to <code>~/.claude/neon-sumi/</code>, renders once so you can see it works, and asks before it touches <code>settings.json</code>. It keeps a backup. Needs Python 3.9+, a Nerd Font and <code>git</code>; <code>gh</code> is optional and lights up the GitHub rows.</p>
</section>

<footer>MIT · <a href="__REPO__">source, issues and docs on GitHub</a> · typeset in Maple Mono (SIL OFL 1.1) · icons from Nerd Fonts</footer>
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
  const DPR = 2, FS = 14 * DPR, LH = Math.round(FS * 1.45), PADX = 16 * DPR, PADY = 12 * DPR;
  const BG = [15, 12, 13], CURSOR = [255, 46, 196];
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const st = document.getElementById("st"), lit = document.getElementById("lit");
  const src = document.createElement("canvas");
  let edition = "tubes", shaderOn = true, cw = 0;
  const PROMPT_ROW = 1, STOPS = [53, 2, 30, 53];
  let stop = 0, curCol = STOPS[0], prevCol = STOPS[0], changedAt = -10;
  const rgb = (c, a) => "rgba(" + c[0] + "," + c[1] + "," + c[2] + "," + (a == null ? 1 : a) + ")";

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

  function draw() {
    const rows = DATA[edition];
    const cols = Math.max(...DATA.tubes.map(r => r.reduce((n, s) => n + Array.from(s.t).length, 0)));
    const g = src.getContext("2d");
    g.font = "400 " + FS + 'px "NS Mono", monospace';
    cw = g.measureText("M").width;
    src.width = Math.ceil(PADX * 2 + cols * cw);
    src.height = Math.ceil(PADY * 2 + rows.length * LH);
    g.fillStyle = rgb(BG); g.fillRect(0, 0, src.width, src.height);
    rows.forEach(function (row, r) {
      let col = 0; const y = PADY + r * LH, base = y + Math.round(LH * 0.72);
      row.forEach(function (s) {
        const color = rgb(s.c || [232, 220, 198]);
        g.font = (s.b ? "700 " : "400 ") + FS + 'px "NS Mono", monospace';
        Array.from(s.t).forEach(function (ch) {
          const x = PADX + col * cw;
          if (!sprite(g, ch, x, y, color) && ch !== " ") { g.fillStyle = color; g.fillText(ch, x, base); }
          if (s.u) { g.fillStyle = rgb(s.uc || s.c || [232, 220, 198]); g.fillRect(x, base + 3 * DPR, cw + 0.5, DPR); }
          col++;
        });
      });
    });
    g.fillStyle = rgb(CURSOR);
    g.fillRect(PADX + curCol * cw, PADY + PROMPT_ROW * LH + LH * 0.1, 2 * DPR, LH * 0.8);
  }

  function flat() {
    lit.width = src.width; lit.height = src.height;
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
        gl.uniform4f(U("iCurrentCursor"), PADX + curCol * cw, top, w, h);
        gl.uniform4f(U("iPreviousCursor"), PADX + prevCol * cw, top, w, h);
        gl.uniform4f(U("iCurrentCursorColor"), CURSOR[0] / 255, CURSOR[1] / 255, CURSOR[2] / 255, 1);
        gl.uniform1f(U("iTimeCursorChange"), changedAt);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      }
    };
  }

  document.fonts.load("400 " + FS + 'px "NS Mono"').then(() => document.fonts.load("700 " + FS + 'px "NS Mono"')).then(function () {
    draw();
    let r = null;
    try { r = webgl(); } catch (e) { r = null; st.textContent = "shader did not compile: " + e.message; }
    if (!r) { const c = lit.getContext("2d"); flat(); c.drawImage(src, 0, 0); if (!st.textContent.startsWith("shader")) st.textContent = "WebGL2 is off in this browser: showing the flat status line"; return; }
    r.upload();
    function pick(lit_) {
      edition = lit_ ? "tubes" : "classic"; shaderOn = lit_;
      document.getElementById("b-lit").setAttribute("aria-pressed", lit_);
      document.getElementById("b-flat").setAttribute("aria-pressed", !lit_);
      document.getElementById("cap").textContent = lit_ ? "ghostty · neon-sumi.glsl · live" : "iTerm2, Terminal, Windows Terminal · no shader";
      draw(); r.upload(); r.frame(performance.now() / 1000);
    }
    document.getElementById("b-lit").addEventListener("click", () => pick(true));
    document.getElementById("b-flat").addEventListener("click", () => pick(false));
    const t0 = performance.now();
    if (reduce) { r.frame(1.2); st.textContent = "still frame · reduced motion is on"; return; }
    st.textContent = "live · the cursor on the prompt shows the comet";
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
