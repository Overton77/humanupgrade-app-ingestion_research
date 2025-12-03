from dotenv import load_dotenv
import os
import asyncio
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from uuid import uuid4
from typing import Optional, List, Dict, Any, Literal
from research_agent.output_models import GuestInfoModel, TranscriptSummaryOutput
from research_agent.prompts import summary_prompt, SUMMARY_SYSTEM_PROMPT
from pathlib import Path
import aiofiles


load_dotenv()

here = Path(__file__).resolve().parent    




transcript_file = here / "dev_env" / "data" / "full_transcript.txt"
webpage_summary_file = here / "dev_env" / "data" / "webpage_summary.txt"

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY") 



openai_search_tool = {"type": "web_search"}

summary_model = ChatOpenAI(
    model="gpt-5-nano", 
    reasoning_effort="medium", 
    temperature=0.0, 
    output_version="responses/v1",
    max_retries=2,
)

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# Low-level HTTP client for Qdrant
qdrant_http_client = QdrantClient(
    url=os.getenv("QDRANT_URL") or "http://localhost:6333",
    # api_key=os.getenv("QDRANT_API_KEY"),  
)

# LangChain vector store wrapper that KNOWS how to use embeddings on add_documents/aadd_documents
qdrant_vector_store = QdrantVectorStore(
    client=qdrant_http_client,
    collection_name="human-upgrade",
    embedding=embeddings,
)

summary_agent = create_agent(
    summary_model,
    system_prompt=SUMMARY_SYSTEM_PROMPT,
    response_format=TranscriptSummaryOutput,
)

SUMMARY_BREAK_REGEX = r"<summary_break/>"

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1200,
    chunk_overlap=150,
    separators=[SUMMARY_BREAK_REGEX, r"\n\n", r"\n", r" "],
    is_separator_regex=True,
)


async def summarize_transcript(
    webpage_summary_file_path: Path, transcript_file_path: Path
) -> TranscriptSummaryOutput:
    webpage_summary = webpage_summary_file_path.read_text(encoding="utf-8")
    print(f"Webpage summary: {webpage_summary[:50]}")

    full_transcript = transcript_file_path.read_text(encoding="utf-8")
    print(f"Full transcript: {full_transcript[:50]}")

    # Use the imported PromptTemplate to format the prompt
    formatted_summary_prompt = summary_prompt.format(
        webpage_summary=webpage_summary,
        full_transcript=full_transcript,
    )

    print("Summary prompt formatted, continuing to agent")

    summary_agent_response = await summary_agent.ainvoke(
        {"messages": [{"role": "user", "content": formatted_summary_prompt}]}
    )

    print("Summary agent finished")

    summary_output: TranscriptSummaryOutput = summary_agent_response[
        "structured_response"
    ]

    return summary_output


async def store_document_embeddings(
    summary_output: TranscriptSummaryOutput,
    splitter: RecursiveCharacterTextSplitter,
    vector_store: QdrantVectorStore,
    episode_number: int,
) -> List[Document]:
    summary_text = summary_output.summary

    docs = splitter.create_documents([summary_text]) 

    ids = [str(uuid4()) for _ in docs]   

    # Create metadata per chunk
    metadata = [
        {
            "guest_name": summary_output.guest_information.name,
            "episode_number": episode_number,
            "chunk_index": i,
        }
        for i in range(len(docs))
    ]

    docs = [
        Document(page_content=doc.page_content, metadata=meta)
        for doc, meta in zip(docs, metadata)
    ]

    print(f"Storing {len(docs)} documents for episode {episode_number}")

    await vector_store.aadd_documents(documents=docs, ids=ids)

    return docs


async def write_summary_outputs_to_fs(
    summary_output: TranscriptSummaryOutput,
    docs: List[Document],
    output_dir: Path,
    episode_number: int,
) -> None:
    """
    Write summary + guest info + chunked docs to the filesystem using aiofiles.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / f"episode_{episode_number}_summary.txt"
    guest_path = output_dir / f"episode_{episode_number}_guest.json"
    chunks_path = output_dir / f"episode_{episode_number}_chunks.txt"

    # Write raw summary (with <summary_break/> markers)
    async with aiofiles.open(summary_path, "w", encoding="utf-8") as f:
        await f.write(summary_output.summary)

    # Write guest info as JSON
    async with aiofiles.open(guest_path, "w", encoding="utf-8") as f:
        await f.write(summary_output.guest_information.model_dump_json(indent=2))

    # Write chunks (one after another, with separators for readability)
    async with aiofiles.open(chunks_path, "w", encoding="utf-8") as f:
        for idx, doc in enumerate(docs):
            await f.write(f"--- chunk {idx} ---\n")
            await f.write(doc.page_content)
            await f.write("\n\n")


async def main() -> None:
    # You can later parameterize this episode_number (CLI arg, env, etc.)
    episode_number = 1330

    # 1. Summarize transcript
    summary_output = await summarize_transcript(
        webpage_summary_file_path=webpage_summary_file,
        transcript_file_path=transcript_file,
    )

    # 2. Store document embeddings in Qdrant
    docs = await store_document_embeddings(
        summary_output=summary_output,
        splitter=splitter,
        vector_store=qdrant_vector_store,
        episode_number=episode_number,
    )

    # 3. Persist outputs to filesystem with aiofiles
    output_dir = here / "dev_env" / "outputs"
    await write_summary_outputs_to_fs(
        summary_output=summary_output,
        docs=docs,
        output_dir=output_dir,
        episode_number=episode_number,
    )

    print(f"Finished pipeline for episode {episode_number}")


if __name__ == "__main__":
    asyncio.run(main())






