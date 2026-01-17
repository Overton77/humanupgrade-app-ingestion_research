from __future__ import annotations

from dotenv import load_dotenv
import os
import asyncio
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field 
from qdrant_client import QdrantClient, models
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from uuid import uuid4
from typing import List
from research_agent.retrieval.async_mongo_client import get_episodes_by_urls
from research_agent.retrieval.async_s3_client import get_transcript_text_from_s3_url
from pathlib import Path
import aiofiles 
from uuid import uuid4, uuid5, NAMESPACE_URL



from typing import Dict, Any, List, Optional
from pymongo import AsyncMongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId
from pymongo.asynchronous.database import AsyncDatabase  # type: ignore[import]
from pymongo.asynchronous.collection import AsyncCollection  # type: ignore[import]

load_dotenv()
here = Path(__file__).resolve().parent

# -------------------------
# MongoDB (PyMongo Async) - Faithful to your snippet
# ------------------------- 

COLLECTION_NAME=os.getenv("QDRANT_COLLECTION_NAME") or "human-upgrade"

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB_NAME = os.getenv("HU_DB_NAME") 



VECTOR_SIZE = 1536
DISTANCE = models.Distance.COSINE



def create_mongo_client() -> AsyncMongoClient:
    """
    Create an AsyncMongoClient.

    Keep this as a singleton at app level (e.g. FastAPI startup)
    and reuse it instead of creating a new one per request.
    """
    client: AsyncMongoClient = AsyncMongoClient(MONGO_URI)
    return client


def get_humanupgrade_db(client: AsyncMongoClient) -> AsyncDatabase:
    """
    Return the 'humanupgrade' AsyncDatabase from the given client.
    """
    db: AsyncDatabase = client[MONGO_DB_NAME]
    return db


_client: AsyncMongoClient = create_mongo_client()
_humanupgrade_db: AsyncDatabase = get_humanupgrade_db(_client)
episodes_collection: AsyncCollection = _humanupgrade_db["episodes"]

# -------------------------
# PROMPTS
# -------------------------

SUMMARY_SYSTEM_PROMPT = """
You are a Master Journalist and meticulous scientific editor working on a consumer biotech application.
Your job is to transform podcast episodes of "The Human Upgrade" into:
- faithful summaries,
- clear explanations,
- and verifiable context about guests, businesses, and products.

Core principles:
1) Faithfulness first:
   - Treat the transcript as primary source.
   - Do NOT invent details. If uncertain, say so explicitly.
   - Separate what was said in the episode vs what you found via web research.

2) Consumer clarity without losing accuracy:
   - Explain technical topics simply, but keep precise terms when needed.
   - When summarizing mechanisms, specify: intervention → proposed mechanism → outcome (as described).

3) Safety & responsibility:
   - No medical diagnosis. Avoid giving prescriptive medical instructions.
   - If discussing risks, contraindications, dosing, or treatment claims, attribute them to sources and use cautious language.

4) Web research behavior:
   - Use web search to confirm guest identity and affiliations (companies, products, roles, titles).
   - Prefer authoritative sources: official sites, institutional bios, reputable publications.
   - If sources disagree, report the disagreement rather than choosing arbitrarily.

5) Output formatting:
   - Follow the response format exactly when a structured schema is requested.
   - For article-style output, write in a polished, editorial voice: precise, readable, not hypey.
"""

class TranscriptSummaryOutput(BaseModel):
    initial_summary: str = Field(description="A detailed, structured summary of the episode content.")
    guest_overview: str = Field(description="A detailed, structured overview of the guest and their affiliations.")

