---
title: AI Work Needs Real Tools
date: 2026-04-17
slug: what-working-with-codex-taught-me-about-ai-work
summary: Months of hands-on use reinforced that useful AI work depends on tools, files, review loops, and recovery paths around the model.
---

Over the last few months I have used Codex on real work more than demos. The main lesson has been simple: the useful part is not one response. It is the setup around the model. When the workspace is good, the model can inspect the right files, run the right tools, make the change, rebuild the artifact, and show what happened. When the setup is weak, you mostly get fluent guesswork.

## It works best when it can actually work the repo

At its best, this feels less like "generate some text" and more like working with someone who can inspect the repo, trace the problem, try a fix, and explain the tradeoff. That does not remove judgment. It just means the human judgment shifts up a level: what should be automated, what should be checked, and where the bar should be.

## What actually matters

What has mattered most in practice has been the ability to move across different kinds of work without resetting context:

- inspect source files
- update content and rebuild a site
- turn notes into docs or slides
- check output against the underlying files
- trace a broken step and recover cleanly

That is a much more useful capability than "write me a paragraph." It is also why I care less about prompting in the abstract and more about whether the workflow has the right tools, boundaries, and review steps.

## Structure still wins

The sessions that go well usually have a few things in common:

- clear files and source material
- a readable working directory
- scripts that make rebuilding cheap
- outputs that can be checked instead of just admired
- explicit places to stop, confirm, or retry

That sounds obvious, but it points to a broader lesson: a lot of AI quality is downstream of product and system quality. If the inputs are scattered, the tooling is brittle, and the recovery path is vague, the model mostly makes that mess harder to trust.

## What changed in how I think about teams

Using Codex this way has made me value a few things even more:

- teams that keep work legible
- tools that shorten the path from rough input to usable output
- people who can move between strategy, systems, and execution without losing the thread
- AI products that behave more like good workflow software and less like demos

That is also the kind of work I like being around. I like the problems where product judgment, operating reality, and detail all matter at the same time, because those are usually the problems worth solving. The best version of AI work still feels collaborative. It is not the model replacing the team. It is a tighter loop between people, judgment, and tools.
