# Git note: rename detection noise in commit `93547e2`

## What shows up in history

Commit `93547e2` is a large Fetcher / Refiner lane split. Git’s rename heuristics paired several **unrelated** paths (similarity-based renames). `git show --stat` can therefore list misleading “rename” pairs for reviewers who infer lineage from rename metadata alone.

## Why this was not “fixed” in the perfection pass

Correcting author-facing rename metadata **after the fact** requires **rewriting history** (e.g. `git rebase` / `git filter-repo` with explicit rename records) and then **force-pushing** all affected branches. That is explicitly out of scope when:

- the remote already contains the commit, and
- the task forbids history rewrite and push.

## Permanent repo decision

- **Truth for code lineage:** use `git log --follow` on the **current** path and read the **final tree** at each commit; do not rely solely on rename similarity scores from that migration commit.
- **Truth for architecture:** use ADRs and module boundaries ([ADR-0007](ADR-0007-module-owned-worker-lanes.md)), not rename metadata.

If a future maintainer performs an **allowed** history rewrite on a private fork, they may replant that commit with explicit `git mv` steps for clarity; this note documents why the published graph was left unchanged.