initial_summary_and_guest_overview_prompt = """
You are producing a structured response using the TranscriptSummaryOutput schema.
Your output MUST contain exactly two fields:
- initial_summary
- guest_overview

General rules:
- The transcript is the primary source of truth.
- Do NOT fabricate information.
- Clearly distinguish transcript-derived information from web-researched information.
- Use web search ONLY for guest background and affiliations.

Context notes:
- The webpage summary contains enough guest information to guide web searches.
- The transcript contains the full episode content and may include speaker identifiers
  (e.g., Host vs Guest, or numbered speakers).

====================
CONTEXT
====================

<webpage_summary>
{webpage_summary}
</webpage_summary> 

** NOTE:  If <webpage_summary> is empty or missing:
- Infer the guest’s identity from the transcript (names, introductions, context clues).
- Then use web search to confirm the most likely match and retrieve affiliations.
- If multiple plausible matches exist, state the ambiguity and list the top candidates.

<full_transcript_text>
{transcript_text}
</full_transcript_text>

====================
TASKS
====================

A) INITIAL_SUMMARY (transcript-first, faithful) 
** These are important guidelines not hard rules **

- Write a detailed, information-dense structured summary of the episode content.
- Use the transcript as the ground truth.
- Include:
  * Key topics and themes
  * Main arguments and claims
  * Notable protocols, interventions, or practices discussed 
  * Notable Companies, Products and Brands mentioned 
  * Mechanisms described (as stated in the episode)
  * Evidence level when implied (e.g., anecdotal vs studies)
  * Any cautions, limitations, or uncertainties mentioned 
  

- Capture names of products, brands, organizations, people, compounds, biomarkers,
  and devices exactly as they appear.
- If claims are unclear or internally conflicting, explicitly note that.

B) GUEST_OVERVIEW (web-researched)

Use web search to verify and expand on the guest’s background:
- Full name and primary role/title
- Current and past affiliations (companies, labs, clinics, universities)
- Products or brands they are associated with
  (founder, co-founder, advisor, spokesperson, etc.)
- Public-facing references:
  * Official website
  * Company bio
  * LinkedIn
  * Wikipedia (if applicable)
  * Major interviews or publications

Guidelines:
- Prefer authoritative sources.
- If something cannot be verified, explicitly label it “Unverified”.
- Present findings as concise bullet points.
- Include lightweight source labels (domain + page name only; no URLs).

Return ONLY the structured fields required by TranscriptSummaryOutput:
- initial_summary
- guest_overview
"""

full_summary_prompt = """
You are producing a front-end ready article for a consumer biotech application.

General rules:
- Maintain a polished, editorial article voice.
- Be precise, clear, and non-hypey.
- Explain technical concepts in plain English while preserving correct terminology.
- Clearly distinguish between:
  * What was stated in the episode
  * What is added via web research

====================
CONTEXT
====================

<initial_summary>
{initial_summary}
</initial_summary>

<guest_overview>
{guest_overview}
</guest_overview>

====================
TASK
====================

Write a FRONT-END READY ARTICLE that a consumer can read.

Web search enhancement (minimally strategic):
- You have access to a web search tool.
- Use it selectively to:
  * Add brief explanatory context for key compounds, mechanisms, or concepts
  * Reference recent studies or developments relevant to major topics
  * Clarify technical details that improve reader understanding
  * Add clarity around products, companies, or brands mentioned
- Prefer recent, authoritative scientific or industry sources.
- Do NOT attempt exhaustive fact-checking.
- Integrate web-researched information naturally into the narrative.
- Always attribute web-researched information
  (e.g., “According to…”, “Research suggests…”).

====================
FORMAT & CONTENT REQUIREMENTS
====================

CRITICAL FORMATTING RULE:
- Insert the exact marker <summary_break/> on its own line:
  - Before EVERY major section
  - And at least every ~400–700 words in longer sections
(This is required for downstream splitting.)

The article must include:

1) Title (single line)
2) Dek / short introduction (2–4 sentences)
3) Sections with headings covering:
   - Who the guest is
     * Blend transcript information with web-verified background
     * Clearly label what is web-researched
   - What the episode is about (big-picture themes)
   - Deep dive on main interventions or ideas discussed
     * Include mechanisms as described in the episode
   - Evidence & uncertainty
     * What appears supported vs speculative
     * Attribute claims to the episode when appropriate
   - Practical takeaways
     * Bullet list
     * Cautious language
     * Include “discuss with a clinician” where appropriate
   - Products, brands, and companies mentioned
     * Bullet list
     * Note guest affiliations
     * Label “sponsor” if implied
   - Glossary
     * Short, plain-language definitions of key compounds,
       biomarkers, mechanisms, or terms

Claim handling:
- Phrase claims as:
  “In the episode, they claim/suggest…”
  unless independently verified via reputable sources.
- Do NOT introduce new medical claims beyond the provided inputs,
  except for widely accepted background facts (kept minimal).

Return ONLY the article text.
No JSON. No meta-commentary.
Remember: include <summary_break/> markers exactly as specified. 
Remember: your access to a web search tool
"""

# -------------------------
# MODELS / TOOLS
# -------------------------

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

openai_search_tool = {"type": "web_search"}

summary_model = ChatOpenAI(
    model="gpt-5-mini",
    reasoning_effort="medium",
    temperature=0.0,
    output_version="responses/v1",
    max_retries=2,
)

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")



