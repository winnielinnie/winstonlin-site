---
title: Good Small Repos Should Show the Second Move
date: 2026-04-28
slug: good-small-repos-should-show-the-second-move
summary: A small public repo gets more reusable when it makes the next handoff or rerun obvious instead of stopping at the first demo.
---

The first demo matters.

It is not enough.

A lot of small repos do a decent job getting someone to the first useful run. The README explains the problem, shows a quick command, and gives a believable output snippet.

That gets the repo to proof.

What often stays fuzzy is the next move.

## What I want to know after the demo

Once I have seen the tool work, I want one more answer.

What would I do with this in real work next week?

That answer does not need a huge integration guide. It does need to make one of these things obvious:

- what artifact the repo leaves behind
- what handoff it makes easier
- what repeated check I would rerun later

Without that, the repo still feels like a good demo instead of a reusable tool.

## The second move is where the repo becomes reusable

`doc-ship-check` gets stronger when it is framed as the last pass before review or publish, not just a script that finds broken Markdown details.

`one-page-canvas` gets stronger when the Markdown export is treated as the real output, not just a nice extra after the browser demo.

`oci-fn-file-manifest-writer` gets stronger when the compact manifest is clearly the handoff artifact for the downstream batch job.

Those are different kinds of repos, but the useful question is the same.

After I run this once, what stable thing carries forward.

## A good README should close that gap

For small public tools, I keep wanting the README to make the path visible:

- show the quick proof step
- show the output or artifact that survives the run
- show the next place that output plugs in

That is usually enough.

It tells a reader whether the repo is just a neat example or whether it actually reduces work somewhere.

## Why this matters on the site too

This is also why I do not want the projects page to read like a flat inventory.

The interesting part is not only that there are several small repos. It is the pattern underneath them:

- some turn repeated review work into checks
- some leave behind a reusable artifact
- some make one workflow boundary visible and easier to hand off

That is the level where the repo batch starts to say something coherent.

## The bar I keep using

If a public repo can get me to first proof and also make the second move obvious, it usually earns another look.

That is the standard I keep trusting.

The repo does not just work once.
It tells me how it fits into the next step of real work.
