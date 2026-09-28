#!/usr/bin/env python3
"""One answer to "what URL opens this path when I click it".

  note (.md) inside a configured Obsidian vault -> obsidian://open?vault=<name>&file=<rel>
  macOS / native Linux                           -> file:///path
  WSL, /mnt/<d>/rest                             -> file:///<D>:/rest
  WSL, any other path                            -> file://wsl.localhost/<distro>/<path>

Vaults come from config.json ("vaults": [{"path": "~/notes", "name": "notes"}]);
without any, every file is a plain file link.

Call it from a shell:  python3 pathlink.py <path>   (prints the URL)
"""
import os
import sys
import urllib.parse

HOME = os.path.expanduser("~")
DISTRO = os.environ.get("WSL_DISTRO_NAME") or ""
VAULTS = []


def configure(vaults):
    """[{path, name}] -> VAULTS, most specific first."""
    global VAULTS
    out = []
    for v in vaults or []:
        if isinstance(v, dict) and v.get("path"):
            root = os.path.normpath(os.path.expanduser(v["path"]))
            out.append((root, v.get("name") or os.path.basename(root)))
    VAULTS = sorted(out, key=lambda rv: -len(rv[0]))


def expand(path):
    path = os.path.expanduser(str(path).strip())
    return os.path.normpath(path) if os.path.isabs(path) else path


def link_for(path):
    """URL that opens `path`. '' for a relative path (ambiguous)."""
    p = expand(path)
    if not os.path.isabs(p):
        return ""
    if p.lower().endswith(".md"):
        for root, name in VAULTS:
            if p == root or p.startswith(root + os.sep):
                rel = os.path.relpath(p, root)
                return "obsidian://open?vault=%s&file=%s" % (urllib.parse.quote(name, safe=""),
                                                             urllib.parse.quote(rel[:-3], safe="/"))
    if not DISTRO:
        return "file://" + urllib.parse.quote(p, safe="/")
    parts = p.split("/")
    if len(parts) >= 3 and parts[1] == "mnt" and len(parts[2]) == 1:
        return "file:///%s:/%s" % (parts[2].upper(), urllib.parse.quote("/".join(parts[3:]), safe="/"))
    return "file://wsl.localhost/%s%s" % (urllib.parse.quote(DISTRO, safe=""), urllib.parse.quote(p, safe="/"))


def short(path, width=48):
    """Display form: ~ for home, vault name for a vault, middle-elided."""
    p = expand(path)
    for root, name in VAULTS:
        if p == root or p.startswith(root + os.sep):
            p = name + p[len(root):]
            break
    else:
        if p == HOME or p.startswith(HOME + os.sep):
            p = "~" + p[len(HOME):]
    if len(p) > width:
        keep = width - 1
        p = p[: keep // 3] + "…" + p[-(keep - keep // 3):]
    return p


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(link_for(arg))