# IMPORTANT: initial agent needs web search to enrich guest overview
summary_agent = create_agent(
    summary_model,
    tools=[openai_search_tool],
    system_prompt=SUMMARY_SYSTEM_PROMPT,
    response_format=TranscriptSummaryOutput,
) 


final_summary_agent = create_agent( 
    summary_model,
    tools=[openai_search_tool],
    system_prompt=SUMMARY_SYSTEM_PROMPT,
)

SUMMARY_BREAK_REGEX = r"<summary_break/>"

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=150,
    separators=[SUMMARY_BREAK_REGEX, r"\n\n", r"\n", r" "],
    is_separator_regex=True,
)

# -------------------------
# FILESYSTEM SAVE (transcript_runs)
# -------------------------

TRANSCRIPT_RUNS_DIR = here / "transcript_runs"


def _safe_slug(value: str) -> str:
    keep = []
    for ch in value.lower():
        if ch.isalnum():
            keep.append(ch)
        elif ch in ["-", "_"]:
            keep.append(ch)
        else:
            keep.append("-")
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")[:140] if slug else "episode"


async def save_initial_outputs_to_filesystem(
    episode_url: str,
    mongo_episode_id: str | None,
    initial_summary: str,
    guest_overview: str,
) -> None:
    TRANSCRIPT_RUNS_DIR.mkdir(parents=True, exist_ok=True)

    base = _safe_slug(episode_url)
    id_part = f"__{mongo_episode_id}" if mongo_episode_id else ""
    file_path = TRANSCRIPT_RUNS_DIR / f"{uuid4()}_{base}{id_part}__initial.txt"

    content = (
        f"episode_url: {episode_url}\n"
        f"mongo_episode_id: {mongo_episode_id}\n"
        "\n"
        "===== INITIAL_SUMMARY =====\n"
        f"{initial_summary.strip()}\n"
        "\n"
        "===== GUEST_OVERVIEW =====\n"
        f"{guest_overview.strip()}\n"
    )

    async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
        await f.write(content)


# -------------------------
# Mongo update
# -------------------------

async def update_episode_summary_detailed(
    mongo_episode_id: str,
    summary_detailed: str,
) -> None:
    """
    Save the final article-like summary into episode.summaryDetailed and persist to Mongo.
    """
    # Support either string ObjectId or already ObjectId-like values
    try:
        oid = ObjectId(mongo_episode_id)
    except (InvalidId, TypeError):
        # If your episode ids are not ObjectIds, fall back to direct match on _id
        oid = mongo_episode_id  # type: ignore[assignment]

    await episodes_collection.update_one(
        {"_id": oid},
        {"$set": {"summaryDetailed": summary_detailed}},
    )


# -------------------------
# PIPELINE
# -------------------------

async def summarize_transcript(transcript_text: str, webpage_summary: str) -> TranscriptSummaryOutput:
    formatted_prompt = initial_summary_and_guest_overview_prompt.format(
        webpage_summary=webpage_summary,
        transcript_text=transcript_text,
    )

    resp = await summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_prompt}]}
    )

    structured_response = resp["structured_response"] 

    return TranscriptSummaryOutput( 
        initial_summary=structured_response.initial_summary,
        guest_overview=structured_response.guest_overview,
    )


async def create_final_client_summary(initial_summary: str, guest_overview: str) -> str:
    formatted_prompt = full_summary_prompt.format(
        initial_summary=initial_summary,
        guest_overview=guest_overview,
    )

    resp = await final_summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_prompt}]}
    ) 

    # Extract the final text response from the agent
    # The final response is the last AIMessage that doesn't have tool_calls
    # (AIMessages with tool_calls are intermediate steps, not final responses)
    messages = resp.get("messages", [])
    
    # Iterate backwards to find the last AIMessage without tool calls
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            # Skip AIMessages with tool_calls - these are intermediate steps
            if message.tool_calls:
                continue
            # This is the final text response
            # Use .text property (extracts just text) or fallback to .content
            final_text = getattr(message, 'text', None) or message.content
            # Handle case where content might be a list (multimodal) or other types
            if isinstance(final_text, str):
                return final_text.strip()
            elif isinstance(final_text, list):
                # If content is a list (multimodal), extract text from content blocks
                text_parts = []
                for block in final_text:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        text_parts.append(block.get('text', ''))
                    elif isinstance(block, str):
                        text_parts.append(block)
                return ' '.join(text_parts).strip() if text_parts else ''
            else:
                return str(final_text).strip()
    
    # Fallback: if no AIMessage found, try the last message's content
    if messages:
        last_msg = messages[-1]
        final_text = getattr(last_msg, 'text', None) or getattr(last_msg, 'content', None)
        if isinstance(final_text, str):
            return final_text.strip()
        return str(final_text).strip() if final_text else ''
    
    # Ultimate fallback
    raise ValueError("No valid response found in agent output")


