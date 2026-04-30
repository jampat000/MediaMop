# Execution Plans

Use execution plans for work that is too large or risky for a single conversational task.

## Directory Layout

- `active/` - plans currently being implemented.
- `completed/` - completed plans retained for decision history.
- `tech-debt-tracker.md` - known cleanup queue that is not yet an active plan.

## When To Create A Plan

Create a plan when work touches multiple modules, changes release or installer behavior, changes file deletion/mutation safety, changes data migrations, or requires staged validation across Windows, Docker, backend, and frontend.

Small bug fixes can stay in the PR description if they have clear acceptance criteria and validation.

## Plan Template

```markdown
# Plan: short title

## Goal

What user-visible outcome this delivers.

## Current State

What exists now and what is failing or missing.

## Scope

Files, modules, workflows, or docs expected to change.

## Non-Goals

What this plan intentionally does not cover.

## Acceptance Criteria

- Observable condition that proves the goal is met.
- Tests or smoke checks that must pass.

## Steps

1. First durable step.
2. Second durable step.

## Validation Log

- Date, command, result.

## Decisions

- Date, decision, reason.
```
