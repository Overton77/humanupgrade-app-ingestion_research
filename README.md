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

## AWS AgentCore Integration ⭐

This project is now integrated with **AWS AgentCore** for production deployment!

### Quick Start (5 minutes)

```bash
# 1. Test locally
python agentcore_entrypoint.py

# 2. Deploy to AWS
agentcore deploy

# 3. Invoke your agent
agentcore invoke '{"workflow": "full", "episode_url": "https://daveasprey.com/1296-qualia-greg-kelly/"}'
```

### Documentation

- 🚀 **[Quick Start Guide](AGENTCORE_QUICKSTART.md)** - Get started in 5 minutes
- 📖 **[Deployment Guide](AGENTCORE_DEPLOYMENT_GUIDE.md)** - Comprehensive deployment documentation
- 📊 **[Summary](AGENTCORE_SUMMARY.md)** - What's included and how it works
- ⚡ **[Cheat Sheet](AGENTCORE_CHEATSHEET.md)** - Quick reference for common commands
- 🔀 **[Multi-Project Guide](AGENTCORE_MULTI_PROJECT_GUIDE.md)** - When to split into multiple projects

### What You Get

- ✅ **One-command deployment** to AWS
- ✅ **Built-in memory & sessions** for tracking research across episodes
- ✅ **Auto-scaling** containers (ARM64/Graviton)
- ✅ **CloudWatch logging** + LangSmith tracing
- ✅ **API Gateway** with IAM authentication
- ✅ **Production-ready** infrastructure

### Make Commands

```bash
make -f Makefile.agentcore help          # Show all commands
make -f Makefile.agentcore deploy        # Deploy to AWS
make -f Makefile.agentcore invoke-test   # Test your deployment
make -f Makefile.agentcore logs          # View CloudWatch logs
```

## Status

✅ **Production Ready** - The system is fully integrated with AWS AgentCore and ready for deployment. Development continues for additional features.
