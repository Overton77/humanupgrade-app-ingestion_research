from __future__ import annotations

import os
from typing import Sequence, Type

from beanie import Document, init_beanie
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase  # type: ignore[import]  
from research_agent.infrastructure.storage.mongo.base_client import mongo_client 
from dotenv import load_dotenv 


from research_agent.models.mongo.candidates.docs.candidate_seeds import CandidateSeedDoc
from research_agent.models.mongo.candidates.docs.official_starter_sources import OfficialStarterSourcesDoc
from research_agent.models.mongo.domains.docs.domain_catalog_sets import DomainCatalogSetDoc
from research_agent.models.mongo.candidates.docs.connected_candidates import ConnectedCandidatesDoc
from research_agent.models.mongo.candidates.docs.candidate_sources_connected import CandidateSourcesConnectedDoc
from research_agent.models.mongo.entities.docs.candidate_runs import IntelCandidateRunDoc
from research_agent.models.mongo.entities.docs.candidate_entities import IntelCandidateEntityDoc
from research_agent.models.mongo.entities.docs.dedupe_groups import IntelDedupeGroupDoc
from research_agent.models.mongo.entities.docs.artifacts import IntelArtifactDoc
from research_agent.models.mongo.research.docs.research_runs import ResearchRunDoc
from research_agent.models.mongo.threads.docs.conversation_threads import ConversationThreadDoc



load_dotenv()  

MONGO_BIOTECH_DB_NAME = os.getenv("MONGO_BIOTECH_DB_NAME")





def get_document_models() -> Sequence[Type[Document]]:
    # Keep this centralized so app startup is deterministic.
    return [
        # Candidate graph outputs
        CandidateSeedDoc,
        OfficialStarterSourcesDoc,
        DomainCatalogSetDoc,
        ConnectedCandidatesDoc,
        CandidateSourcesConnectedDoc,
        # Optional legacy / core intel collections
        IntelCandidateRunDoc,
        IntelCandidateEntityDoc,
        IntelDedupeGroupDoc,
        IntelArtifactDoc,
        # Runs
        ResearchRunDoc,
        # Conversation threads (for coordinator agent)
        ConversationThreadDoc,
    ]


async def init_beanie_biotech_db(client: AsyncMongoClient) -> AsyncDatabase:
    db: AsyncDatabase = client[MONGO_BIOTECH_DB_NAME]
    await init_beanie(database=db, document_models=list(get_document_models()))
    return db