---
title: Examples Are the Interface for Small Tools
date: 2026-04-16
slug: examples-are-the-interface-for-small-tools
summary: For small public tools, a good example usually teaches faster than architecture talk because it shortens the gap between curiosity and proof.
---

Small tools do not usually get a long sales cycle.

Someone lands on the repo, scans for about thirty seconds, and decides whether the thing feels usable.

That decision is often driven less by the code than by the example.

Can I see the input.
Can I see the command.
Can I see the output.

If those three things are obvious, the tool already feels more real.

## Examples do the trust-building work

A lot of tiny repos describe themselves well enough.

What they fail to do is prove themselves quickly.

That is the job of the example.

A good example answers the questions people have right away:

- what shape does the input need to be in
- what exact command am I supposed to run
- what kind of output should I expect back

That is not garnish.
That is the interface.

## Why this matters more for small repos

Bigger products can survive some ambiguity because they have more context around them.

A small public repo usually cannot.

It has to earn the next five minutes.

If the example is weak, the repo starts feeling like homework.

If the example is clear, the repo starts feeling usable before someone has read the entire codebase.

## The pattern I keep wanting to see

For compact tools, I keep coming back to the same structure:

- one short problem statement
- one realistic sample input
- one exact command
- one believable output snippet

That path is often enough.

Once somebody has seen the proof, they can decide whether they care about the implementation details.

Before that, architecture notes are usually too early.

## What I optimize for now

When I publish a small tool, I try to make the example do most of the onboarding work.

That usually means the README should let someone move from "I think I get it" to "I ran it and saw the point" with as little friction as possible.

That is the threshold I care about.

Not whether the repo looks impressive.
Whether it gets to proof quickly enough to be worth reopening.
