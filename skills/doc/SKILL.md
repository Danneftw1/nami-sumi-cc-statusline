---
name: doc
description: Summarize the latest topic of the current Claude Code session into a concise markdown note in the repo. Pass a topic (`/doc <topic>`) to document that instead of the latest segment. Use when the recent work should be captured as a note. Documentation, not a transcript.
---

# /doc

Capture the most recent thread of this session as a short, well-structured note. Favour the few
load-bearing facts over completeness.

## Scope

- **Default:** the latest coherent topic of this session, meaning since the last topic shift or the last `/doc`.
- **`/doc <topic>`:** document that topic from the session instead.
- If "latest" is ambiguous, state your reading in one line and proceed.

## Steps

1. Identify the scope.
2. Write `docs/sessions/<YYYY-MM-DD> <topic-slug>.md` in the current repo (create the folder if needed).
   If a note for the same date and topic exists, extend it instead of duplicating.
3. Use this shape:
   - **Frontmatter:** `title`, `date`, `tags: [session-doc, <topic-slug>]`.
   - **TL;DR:** 1 to 3 sentences.
   - **Context:** why the work happened.
   - **Done / decided:** bullets with settled outcomes, not the back-and-forth.
   - **Artifacts:** file paths, PR or issue numbers, commands, key numbers, in backticks.
   - **Open / next:** unfinished items. Omit if none.
4. Confirm with the path written and a one-line summary.

## Rules

- Write only the note. Change nothing else during `/doc`.
- Never include secrets or tokens. Reference paths instead of pasting large file contents.
- Plain language, ordinary markdown.
