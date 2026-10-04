---
name: install
description: Install or update the Neon Sumi status line, subagent line and cockpit for this user. Use when the user runs /neon-sumi:install or asks to set up, update, or remove Neon Sumi.
---

# Install Neon Sumi

A plugin cannot change `statusLine`, so this skill copies the files to a stable place and, with the user's
confirmation, points `settings.json` at them. The cockpit pane needs none of this: `/neon-sumi-cockpit` works
from the plugin folder as soon as the plugin is enabled. Follow the steps in order and report what you did.

## 1. Check the requirements

- `python3 --version` must be 3.9 or newer. Standard library only; nothing to pip install.
- `gh auth status`: optional. Without an authenticated `gh`, the PR / ticket / issue rows and the cockpit's
  work and inbox blocks stay empty; everything else works.
- `jq`: needed by the subagent line only.
- A Nerd Font in the terminal (for example Maple Mono NF or JetBrains Mono Nerd Font); without one the icons
  show as boxes.

Pick the interpreter. On macOS, `/usr/bin/python3` is Xcode's Python 3.9, which ships without compiled
bytecode for its standard library and costs about 80 ms extra per render. If a faster `python3` exists
(`~/.local/bin/python3.12` from uv, `/opt/homebrew/bin/python3`), prefer it and say why.

## 2. Copy the files

Copy everything in `${CLAUDE_PLUGIN_ROOT}/statusline/` to `~/.claude/neon-sumi/`, creating the folder. On an
update, keep the user's existing `~/.claude/neon-sumi/config.json`; never overwrite it. If there is no
`config.json` yet, do not create one: every key is optional, and `config.example.json` shows them all.

## 3. Test before touching settings

Render once with a sample payload and show the user the output:

```bash
printf '%s' '{"model":{"display_name":"Opus"},"effort":{"level":"high"},"cwd":"'"$PWD"'","context_window":{"total_input_tokens":120000,"context_window_size":1000000,"used_percentage":12},"rate_limits":{"five_hour":{"used_percentage":34,"resets_at":'"$(( $(date +%s) + 5400 ))"'},"seven_day":{"used_percentage":21,"resets_at":'"$(( $(date +%s) + 300000 ))"'}}}' \
  | <python> -B ~/.claude/neon-sumi/statusline.py
```

It must print rows and exit 0. If it prints nothing, stop and report.

## 4. Point settings.json at it (ask first)

Show the user this change to `~/.claude/settings.json` and apply it only after they confirm. Back the file up
first (`settings.json.bak-neon-sumi`). Keep every other key untouched.

```json
"statusLine": {
  "type": "command",
  "command": "<python> -B ~/.claude/neon-sumi/statusline.py",
  "refreshInterval": 1
},
"subagentStatusLine": {
  "type": "command",
  "command": "sh ~/.claude/neon-sumi/subagent.sh"
}
```

If the user already has a `statusLine`, show it next to the new one and say that the backup restores it.

## 5. Tell the user what else is there

- Cockpit: `/neon-sumi-cockpit` opens it as a pane inside Claude Code (2.1.286 or newer). In an older Claude
  Code, or in a tmux or iTerm2 split of its own: `<python> -B ~/.claude/neon-sumi/cockpit.py`
- Links per repo, boards, services and a guide link: copy `config.example.json` to `config.json` and edit.
- Ghostty edition: tubes, a sparkline and pace on the 5h row, and a shader that makes the neon glow. Add
  `config-file = ~/.claude/neon-sumi/ghostty/neon-sumi.ghostty` to the Ghostty config. The status line
  switches by itself when `TERM_PROGRAM` is `ghostty`.

## Uninstall

Restore `settings.json.bak-neon-sumi` (or remove the two keys), then delete `~/.claude/neon-sumi/` and
`~/.cache/neon-sumi/`.
