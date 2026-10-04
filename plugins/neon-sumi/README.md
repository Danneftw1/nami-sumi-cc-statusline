# Neon Sumi

A status line for Claude Code that tells you where you stand, so you don't have to ask: context left, the 5-hour and
weekly limits, the branch and its pull request with CI and review state, the tickets and issues mentioned in the chat,
and the local dev servers that actually serve a page. Drawn as neon tubes on an ink-wash scroll, with a cockpit that opens
as a pane inside Claude Code (`/neon-sumi-cockpit`) or in any terminal split, and an optional Ghostty shader that makes
the neon glow.

Free and open source under the MIT license. Python standard library only, plus one TypeScript module that Claude Code
itself runs for the cockpit pane. Works in Claude Code (the CLI) only.

See it running: https://danneftw1.github.io/neon-sumi/

## Install

```
/plugin marketplace add Danneftw1/neon-sumi
/plugin install neon-sumi@neon-sumi
/neon-sumi:install
```

Needs Python 3.9 or newer as `python3` on your PATH, a Nerd Font in the terminal and `git`. An authenticated `gh` is
optional and enables the GitHub rows and the cockpit's work and inbox blocks.

## What the install skill changes

A plugin cannot change `statusLine` in `settings.json`, so `/neon-sumi:install` does it for you, in the open:

- It copies the scripts to `~/.claude/neon-sumi/` and renders once so you can see the output.
- It shows you the `statusLine` and `subagentStatusLine` entries it wants to add to `~/.claude/settings.json` and
  writes them only after you confirm. It saves a backup first, `settings.json.bak-neon-sumi`, and touches no other key.

To undo it, restore that backup (or remove the two keys) and delete `~/.claude/neon-sumi/` and `~/.cache/neon-sumi/`.

The cockpit pane needs no install step: `/neon-sumi-cockpit` is there as soon as the plugin is enabled. It runs
`cockpit.py` from the plugin's own folder every two seconds with the first `python3` on your PATH and draws the result
in a pane (beside the transcript in the fullscreen layout from 110 columns, above the prompt otherwise). It takes the
5-hour and weekly figures from the session, reads `~/.claude/neon-sumi/config.json` when you have one, and writes
nothing to your settings.

The plugin also adds a Neon Sumi colour theme for Claude Code itself. Nothing changes until you pick it in `/theme`.

## Privacy: what it reads and where it connects

- **Your session, locally.** The status line payload from Claude Code, and the session transcript to find the links,
  files and `#123` references mentioned in the conversation. Only those issue and PR numbers are looked up, on
  GitHub, as below; nothing else from either leaves your machine.
- **GitHub, through your own `gh`.** Read-only queries for your pull requests, their checks and reviews, the issues and
  project-board tickets mentioned in the chat, and (in the cockpit) your notifications. These run in a background
  process, never on the render path, and use whatever account `gh` is logged in as.
- **Your own machine's ports.** `lsof` or `ss`, and `docker ps` if Docker is installed, to list listening ports; then a
  plain HTTP request to `127.0.0.1` to see which of them serve a page.
- **Skills, locally.** The cockpit reads your session transcripts under `~/.claude/projects/` to count which skills
  fired this week, and the plugin folders to list the ones that stayed silent. It keeps skill names and counts, the
  first line of each hook refusal in that week and the paths of the transcripts it has read, in `~/.cache/neon-sumi/`;
  none of it leaves your machine, and the pane and the terminal cockpit share that cache.

No telemetry, no analytics, no other network access. Nothing is sent to the author of Neon Sumi or to any server they run.

Source, full documentation and issues: https://github.com/Danneftw1/neon-sumi
