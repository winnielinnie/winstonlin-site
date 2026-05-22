---
title: Validation Gates Should Fail in a Useful Shape
date: 2026-05-04
slug: validation-gates-should-fail-in-a-useful-shape
summary: A starter validation repo gets more reusable when the failing result is structured enough to show what broke, why it broke, and what the next fix should be.
---

A validation example is weak if it only shows the happy path.

For a gate, the failure shape is part of the product.

If the failing result is vague, the pattern is still hard to reuse because the next person has to invent the repair flow themselves.

## The failing case teaches the contract

This is why I like starter patterns such as `oci-fn-csv-quality-gate` when they show both the passing and failing run.

The useful part is not only that a valid CSV returns `valid: true`.

The more important part is that a bad file returns something specific enough to act on:

- which columns are missing
- which unexpected columns appeared
- what reason triggered the failure
- whether the file was effectively empty

That makes the contract visible in both directions.

## Good starter repos should make repair obvious

I keep wanting starter repos to make the next move easy to understand.

The first run should answer:

- what input shape is expected
- what result shape comes back
- what breaks when the contract is violated
- what the downstream system can do with that result

That is how a starter repo stops being a toy.

It becomes a believable boundary.

## Why this matters for workflow patterns

Real workflows rarely fail in neat ways.

So a public starter repo earns trust when it shows a failure mode without dramatizing the whole production system around it.

That means staying close to one gate, one contract, and one output shape that a later queue, alert, or quarantine step could consume.

I do not need the starter repo to implement every downstream decision.
I need it to make the edge legible enough that those later decisions can be added cleanly.

## The bar I keep using

If a starter validation repo helps somebody answer "what broke and what should I fix first" after one local run, it is already doing the right job.

That is usually the difference between a sample that feels reusable and one that feels like a sketch.
