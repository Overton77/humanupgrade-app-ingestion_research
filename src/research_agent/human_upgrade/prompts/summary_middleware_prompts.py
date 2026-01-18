SUMMARY_PROMPT = """
You are compressing the agent's past work into a durable working summary.
Write a compact, high-signal summary that preserves ONLY what is needed to finish the direction.

Include these sections (use exact headers):

## Objective
- Restate the chosenDirection.objective verbatim if present.

## Required fields coverage
- List each requiredField and mark: ✅ covered / ⚠️ partial / ❌ missing
- For each ✅/⚠️, point to supporting file(s) by path and what they contain.

## Key findings (high signal only)
- Bullets of concrete facts, numbers, dates, names.
- Prefer authoritative sources; include URLs when available.

## Files produced / updated
- For each file: path, description, which requiredFields it covers, and any important notes.

## Tool outcomes (only what matters)
- What searches/extracts were most useful (domain + why).
- Dead ends that should NOT be repeated.

## Open gaps / next actions
- 1–5 bullets: the smallest next steps to finish missing requiredFields.
"""