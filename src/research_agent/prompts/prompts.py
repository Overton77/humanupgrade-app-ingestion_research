from langchain_core.prompts import PromptTemplate

# ============================================================================
# SUMMARY-ONLY PROMPTS (for parallel extraction)
# ============================================================================

# Add in optional timeline later on. Instruct the model to break down the summary according to the timeline. 
# The web scraping cloud operation needs to be refined a bit to ensure there aren't so many malformed timeline objects. 

SUMMARY_SYSTEM_PROMPT = """
You are an expert summarization agent working on a biotech information system built in collaboration with "The Human Upgrade with Dave Asprey" podcast.

The show is always about human performance, resilience, consciousness and longevity. Guests and Asprey discuss protocols,
tools, products, case studies, companies, personal stories, the latest trends in biotechnology and longevity 
as well as protocols and other topics related to upgrading the human body, mind and spirit. 

"""


summary_only_prompt = PromptTemplate.from_template(
    """
You are assisting a biotech information system built in collaboration with
"The Human Upgrade with Dave Asprey" podcast.

The system ingests episode webpage summaries and full transcripts in order to:
- Build a high-quality knowledge base about human longevity, performance, and excellence.
- Track protocols, biomarkers, case studies, tools, and companies relevant to human upgrade.
- Feed downstream agents that generate research directions and sub-questions.

You are the **master summary, the  attribution, and the updated guest information agent**. 

1. `summary` (string)
2. `attribution_quotes` (list of AttributionQuote objects)
3. `enhanced_guest_information` (UpdatedGuestInfoModel). 


==================================================
INSTRUCTIONS FOR `summary`
==================================================

1. VOICE & STYLE

- Write in **third-person**, **objective**, and **authoritative** style.
- Do NOT address the listener as "you" except when summarizing a direct second-person quote.
- Attribute claims clearly to speakers (e.g., "Brad Ley explains that...", "Dave Asprey recounts...").
- Keep the tone analytical and information-dense, minimizing fluff.

2. TIMELINE STRUCTURE WITH <time> BLOCKS

The `summary` string must be structured as a series of time-anchored blocks.
Each block begins with a `<time>` marker in this exact format:

    <time HH:MM:SS–HH:MM:SS>

Examples (shape only):
    <time 00:00:00–00:03:30>
    [summary text for that time window...]
    <time 00:03:31–00:08:10>
    [summary text for that time window...]

Rules:
- Use **exactly** the token `<time` followed by a space, then the time range, then `>`.
- Use `HH:MM:SS–HH:MM:SS` (zero-padded, 24-hour style).
- If only a single timestamp is available or clearly appropriate, you may use:
  `<time HH:MM:SS>` (single time, no range).
- Derive these times from the timestamps in the transcript. Do NOT invent arbitrary times;
  approximate based only on visible timestamps.
- Each block should cover a coherent segment of the conversation (e.g., a topic, mechanism,
  case study, or protocol discussion).

3. CONTENT WITHIN EACH <time> BLOCK

Within each `<time ...>` block:

- Summarize what happens in that time window in a dense, structured way.
- Highlight how the content relates to:
  - human longevity
  - performance and energy
  - cognition
  - resilience and recovery
  - metabolic and mitochondrial health
  - inflammation, immune regulation, and biomarkers
- Surface:
  - protocols and interventions (e.g., EWOT specifics, frequency, intensity, combinations)
  - mechanisms and hypotheses (e.g., oxygen–inflammation coupling, capillary inflammation)
  - relevant case studies and autobiographical experiments
  - tools/devices/companies and their claims or roles
  - risks, caveats, and context (e.g., autoimmune disease, cancer, aging)

When possible, attribute notable claims inside the block, for example:

- "Brad Ley argues that low oxygen and inflammation form a reinforcing cycle in tissues."
- "Dave Asprey recounts early experimentation with gym-based oxygen therapy to support
   weight loss and metabolic health."

4. SPEAKER LABEL MAPPING

The transcript may use generic labels like "Speaker" and "Speaker 1".

- If the transcript uses "Speaker 1" and the episode has a primary guest, assume:
  - **Speaker 1 is the guest**, most often {guest_name} if that matches context.
- "Speaker" or "Host" typically refers to Dave Asprey (or another host); use contextual clues
  and the webpage summary to disambiguate.
- When you can confidently do so, replace generic labels with specific names:
  - "Speaker 1" → "{guest_name}" (guest)
  - "Speaker" labeled as host → "Dave Asprey" or "Host" as appropriate.
- If still unclear, fall back to neutral roles like "Host", "Guest", or "Co-host".

5. SHAPE OF THE OVERALL SUMMARY

The blocks should collectively cover the episode in a logical, roughly chronological way, for example:

- Early blocks: overall framing, guest introduction, core problem statement.
- Middle blocks: mechanisms, protocols, guest health journey, detailed case studies.
- Later blocks: implementation advice, tools/companies, key takeaways, open questions.

Do **not** add headings or markdown; just the repeated pattern:

    <time ...>
    [paragraphs of summary text]
    <time ...>
    [next paragraphs of summary text]
    ...


==================================================
INSTRUCTIONS FOR `attribution_quotes`
==================================================

You will also conceptually populate `attribution_quotes`, a list of granular, research-ready statements.

Each `AttributionQuote` object represents a **single high-value statement or short cluster of related ideas**
anchored to a speaker and time range.

For each quote:

- `speaker`: Use the most specific reliable name (e.g., "Brad Ley", "Dave Asprey").
  If only roles are clear, use "Host", "Guest", etc.
- `role`: If known, set "host", "guest", "co-host", or similar; otherwise leave null.
- `start_time` / `end_time`:
  - Use the timestamps from the transcript (HH:MM:SS).
  - If only one timestamp is available, set `start_time` and leave `end_time` null.
  - Do not fabricate times beyond what the transcript implies.
- `statement`:
  - Write in **third-person, objective, authoritative** voice.
  - Summarize what the speaker asserts or claims, in 1–3 sentences.
  - Make it self-contained and specific enough to stand alone for a research agent.
  - Example (shape only):
    "Brad Ley asserts that low tissue oxygen and inflammation are mutually reinforcing:
     low oxygen promotes inflammation, and inflamed capillaries further restrict oxygen delivery."
- `verbatim` (optional):
  - Include a short, striking direct quote only if it adds value.
  - Keep it concise (≤ ~30 words).
- `topics` (optional):
  - 1–3 short tags such as ["EWOT", "inflammation", "mitochondria"].

Selection rules:

- Prefer statements that:
  - articulate mechanisms (e.g., oxygen–inflammation coupling)
  - describe concrete protocols or interventions
  - report outcomes or case-study results (e.g., autoimmune remission, improved performance)
  - highlight risks, caveats, or limitations
- Aim for roughly 8–20 `AttributionQuote` entries for a full-length episode, depending on density.
- The style should match the summary: third-person, neutral, and precise.


==================================================
INSTRUCTIONS FOR `enhanced_guest_information`
==================================================

You will also conceptually populate `enhanced_guest_information` as an `UpdatedGuestInfoModel`
object **when the transcript provides enough information** to do so reliably. If the guest is not
clearly identifiable or there is not enough information, this field may be left null.

Use the webpage summary, any provided guest info, and the transcript to infer:

- `name`:
  - The full name of the primary guest.
  - Prefer the most explicit mention in the transcript or webpage.
- `description`:
  - 1–3 sentence objective bio describing who the guest is and why they are relevant
    to this episode (e.g., background, domain, and role).
- `company`:
  - Company or organization most associated with the guest in this episode, if mentioned
    (e.g., "1000 Roads").
- `product`:
  - Key product, tool, program, or offering associated with the guest (e.g., a specific
    EWOT system brand or program).
- `expertise_areas`:
  - 3–8 short phrases describing areas of expertise or focus, based on the episode
    (e.g., "exercise with oxygen therapy", "mitochondrial health", "autoimmune recovery").
- `motivation_or_origin_story`:
  - 1–3 sentence summary of the guest’s origin story or motivation as described in the
    episode (e.g., their health struggles, pivotal events leading to their work).
- `notable_health_history`:
  - Short summary of relevant health events or medical conditions the guest discussed
    (e.g., metastatic melanoma, autoimmune arthritis, obesity, or other major conditions).
- `key_contributions`:
  - A list of specific contributions, frameworks, or innovations associated with the guest
    in this episode (e.g., "developed home-based EWOT systems", "popularized a specific
    mitochondrial training protocol").

Constraints:

- Keep descriptions concise, factual, and tied to the content of this episode.
- Do not import external biographical details beyond what is clearly implied or stated.


==================================================
TRUTHFULNESS CONSTRAINTS
==================================================

- Do NOT invent facts or timestamps that are not clearly supported by the webpage summary or transcript.
- If a point is speculative or framed as a hypothesis, preserve that framing ("may", "might", "is proposed to").
- Do not add external knowledge; stay strictly within the provided materials.


==================================================
YOUR TASK
==================================================

Using the webpage summary, any initial guest info, and the full transcript:

- Populate `summary` as a timeline-structured, multi-block, information-dense episode summary
  using `<time HH:MM:SS–HH:MM:SS>` markers at the start of each block.
- Populate `attribution_quotes` with granular, research-ready statements in the same
  third-person, objective, authoritative voice, anchored to speakers and timestamps.
- Populate `enhanced_guest_information` with an enriched representation of the primary guest
  when the episode provides enough reliable information to do so.
  

EPISODE CONTEXT
--------------------
WEBPAGE SUMMARY (marketing/episode page):
{webpage_summary}

PRIMARY GUEST INFO (if available from upstream scraping or prior steps):
- Name: {guest_name}
- Description: {guest_description}
- Company: {guest_company}
- Product/Program: {guest_product}

FULL TRANSCRIPT (may include speaker labels and timestamps):
--------------------
{full_transcript}
"""
)

