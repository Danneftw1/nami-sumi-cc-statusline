# Neon Sumi for Obsidian

Neon tubes mounted on an ink-wash scroll.

A dark Obsidian theme. The ground is warm sumi black (`#0f0c0d`), text is rice paper (`#e8dcc6`), and every border, rule and piece of chrome is quiet ink. Neon appears only where something is live or interactive: magenta links and cursor, a violet-to-mint sweep across heading levels, amber tag pills, the active tab and file, checked boxes, and the selection. H1, H2, links, tags and callout titles carry a faint glow; body text never does. Nothing animates.

Open `preview.html` in a browser for a mock Obsidian window with the theme applied.

## Install

1. Create the folder `<vault>/.obsidian/themes/Neon Sumi/` (the name must match exactly).
2. Copy `theme/manifest.json` and `theme/theme.css` into it.
3. In Obsidian: Settings → Appearance → Themes, pick **Neon Sumi**. If it is not listed, use the reload button next to *Manage*.

The theme is designed for dark mode. Light mode shows the same dark palette.

## Fonts

Fonts are named, not bundled. Install them for the intended look; without them Obsidian falls back to the system UI and monospace fonts.

- Text and interface: Zen Kaku Gothic New
- Code: Maple Mono NF, then JetBrains Mono

Font fields in Settings → Appearance override the theme's choice.

## Accent colour

The accent is magenta (`#ff2ec4`). Changing it in Settings → Appearance recolours buttons, toggles and other accent UI. Links, tags, headings and the cursor keep the Neon Sumi colours.

## Terminal plugin (optional)

`terminal-profile.md` has the xterm.js colour theme for the community Terminal plugin and where to paste it. `snippets/neon-sumi-terminal.css` adds a faint magenta edge to the terminal pane.

## Files

| Path | What |
| --- | --- |
| `theme/manifest.json` | Theme manifest |
| `theme/theme.css` | The theme |
| `terminal-profile.md` | Terminal plugin colours and setup |
| `snippets/neon-sumi-terminal.css` | Optional CSS snippet for the terminal pane |
| `preview.html` | Self-contained preview page |

## Compatibility

Minimum Obsidian version 1.5.0. Callouts are styled directly rather than through `--callout-color`, whose format changed in Obsidian 1.13, so they render the same before and after that release. A snippet that recolours callouts through `--callout-color` will not take effect under this theme.
