# Neon Sumi for the Terminal plugin

Matches the community plugin **Terminal** (`polyipseity/obsidian-terminal`) to the theme. Checked against plugin version 3.27.2.

The plugin passes `terminalOptions` straight to xterm.js (`ITerminalOptions`). Neon Sumi only sets `fontFamily` and `theme`.

## Terminal options

```json
{
  "fontFamily": "'Maple Mono NF', 'JetBrains Mono', ui-monospace, Menlo, monospace",
  "theme": {
    "background": "#0f0c0d",
    "foreground": "#e8dcc6",
    "cursor": "#ff2ec4",
    "cursorAccent": "#0f0c0d",
    "selectionBackground": "#3a1830",
    "black": "#1a1516",
    "red": "#ff3864",
    "green": "#40ffaa",
    "yellow": "#ffbe28",
    "blue": "#409cff",
    "magenta": "#ff2ec4",
    "cyan": "#00eaff",
    "white": "#e8dcc6",
    "brightBlack": "#544a46",
    "brightRed": "#ff6a8a",
    "brightGreen": "#7dffc4",
    "brightYellow": "#ffd76e",
    "brightBlue": "#7ab8ff",
    "brightMagenta": "#c46eff",
    "brightCyan": "#00ffcc",
    "brightWhite": "#f7efe2"
  }
}
```

## Where to paste it

**Every profile (recommended).** Settings → Terminal → *Profile defaults* → *Terminal options* → Edit → *Data*. Paste the object above as the whole value and confirm.

**One profile.** Settings → Terminal → *Profiles* → Edit → *Edit* on the profile → *Data* → Edit. Put the object above under the `"terminalOptions"` key, keeping any options already there. Save the profile.

Profile options are shallow-merged over the defaults: a profile with its own `theme` replaces the default `theme` as a whole, not key by key.

## Follow theme

Each profile has a **Follow theme** toggle, on by default. While on, the plugin overwrites four theme keys from Obsidian's CSS:

| xterm key | Taken from | Under Neon Sumi |
| --- | --- | --- |
| `background` | `--background-primary` | `#0f0c0d`, same |
| `foreground` | `--text-normal` | `#e8dcc6`, same |
| `cursor` | `--interactive-accent` | magenta, same unless the accent was changed in Settings |
| `selectionBackground` | computed: 30% white over the background | grey, not `#3a1830` |

The 16 ANSI colours, `cursorAccent` and `fontFamily` apply either way. Turn **Follow theme** off on a profile to get the exact selection colour.

## Edge glow

`snippets/neon-sumi-terminal.css` gives the terminal pane a faint magenta edge. Copy it into `<vault>/.obsidian/snippets/`, then enable it under Settings → Appearance → CSS snippets. It targets the plugin's view type `terminal:terminal`.