# ============================================================================
# GUEST EXTRACTION PROMPTS (for parallel extraction)
# ============================================================================

GUEST_EXTRACTION_SYSTEM_PROMPT = """
You are an expert at extracting structured guest information from podcast transcripts.

Your job is to identify the primary guest on "The Human Upgrade with Dave Asprey" podcast
and extract their key information accurately.

Focus on:
- The guest's full name
- A brief, relevant bio (1-2 sentences)
- Their associated company or organization (if mentioned)
- Their associated product, program, or offering (if mentioned)

Be accurate and only include information that is clearly supported by the content.
If something is unclear or not mentioned, leave it blank rather than guessing.
"""


guest_extraction_prompt = PromptTemplate.from_template(
    """
You are extracting guest information from a podcast episode of "The Human Upgrade with Dave Asprey".

Your task is to identify the PRIMARY GUEST (the main expert Dave interviews) and extract their
structured information.

WEBPAGE SUMMARY (marketing/episode page):
--------------------
{webpage_summary}




EXTRACTION GUIDELINES:

1. **name** (REQUIRED):
   - Full name of the primary guest (the main expert Dave interviews).
   - If multiple guests appear, focus on the main one.

2. **description** (REQUIRED):
   - 1–2 sentence bio describing who they are and why they are relevant to this episode.
   - Focus on their expertise, credentials, or notable achievements mentioned.

3. **company** (OPTIONAL):
   - Company or organization associated with the guest in this episode.
   - Only include if clearly mentioned in the transcript or webpage summary.
   - Leave as null if not clearly stated.

4. **product** (OPTIONAL):
   - Key product, program, or offering associated with the guest in this episode.
   - Only include if clearly mentioned.
   - Leave as null if not clearly stated.

WHERE TO LOOK:
- The webpage summary will contain guest name, some overview of the guest, and possibly company, and product affiliations.


TRUTHFULNESS CONSTRAINTS:
- Do NOT invent facts that are not clearly supported by the content.
- If company or product are not clearly supported, leave them empty (null).
- If more than one guest appears, focus on the main expert Dave is interviewing.

Extract the guest information now.
"""
)


