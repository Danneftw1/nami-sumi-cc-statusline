---
name: park
description: Stop the current work and save what is unfinished as a resumable note, so a fresh session can pick it up cold. Nothing is implemented after /park is invoked; only the save happens. Use when you need to break off mid-task.
---

# /park

Stop now. Capture what is unfinished so a future session can resume without this conversation.
Nothing gets implemented after this point; only the save file is written.

## Steps

1. **Check whether anything is unfinished.** If the plan or task chain concluded, say so and stop.
   No file needed.
2. **Pick the file.** Save to `.claude/parked/<slug>.md` in the current repo (create the folder if
   needed). Use a short kebab-case slug for the topic. If a file for this topic already exists,
   add a `## Status (parked <date>)` section instead of rewriting it.
3. **Write a record that stands alone.** A cold reader must be able to continue from it:
   - **In progress**: one paragraph of context.
   - **Done**: settled steps and decisions. Do not re-derive these.
   - **Next**: ordered steps, specific enough to run without asking. Exact paths, commands, branch names.
   - **Open questions**: decisions that need the user before work continues.
   - **Pointers**: files, branches, PR or issue numbers.
4. **Confirm in two lines.** The path written, and one sentence on where the work is parked.

## Rules

- No implementation after `/park`, not even a small fix noticed in passing. Put it under Open questions.
- Keep the record lean. The goal is re-entry, not documentation.
- Never write secrets or tokens into the record.
