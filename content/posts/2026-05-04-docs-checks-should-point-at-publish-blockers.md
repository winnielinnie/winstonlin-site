---
title: Docs Checks Should Point at Publish Blockers
date: 2026-05-04
slug: docs-checks-should-point-at-publish-blockers
summary: A useful docs checker should stay close to the few issues that actually stop a draft from being ready to hand off, review, or publish.
---

It is easy for a docs checker to drift into a vague quality assistant.

That is usually where it gets weaker.

The better version is smaller.

I want the tool to catch the issues that most often make a draft feel unfinished right before it is reviewed, shared, or published.

## The last pass should be brutally practical

At the end of a docs workflow, I usually care less about style theory and more about whether the obvious blockers are still there.

Things like:

- leftover placeholder text
- broken local links
- duplicate headings from rough copy-paste cleanup

Those are not glamorous checks.

They are the ones that keep surfacing anyway.

## Good checks narrow the fix list

`doc-ship-check` works for me because it stays close to that last-mile problem.

It does not try to score the quality of the writing.
It does not pretend to replace a real docs review.
It gives a short list of fixable blockers.

That shape matters.

If the output is short enough to act on immediately, the tool speeds up the finish.
If the output turns into another long diagnostic report, it starts adding drag instead.

## The best small checks are honest about the boundary

This is the same standard I keep wanting from other small workflow utilities.

The repo should say what it checks.
It should show what the output looks like.
It should admit what still needs a human review.

That is usually enough.

The point is not to automate all judgment.
The point is to make the repeated blockers visible early enough that the human review can spend more time on the parts that actually need judgment.

## What I keep optimizing for

When I make a small check, I keep asking one question:

Would this help somebody finish the draft faster without making them learn a new system first.

If the answer is yes, the tool is probably scoped correctly.

If the answer requires a long explanation, the scope is probably already drifting.
