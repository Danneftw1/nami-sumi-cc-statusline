# Neon Sumi

A status line for [Claude Code](https://code.claude.com). Neon tubes mounted on an ink-wash scroll: neon is
reserved for what is live (bar fills, percentages, state, links), everything static is warm ink and paper.

![Neon Sumi in Ghostty, with the shader on](docs/neon-sumi.png)

The picture is the Ghostty edition with its shader. Open `docs/index.html` in a browser to see it live, with a
toggle to the edition for every other terminal. The repo, tickets and ports in it are made up.

## What it shows

**Claude**: model, effort, advisor, session cost. Context, 5-hour and weekly usage as three bars, each in its own
colour until it reaches 70 % (amber) and 85 % (red). Web links and readable files (documents, images, video;
never code or config) mentioned in the conversation, as clickable chips.

**GitHub**: repo, branch, ahead/behind and the uncommitted diff. The worktree you are in, or, in the main checkout,
the worktrees your agents are using. One row each for PRs, board tickets and plain issues mentioned in the chat,
every number with its title and state, a ticket with its board column. The branch's own PR comes first with
CI and review state. Then where the repo lives online: GitHub, plus any board, deploy or design links you add.

**Machine**: local ports that actually serve a page, as links. Ports that only answer with an error are counted,
not linked.

Everything that is the same in every session (all your open PRs, the GitHub inbox, every port grouped by owner,
your boards) lives in the **cockpit**, a separate view for a narrow split pane. Every block in it says how old its
data is.

## Install

In Claude Code:

```
/plugin marketplace add Danneftw1/neon-sumi
/plugin install neon-sumi@neon-sumi
/neon-sumi:install
```

The install skill copies the files to `~/.claude/neon-sumi/`, renders once to check that it works, and asks
before it changes `statusLine` and `subagentStatusLine` in `~/.claude/settings.json` (it keeps a backup).
Plugins cannot set the status line themselves, which is why this step exists.

Manual install: copy `plugins/neon-sumi/statusline/` to `~/.claude/neon-sumi/` and add to `settings.json`:

```json
"statusLine": { "type": "command", "command": "python3 -B ~/.claude/neon-sumi/statusline.py", "refreshInterval": 1 },
"subagentStatusLine": { "type": "command", "command": "sh ~/.claude/neon-sumi/subagent.sh" }
```

**Needs**: Python 3.9+ (standard library only), a Nerd Font in the terminal, `git`. Optional: an authenticated
`gh` for the GitHub rows and the cockpit, `jq` for the subagent line, `docker` for container ports.

**Speed**: one Python process per render, about 25 ms on Python 3.12. Git is refreshed at most every 2 s, and
nothing on the render path touches the network: GitHub and ports are collected by detached background
processes that share one cache between all open sessions.

## Configure

Everything works without a config file. To add links, copy `config.example.json` to
`~/.claude/neon-sumi/config.json`:

| Key | What it does |
| --- | --- |
| `edition` | `auto` (default), `classic` or `tubes` |
| `repos` | extra links per `owner/name` for the online row: board, Vercel, v0, anything |
| `boards`, `services`, `resources` | links in the cockpit |
| `guide_url` | adds a guide chip to the first row |
| `vaults` | Obsidian vaults: `.md` files inside open in Obsidian instead of as files |

## Cockpit

```
python3 -B ~/.claude/neon-sumi/cockpit.py
```

Run it in a split pane (it is designed for 56 columns and wider). `--once` prints one frame.

## Ghostty edition

In Ghostty, the status line switches to tubes: bars drawn with box-drawing strokes that Ghostty renders edge to
edge, a sparkline of the last hour on the 5h row, and where you will land at reset at the current pace
(`→ 89 % at reset`, or `cap in 38m` in red). `ghostty/neon-sumi.glsl` is a custom shader that makes the neon glow:
bloom on saturated colours only, a slow current along the tubes, an ink-wash grain on the background and a
short comet behind the cursor. To use the theme, shader and Display P3 colour, add this line to your Ghostty
config:

```
config-file = ~/.claude/neon-sumi/ghostty/neon-sumi.ghostty
```

The shader makes the whole terminal glow, not only the status line. `custom-shader-animation = false` in that
file keeps the glow and stops the motion.

## Obsidian

`obsidian/` has a matching Obsidian theme and a profile for the community Terminal plugin, so a terminal inside
Obsidian gets the same colours. See [obsidian/README.md](obsidian/README.md).

![The Obsidian theme](docs/obsidian.png)

## Development

`tools/fixtures.py` builds a made-up world (a git repo with worktrees, PRs, tickets, ports) and
`tools/build_docs.py` renders `docs/index.html` from it:

```
uv run --no-project --with fonttools --with brotli python tools/build_docs.py
```

## Credits

Typeset in [Maple Mono](https://github.com/subframe7536/maple-font) (SIL OFL 1.1); icons from
[Nerd Fonts](https://www.nerdfonts.com). MIT licensed, see [LICENSE](LICENSE).
