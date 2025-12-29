# Research Agent

A LangGraph-based research pipeline for processing podcast transcripts and conducting automated research on biotech topics.

## Overview

The Research Agent is part of the **Human Upgrade App** — a biotech knowledge, advice, and exploration system. It ingests podcast episode transcripts from "The Human Upgrade with Dave Asprey" and performs automated summarization and research.

## Architecture

The system consists of a main transcript graph that orchestrates the research pipeline:

1. **Transcript Summarization** - Extracts episode summaries, guest information, and attribution quotes
2. **Research Direction Generation** - Identifies key research questions and directions from the episode
3. **Research Execution** - Routes directions to specialized subgraphs:
   - **Evidence Research Subgraph** - Validates claims, explains mechanisms, profiles risk/benefits, and compares interventions
   - **Entity Intel Subgraph** - Conducts due diligence on people, businesses, products, and compounds

## Research Tools

Both subgraphs use a suite of research tools including:

- **Tavily** - Web search
- **Firecrawl** - Web scraping and URL mapping
- **PubMed** - Scientific literature search
- **Wikipedia** - Reference information

## Status

🚧 **In Progress** - The system runs successfully and performs summarization, evidence research, and entity research correctly, but development is ongoing.
