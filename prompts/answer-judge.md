# Answer judge prompts

**Used by**: `tools/judge_answers.py` (two separate calls per answer)
**Model**: claude-haiku-5-5 by default, no tools

The checklist ("facts") is written by the owner, not by a model. The presence judge sees only the question, the facts and the answer. The grounding judge sees only the facts and the pages the agent actually read. Keeping their inputs apart stops the pages from talking the first judge into a "present". `{question}`, `{facts}`, `{answer}`, `{pages}` are replaced by plain text substitution.

Known weaknesses: a small model as judge is lenient with vague answers; check it against the human sample the tool writes (`manual-sample.md`) before trusting its numbers.

## Presence prompt

````text
You grade an answer against a checklist. For each numbered fact decide whether the ANSWER states it (same meaning is enough, exact words are not needed; a vague mention or a contradicting statement does not count).
Output ONLY JSON: {"facts": [{"n": 1, "present": true}, ...]} with one entry per fact. No prose.

QUESTION:
{question}

FACTS:
{facts}

ANSWER:
{answer}
````

## Grounding prompt

````text
You check whether facts are supported by wiki pages. For each numbered fact decide whether the PAGES below contain it (same meaning is enough).
Output ONLY JSON: {"facts": [{"n": 1, "supported": true}, ...]} with one entry per fact. No prose.

FACTS:
{facts}

PAGES:
{pages}
````
