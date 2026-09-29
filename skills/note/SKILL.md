---
name: note
description: Capture a side-thought as ONE line in a notes file, then carry on with the main task. It does not stop the work, and the noted thing is not acted on. Use when something worth remembering surfaces mid-task and chasing it now would cost focus.
---

# /note

Get a side-thought out of the way in one line so it stops competing for attention, then continue the
main task exactly where it was. The sibling of `/park`: `/park` stops everything and writes a full
resumable record, `/note` stops nothing and writes one bullet.

## Destination

`NOTES.md` in the current repo root. If the user's own instructions name another notes file, use that.
Create the file with a `# Notes` heading if it does not exist.

## Bullet format

`- YYYY-MM-DD HH:MM <one line> #note`

- `/note <text>`: the user's words, tightened to one line, about 15 words at most.
- `/note` with no text: compress the thing just discussed into one line.

Append the bullet to the end of the file.

## Rules

- Do not start working on the noted thing. That is the point of the command.
- Reply with exactly one line: `noted: <text>`.
- One write, one place. No plan file, no ticket, no memory entry.
- If it needs more than one line, say "/park it?" in one sentence and drop it. Never auto-escalate.
