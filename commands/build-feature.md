---
description: Drive a whole feature plan to a reviewable branch — refine the design, split into tickets, then run each ticket through build-ticket, committing per ticket. Stops for the user to review before merging.
argument-hint: <plan file path or inline plan>
---

Take this feature plan and drive it to completion on a reviewable branch: $ARGUMENTS

This runs both halves in **one session**: the steps of `/plan-feature` (refine → questions → branch → tickets → handoff), then, instead of stopping at its step 6, continue straight into the steps of `/drive-tickets` for the same feature slug. Follow those two command files exactly; this file adds nothing else.

**On a usage-limited plan, prefer the split.** Running both halves here means the whole batch drive happens on whatever model planned it — usually the most expensive one — and that sequencing work is the bulk of a feature's orchestrator turns. `/plan-feature` on a strong model, then `/drive-tickets` in a fresh Sonnet session, gets the same result for a fraction of the usage. Use this combined command when you want one uninterrupted run and usage isn't the constraint — or for a **small, well-understood feature**, run it in a single `claude --model sonnet --advisor opus` session: Sonnet 5.5 is close to Opus 5.5 on most work, and the advisor covers the planning calls that need more.