async def create_final_client_summary_text(initial_summary: str, guest_overview: str) -> str:
    formatted_prompt = full_summary_prompt.format(
        initial_summary=initial_summary,
        guest_overview=guest_overview,
    )

    resp = await final_summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_prompt}]}
    ) 

    final_message = resp["messages"][-1] 

    final_text = final_message.text  

    return final_text 
    
    
   



async def run_summarization_and_storage(episode_urls: list[str]):
    episodes = await get_episodes_by_urls(episode_urls)

    for ep in episodes:
        episode_url = ep.get("episodePageUrl") or ""
        s3_url = ep.get("s3TranscriptUrl") or ""
        mongo_episode_id = ep.get("_id") or ""
        webpage_summary = ep.get("webPageSummary") or ""  # optional; may not exist

        # Only skip if transcript is missing
        if not s3_url:
            print(f"Skipping {episode_url or '[unknown episode url]'}: missing s3TranscriptUrl")
            continue

        # episode_url is still useful for metadata/logging; but do NOT skip the run
        if not episode_url:
            print("Warning: missing episodePageUrl on record (continuing anyway)")

        transcript_text = await get_transcript_text_from_s3_url(s3_url)

        summary_output = await summarize_transcript(
            transcript_text=transcript_text,
            webpage_summary=webpage_summary,
        )

        await save_initial_outputs_to_filesystem(
            episode_url=episode_url,
            mongo_episode_id=str(mongo_episode_id) if mongo_episode_id is not None else None,
            initial_summary=summary_output.initial_summary,
            guest_overview=summary_output.guest_overview,
        )

        final_summary_text = await create_final_client_summary(
            initial_summary=summary_output.initial_summary,
            guest_overview=summary_output.guest_overview,
        )

        if mongo_episode_id is not None:
            await update_episode_summary_detailed(
                mongo_episode_id=str(mongo_episode_id),
                summary_detailed=final_summary_text,
            )
        else:
            print(f"Warning: no mongo episode id for {episode_url}, skipping Mongo update")

       

        print(f"Done: {episode_url}")


episode_urls: list[str] = [
    "https://daveasprey.com/1303-nayan-patel/",
    "https://daveasprey.com/1302-nathan-bryan/",
    "https://daveasprey.com/1301-ewot/",
    "https://daveasprey.com/1296-qualia-greg-kelly/",
    "https://daveasprey.com/1295-ben-azadi/",
    "https://daveasprey.com/1293-darin-olien/",
    "https://daveasprey.com/1292-amitay-eshel-young-goose/",
    "https://daveasprey.com/1291-mte-jeff-boyd/",
    "https://daveasprey.com/1289-josh-axe/",
    "https://daveasprey.com/1330-energybits/",
    "https://daveasprey.com/1327-jim-murphy/",
    "https://daveasprey.com/1323-sulforaphane-curcumin-and-new-glp-1-drugs-biohacking-for-longevity/",
    "https://daveasprey.com/1315-stemregen/",
    "https://daveasprey.com/1311-biolongevity-labs/",
    "https://daveasprey.com/1352-roxiva/",
    "https://daveasprey.com/1353-vinia-bioharvest/",
]


# remaining_episode_urls: list[str] = [
#     "https://daveasprey.com/1330-energybits/",
#     "https://daveasprey.com/1327-jim-murphy/",
#     "https://daveasprey.com/1323-sulforaphane-curcumin-and-new-glp-1-drugs-biohacking-for-longevity/",
#     "https://daveasprey.com/1315-stemregen/",
#     "https://daveasprey.com/1311-biolongevity-labs/",
#     "https://daveasprey.com/1352-roxiva/",
#     "https://daveasprey.com/1353-vinia-bioharvest/",
# ]
if __name__ == "__main__":
    # asyncio.run(run_summarization_and_storage(episode_urls)) 

    final_result = asyncio.run(create_final_client_summary_text("Here is an initial summary. Please just respond logically", "No guest here just respond logically. Testing output")) 
    print(final_result)