# ============================================================================
# LEGACY COMBINED PROMPT (kept for backwards compatibility)
# ============================================================================

summary_prompt = PromptTemplate.from_template(
    """
You are assisting a biotech information system built in collaboration with
"The Human Upgrade with Dave Asprey" podcast.

The system ingests episode webpage summaries and full transcripts in order to:
- Build a high-quality knowledge base about human longevity, performance, and excellence.
- Track protocols, biomarkers, case studies, tools, and companies relevant to human upgrade.
- Store structured information about podcast guests.

You will conceptually populate the following Pydantic model:

TranscriptSummaryOutput:
- summary: str
- guest_information: GuestInfoModel
  - name: str
  - description: str
  - company: Optional[str]
  - product: Optional[str]

WEBPAGE SUMMARY (marketing/episode page):
--------------------
{webpage_summary}

FULL TRANSCRIPT:
--------------------
{full_transcript}

CRITICAL INSTRUCTIONS – SUMMARY (MOST IMPORTANT FIELD):

1. The `summary` field is the primary output for a vector database that will be indexed
   and split for semantic search. Treat it as an information-dense, multi-section summary
   of the episode.

2. As you summarize the transcript, imagine you are recursively compressing it into
   conceptual blocks. Whenever there is a clear switch in concept, conversation, or topic
   (e.g., new protocol, new case study, new mechanism, new company/product focus),
   insert the exact marker:

   <summary_break>

   Rules for using this marker:
   - Use **exactly** `<summary_break>` (no spaces, no capitalization changes, no extra characters).
   - Put it on its own line or directly between sections of text.
   - Use it ONLY inside the `summary` content, NEVER inside any guest_information fields.
   - Use it to separate coherent sections such as:
     - High-level episode overview
     - Specific protocols or interventions
     - Mechanisms/biological explanations
     - Case studies or anecdotes
     - Products/companies and their roles
     - Implementation advice or key takeaways

3. Within each section of the `summary`:
   - Emphasize how the content relates to human longevity, performance, and excellence
     (e.g., energy, cognition, recovery, resilience, metabolic health, biomarkers).
   - Be concrete and non-redundant.
   - Highlight protocols, tools, and principles listeners could apply in their lives.

Example conceptual shape of the `summary` string (this is just a shape, not literal text):

[Overview of the episode and main theme]
<summary_break>
[Discussion of key protocols, mechanisms, or frameworks]
<summary_break>
[Case studies, anecdotes, or notable experimental details]
<summary_break>
[Products/companies and how they fit into human upgrade]
<summary_break>
[Implementation tips and core takeaways for human performance and longevity]

GUEST INFORMATION (SECONDARY BUT REQUIRED):

4. The `guest_information` fields should be short, clean strings with **no** `<summary_break>`
   markers and no special formatting:

   - name:
     - Full name of the primary guest (the main expert Dave interviews).
   - description:
     - 1–2 sentence bio describing who they are and why they are relevant to this episode.
   - company:
     - Company or organization associated with the guest in this episode, if clearly mentioned.
   - product:
     - Key product, program, or offering associated with the guest in this episode, if clearly mentioned.

5. The guest information will often be easy to infer from:
   - The webpage summary, and/or
   - The beginning of the transcript where Dave introduces the guest.

   Use those sections first when identifying:
   - The guest's name
   - Their role, expertise, and affiliation
   - Any flagship product/program mentioned

TRUTHFULNESS CONSTRAINTS:

6. Do NOT invent facts that are not clearly supported by the webpage summary or transcript.
   - If company or product are not clearly supported, leave them empty.
   - If more than one guest appears, focus on the main expert Dave is interviewing.

YOUR TASK:

- Produce content that can be mapped into:
  - `summary`: a multi-section, information-dense summary of the episode that uses `<summary_break>`
    at concept/topic boundaries.
  - `guest_information`: clean, structured metadata about the main guest with no `<summary_break>`
    markers.

Remember: `<summary_break>` belongs ONLY inside the `summary` text and is critical for
downstream splitting and vectorization.
"""
)
