# Roadmap: ordered next steps for the kit, each with the reason it comes where it does.

Status of every item: not started. The order matters: measurement first, changes to a live wiki last.

## Now: make the measurement trustworthy

1. **Measure answer correctness, not only hits.** Reason: a hit means a gold page was opened, not that the answer was right. Until this exists, "faster and cheaper" cannot be called better. Not started.
2. **Grow the question set to 25 to 30 and repeat each question.** Reason: nine questions, one model, three runs is a direction only. Also write gold pages independently of what the agent opened, to remove the selection bias noted in [our-findings.md](our-findings.md). Not started.
3. **Fix the answer checker's inputs.** Keep question context (what the owner knew) and freeze the wiki at question time where possible, since some gold pages changed during their own tasks. Not started.

## Then: tune the search tool

4. **Address the top-hit trust problem.** The agent stops at the first result even when the gold page ranks 2nd by a small margin, and noisy alias matches push gold out of the top 4. Candidate fixes to test, none tried: show several close candidates with scores, lower the weight of generated aliases, require the page summary in the output. Not started.
5. **Review the generated aliases by hand.** They are a draft made from page text only. Not started.

## Then: compare

6. **Re-run A (as is) versus B (aliases in summaries) versus C (search tool plus alias file)** on one frozen copy with repeats. B has never been measured because of a usage limit. Reason: only then do we know which change helps. Not started.

## Only after that

7. **Change a live wiki**, with the owner's approval, using the variant that won. Not started.

## Later

8. **Wiki linter** (orphans, missing summary lines, duplicate or overlapping pages, broken links), possibly with a single health number. Not started.
9. **Post-session mode of the miner**: take single-session signals right after a session and feed them into the 3-session rule. Not started.
10. **Hub or entry pages** for topics where many pages overlap (the updates topic needed four of five pages). Not started.
11. **Staleness markers** on pages (fresh, stale, unverified) and a check against source changes. Not started.
12. **Indexes generated from frontmatter**, tiered or per folder, instead of one hand-kept `index.md`. Idea from an unverified note. Not started.
