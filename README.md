# Neon Sumi

**A status line for [Claude Code](https://code.claude.com) that tells you where you stand, so you don't have to ask.**

Context left, the 5-hour and weekly limits, the branch and its PR, the tickets you mentioned, the dev server that is
actually up. One glance below the prompt, drawn as neon tubes on an ink-wash scroll.

Free and open source (MIT). Python standard library only. Three commands to install.

![Neon Sumi in Ghostty, with the shader on](docs/neon-sumi.png)

**[See it running live →](https://danneftw1.github.io/neon-sumi/)** The real shader over the real status line, in
your browser, with a toggle for terminals without shaders. The repo, tickets and ports in it are made up.

## Why you might want it

- **You stop asking.** How much context is left, whether CI passed, which port the app is on: the answers are already
  on screen, refreshed every second.
- **It stays out of the way.** About 25 ms per render, one Python process, and nothing on the render path touches the
  network. GitHub and ports are collected in the background and share one cache across every open session.
- **Colour means something.** Neon is reserved for what is live: bar fills, percentages, state, links. Everything
  static is warm ink and paper. Bars turn amber at 70 % and red at 85 %, so the only thing that stands out is the
  thing that needs you.
- **Nothing to take on trust.** No pip install, no account, no telemetry. It talks to your own `localhost` and, through
  your own `gh`, to GitHub. About 2,000 lines of Python you can read in an afternoon.

## Install

In Claude Code:

```
/plugin marketplace add Danneftw1/neon-sumi
/plugin install neon-sumi@neon-sumi
/neon-sumi:install
```

The install skill copies the files to `~/.claude/neon-sumi/`, renders once so you can see it works, and asks before it
changes `statusLine` and `subagentStatusLine` in `~/.claude/settings.json`. It keeps a backup of your settings.
Plugins cannot set the status line themselves, which is why that last step exists.

**Needs**: Python 3.9+, a [Nerd Font](https://www.nerdfonts.com) in the terminal, `git`. Optional: an authenticated
`gh` for the GitHub rows and the cockpit, `jq` for the subagent line, `docker` for container ports.

<details>
<summary>Manual install</summary>

Copy `plugins/neon-sumi/statusline/` to `~/.claude/neon-sumi/` and add to `~/.claude/settings.json`:

```json
"statusLine": { "type": "command", "command": "python3 -B ~/.claude/neon-sumi/statusline.py", "refreshInterval": 1 },
"subagentStatusLine": { "type": "command", "command": "sh ~/.claude/neon-sumi/subagent.sh" }
```

</details>

## What it shows

**Claude**: model, effort, advisor, session cost. Context, 5-hour and weekly usage as three bars, each in its own
colour until it reaches 70 % (amber) and 85 % (red). Web links and readable files (documents, images, video; never
code or config) mentioned in the conversation, as clickable chips.

**GitHub**: repo, branch, ahead/behind and the uncommitted diff. The worktree you are in, or, in the main checkout, the
worktrees your agents are using. One row each for PRs, board tickets and plain issues mentioned in the chat, every
number with its title and state, a ticket with its board column. The branch's own PR comes first, with CI and review
state. Then where the repo lives online: GitHub, plus any board, deploy or design links you add.

**Machine**: local ports that actually serve a page, as links. Ports that only answer with an error are counted, not
linked.

## The cockpit

Everything that is the same in every session lives in a separate view for a narrow split pane: all your open PRs, the
GitHub inbox, every port grouped by owner, your boards. Every block says how old its data is.

```
python3 -B ~/.claude/neon-sumi/cockpit.py
```

It is designed for 56 columns and wider. `--once` prints one frame.

## Ghostty edition

In [Ghostty](https://ghostty.org) the status line switches to tubes by itself: bars drawn with box-drawing strokes
that Ghostty renders edge to edge, a sparkline of the last hour on the 5h row, and where you will land at reset at the
current pace (`→ 89 % at reset`, or `cap in 38m` in red).

`ghostty/neon-sumi.glsl` is a custom shader that makes the neon glow: bloom on saturated colours only, a slow current
along the tubes, an ink-wash grain on the background and a short comet behind the cursor. To use the theme, shader and
Display P3 colour, add one line to your Ghostty config:

```
config-file = ~/.claude/neon-sumi/ghostty/neon-sumi.ghostty
```

The shader lights the whole terminal, not only the status line. `custom-shader-animation = false` in that file keeps
the glow and stops the motion.

Every other terminal (iTerm2, Terminal, Windows Terminal) gets the classic edition: the same rows, no shader.

## Obsidian

`obsidian/` has a matching Obsidian theme and a profile for the community Terminal plugin, so a terminal inside
Obsidian gets the same colours. See [obsidian/README.md](obsidian/README.md).

![The Obsidian theme](docs/obsidian.png)

## Configure

Everything works without a config file. To add links, copy `config.example.json` to `~/.claude/neon-sumi/config.json`:

| Key | What it does |
| --- | --- |
| `edition` | `auto` (default), `classic` or `tubes` |
| `repos` | extra links per `owner/name` for the online row: board, Vercel, v0, anything |
| `boards`, `services`, `resources` | links in the cockpit |
| `guide_url` | adds a guide chip to the first row |
| `vaults` | Obsidian vaults: `.md` files inside open in Obsidian instead of as files |

## Uninstall

Restore `~/.claude/settings.json.bak-neon-sumi` (or remove the two keys), then delete `~/.claude/neon-sumi/` and
`~/.cache/neon-sumi/`. `/plugin uninstall neon-sumi@neon-sumi` removes the plugin itself.

## Development

`tools/fixtures.py` builds a made-up world (a git repo with worktrees, PRs, tickets, ports) and `tools/build_docs.py`
renders the site, `docs/index.html`, from it:

```
uv run --no-project --with fonttools --with brotli python tools/build_docs.py
```

Issues and pull requests are welcome.

## License and credits

MIT, see [LICENSE](LICENSE). Typeset in [Maple Mono](https://github.com/subframe7536/maple-font) (SIL OFL 1.1); icons
from [Nerd Fonts](https://www.nerdfonts.com).
