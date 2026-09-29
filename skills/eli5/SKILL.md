---
name: eli5
description: Turn a just-finished plan, task, or PR into a radically simple, visual "explain like I'm 5" Artifact with a headline, what got built, and what is left. Triggers on "eli5" and "explain like I'm five". Disposable and throwaway-simple, built for a 10-second scan, not documentation.
---

# /eli5

Simplicity is the whole point. Resist every urge to add sections, charts, or polish beyond what is
below. Someone should read this in 10 seconds and get the real picture. The visual spec is **fixed**:
"make it visual" means use the glyphs and colors below, not add a chart.

## Source

- **Default:** the plan, task, or work that just finished in this session. Use what is already in context.
- **With an argument** (plan path, PR number, or branch): gather from that with `git log`, `git diff`,
  the PR body, or the named plan file.

## Content: a headline and two blocks

1. **Headline:** a kicker naming the thing (for example `TASK 3 · LOGIN PAGE`) above one sentence in
   kid-words, with the single most important phrase highlighted in the accent color.
2. **What got built:** a few short, concrete bullets. Real nouns and numbers, not "improved".
3. **What's left:** only from named sources: unchecked plan items, an explicit deferred line, a `TODO`
   left in the diff, or an open follow-up ticket. If none exist, say "nothing left". Never invent a gap.

Fold the 1 to 3 decisions that mattered ("we picked X over Y because Z") into the section they explain,
right under the bullet, as a `why` line. Skip if nothing decision-worthy happened.

## Style

- Words a 5 year old knows. Short sentences. "3 files, 40 lines" beats "a moderate change".
- Simple is not vague: every claim points at a file, a number, or a name.

## Visual design (fixed)

Single dark theme. Google Fonts `Sora` (headline) and `IBM Plex Sans` (body). One card per section,
one accent color per section.

```css
:root {
  --bg: #0d0f14; --surface: #171a23; --line: #2a2f40;
  --ink: #e6e8f0; --ink-muted: #9298ab;
  --teal: #4fd1c5;   /* What got built */
  --amber: #f2b04c;  /* What's left */
}
body { background: var(--bg); color: var(--ink); font-family: "IBM Plex Sans", sans-serif; }
.eyebrow {
  font-family: "Sora", sans-serif; font-size: 0.75rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em; color: var(--ink-muted); margin: 0 0 6px;
}
.tldr { font-family: "Sora", sans-serif; font-size: 1.45rem; font-weight: 700; line-height: 1.35; margin: 0; }
.tldr em { color: var(--teal); font-style: normal; }
.block { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 18px 20px; }
.block h2 {
  font-family: "Sora", sans-serif; font-size: 0.8rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.07em; margin: 0 0 10px;
  display: flex; justify-content: space-between; align-items: baseline;
}
.block h2 .count { font-weight: 400; text-transform: none; letter-spacing: normal; color: var(--ink-muted); }
.built h2 { color: var(--teal); }
.left h2 { color: var(--amber); }
.block ul { margin: 0; padding-left: 1.3em; display: flex; flex-direction: column; gap: 8px; }
.built li::marker { content: "✓  "; color: var(--teal); }
.left li::marker { content: "→  "; color: var(--amber); }
.why { display: block; margin-top: 3px; padding-top: 3px; border-top: 1px solid var(--line); color: var(--ink-muted); }
```

Shape (one item shown per section):

```html
<div class="eyebrow">TASK 3 · LOGIN PAGE</div>
<p class="tldr">The site now has a front door. Visitors can <em>sign in</em> with an email link.</p>

<div class="block built">
  <h2>What got built <span class="count">3</span></h2>
  <ul>
    <li>One new page with a single email box.
      <span class="why"><b>No passwords.</b> Nothing to forget, nothing to leak.</span></li>
  </ul>
</div>

<div class="block left">
  <h2>What's left <span class="count">1</span></h2>
  <ul>
    <li>Sending the real emails.
      <span class="why"><b>Waits on the mail provider account.</b></span></li>
  </ul>
</div>
```

`count` is the real number of bullets in that section, never a made-up number.

## Build

- Publish a **new** artifact each run with a dated, slugged title. Do not overwrite the last one.
- Give the user the link. Nothing else is needed in chat.
