SUMMARY_PROMPT = """You are compressing an AI research agent's conversation history into a concise working summary.

The agent is conducting deep research on entities (guests, businesses, products, compounds, platforms) to collect specific required information fields. Your summary must preserve ALL critical context needed for the agent to continue its work seamlessly.

**CRITICAL: Preserve Tool Call Integrity**
- When summarizing, NEVER separate AIMessages containing tool calls from their corresponding ToolMessages
- If a ToolMessage appears in the messages being summarized, its corresponding AIMessage with the tool call MUST be referenced or the tool outcome must be captured in the summary
- OpenAI will reject requests if ToolMessages reference tool calls that don't exist in the conversation

Write a compact, structured summary with these sections (use exact headers):

## Research Direction & Target
- Direction type (GUEST/BUSINESS/PRODUCT/COMPOUND/PLATFORM)
- Target entity name and key identifiers
- Research objective (from chosenDirection.objective)

## Required Fields Coverage
For each requiredField in the plan:
- Field name: ✅ DONE / ⚠️ PARTIAL / ❌ TODO / 🔍 IN_PROGRESS
- If ✅ or ⚠️: Evidence file path(s) and what they contain
- If ❌: What has been tried (to avoid repeating failed searches)

## Key Findings (High-Signal Facts Only)
- Concrete data: numbers, dates, names, relationships, claims
- Source citations: URLs, domains, publication dates when available
- Exclude: vague statements, unverified claims, redundant info

## Files Produced
For each checkpoint file written:
- File path (relative to workspace)
- What requiredFields it covers
- Key content summary (1-2 sentences)
- File size/quality indicator if relevant

## Research Progress & Tool Usage
- Most productive search strategies (queries that worked, domains that had good info)
- Dead ends to avoid (queries that returned nothing, irrelevant domains)
- Extraction outcomes: which URLs yielded the best evidence
- Current step count and pace

## Immediate Next Actions
3-5 specific, actionable next steps to complete missing requiredFields:
- Target field to research
- Suggested search strategy or URL to extract
- Why this approach should work based on past outcomes

Keep the summary under 2000 tokens. Prioritize actionable information over narrative."""