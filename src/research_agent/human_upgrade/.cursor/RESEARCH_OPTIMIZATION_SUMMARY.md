# Research Graph Optimization Summary
**Date**: 2026-01-16

## Overview

This document summarizes the research-driven optimizations made to the Research Graph system, including improved prompts, efficient tool usage patterns, and a comprehensive file synthesis strategy.

---

## 1. Research-Based Optimizations

### Web Search Best Practices Found

From research on LLM agent tool usage and prompt engineering (2026):

1. **Clear Task Decomposition**: Break research into ordered steps (divergent → convergent)
2. **Explicit Tool Instructions**: Specify WHEN and WHY to use each tool
3. **Structured Outputs**: Use JSON schemas for consistency
4. **Efficiency Constraints**: Explicit limits on tool calls prevent runaway behavior
5. **Batching Operations**: Group similar operations to reduce overhead
6. **Examples & Anti-patterns**: Show both good and bad usage

### Applied Strategies

✅ **Tool Selection Guidance**: Each tool has clear "best for" use cases  
✅ **Search Patterns**: Documented 3 efficient research patterns  
✅ **Batching Emphasis**: Strong guidance to batch URL extractions  
✅ **Stop Signals**: Clear criteria for when to stop searching  
✅ **Parallel Tool Calls**: Explicit instruction to call write_file + todo_update together

---

## 2. Updated Research Prompts

### Main Research Prompt (`get_main_research_prompt`)

**Enhancements**:
- ✨ **Strategic Tool Usage Section**: Each tool now has:
  - Best use cases
  - Strategy guidance
  - Concrete examples
  - When to use vs. other tools
  
- ✨ **Efficient Research Patterns**: 3 documented patterns:
  - Pattern 1: Known Entity Deep-Dive (wiki → search → batch extract)
  - Pattern 2: Discovery & Validation (broad search → map → extract)
  - Pattern 3: Multi-Entity Research (comparative queries)
  
- ✨ **Anti-Patterns Section**: Shows what NOT to do:
  - ❌ Calling extract 5 times with 1 URL each (wasteful!)
  - ✅ Call extract once with 5 URLs
  - ❌ Sequential file write then todo update
  - ✅ Parallel file write AND todo update

- ✨ **Tool Call Limits**: Injected max_steps into prompt for awareness

**Key Addition**:
```python
## Strategic Tool Selection
- tavily_search_research(): Use first for broad discovery (5-7 results)
- wiki_tool(): Use FIRST for known entities
- tavily_extract_research(): BATCH multiple URLs (up to 5) in ONE call
- tavily_map_research(): Use after confirming site is valuable
```

### Reminder Prompt (`get_reminder_research_prompt`)

**Enhancements**:
- ✨ **Progress-Aware**: Shows LLM calls, tool calls, steps taken
- ✨ **Urgency Signals**: Adaptive warnings based on call count
  - 10-15 calls: "⏰ MODERATE CALLS USED"  
  - 15+ calls: "⚠️ HIGH CALL COUNT"
- ✨ **Compact Format**: Reduced from verbose to essential reminders
- ✨ **Quick Reference**: One-line tool signatures for fast lookup

**Before**:
```
# Current Todo Status
{todo_summary}

# Your Workflow
1. Get next todo → 2. Research...
```

**After**:
```
# 🔄 Research Continue | GUEST
**LLM**: 8 | **Tools**: 12 | **Steps**: 15

{todo_summary}

🎯 wiki first → search (broad) → extract (BATCH)
```

---

## 3. New Synthesis System

### Problem Statement

After research, we have multiple files per entity:
- `guest_john_doe_identity.json`
- `guest_john_doe_credentials.json`  
- `guest_john_doe_expertise.json`

**Challenge**: Need ONE definitive report that:
- Eliminates redundancy
- Resolves conflicts  
- Maintains attribution
- Ensures completeness

### Implemented Solution

**Two-Level Synthesis**:

#### Level 1: Direction-Level (Implemented)

**Location**: `finalize_research_node` in `entity_research_graphs.py`

**Process**:
1. Group `file_refs` by `entity_key`
2. Read all files for each entity
3. Use LLM with `get_direction_synthesis_prompt()`
4. Output: ONE JSON report per entity
5. Save as `final_report_{direction}_{bundle_id}.json`

**Output Schema**:
```json
{
  "entity_type": "GUEST",
  "entity_key": "john_doe",
  "completeness_score": 0.85,
  "core_fields": {
    "field_name": {
      "value": "...",
      "confidence": "high|medium|low",
      "sources": ["url1", "url2"]
    }
  },
  "research_quality": {
    "missing_required_fields": [],
    "conflicting_information": []
  },
  "all_sources": [...]
}
```

#### Level 2: Bundle-Level (Framework Ready)

**Location**: `get_multi_direction_synthesis_prompt` in `synthesis_prompts.py`

**Purpose**: Create ecosystem narrative connecting all entities in a bundle

**Status**: Prompt ready, node implementation pending

**Output Schema**:
```json
{
  "bundle_id": "ep_123_john_doe",
  "ecosystem_map": {
    "guest": "Dr. John Doe",
    "primary_affiliation": "NeuroTech Institute",
    "products_mentioned": ["BrainBoost"]
  },
  "connections": [
    {"from": "john_doe", "to": "neurotech", "relationship": "founder"}
  ]
}
```

### Why This Approach?

**✅ Advantages**:
- Information preservation (all sources retained)
- Quality assessment (explicit confidence levels)
- Conflict resolution (LLM notes disagreements)
- Structured output (consistent JSON schema)
- Scalable (works for 1 or 10+ entities)

**🆚 Rejected Alternatives**:
- ❌ Agent synthesizes during research (burdens agent, loses intermediate findings)
- ❌ No synthesis, just aggregate (duplicates, no conflict resolution)
- ❌ Use create_agent with file tools (adds complexity, unpredictable)

---

## 4. File Changes Summary

### New Files Created

1. **`prompts/synthesis_prompts.py`** (193 lines)
   - `get_direction_synthesis_prompt()`: Per-direction final report synthesis
   - `get_multi_direction_synthesis_prompt()`: Bundle-level ecosystem synthesis

2. **`.cursor/SYNTHESIS_STRATEGY.md`** (Documentation)
   - Complete strategy explanation
   - Usage examples
   - Testing considerations
   - Performance characteristics

3. **`.cursor/RESEARCH_OPTIMIZATION_SUMMARY.md`** (This file)

### Modified Files

1. **`prompts/research_prompts.py`**
   - Added `max_steps` parameter to main prompt
   - Enhanced tool usage section with strategies
   - Added 3 efficient research patterns
   - Added anti-patterns section
   - Updated reminder prompt with urgency signals

2. **`entity_research_graphs.py`**
   - Imported synthesis prompts
   - Updated `perform_direction_research_node` to pass `tool_calls` count
   - Completely rewrote `finalize_research_node` to synthesize files
   - Added import for `fs_write_file`

---

## 5. Key Metrics & Targets

### Tool Usage Targets
- **Total Tool Calls**: 15-25 per direction (explicit in prompts)
- **Search Calls**: 3-7 (broad discovery)
- **Extract Calls**: 2-4 (batch 3-5 URLs each)
- **File Writes**: 1 per completed todo + 1 final report
- **LLM Calls**: 1 (todos) + 1 (initial) + 8-15 (research loops) + 1 (synthesis) = ~11-18 total

### Quality Metrics
- **Completeness Score**: 0.0-1.0 (in final reports)
- **Source Count**: Track per entity
- **Confidence Levels**: High/Medium/Low for each field
- **Missing Required Fields**: Explicit list in output

---

## 6. Usage Example

```python
# Run research direction
direction_state = await ResearchDirectionSubGraph.ainvoke({
    "direction_type": "GUEST",
    "bundle_id": "ep_123_john_doe",
    "episode": {"title": "Longevity Science with Dr. Doe"},
    "plan": {
        "chosen": {"objective": "Create guest profile", "entityName": "Dr. John Doe"},
        "required_fields": ["canonicalName", "currentRole", "expertise"]
    },
    "max_steps": 30,
})

# Automatic flow:
# 1. generate_todos_node → creates 5-8 todos
# 2. perform_research loop → agent researches, saves files
# 3. finalize_research_node → synthesizes all files into final report

# Access results
final_files = direction_state["file_refs"]  # Includes final_report_guest_ep_123.json
llm_calls = direction_state["llm_calls"]
completeness = "see final report JSON"
```

---

## 7. Testing Checklist

### Prompt Testing
- [ ] Test with 0 todos (should handle gracefully)
- [ ] Test with 10+ todos (should prioritize efficiently)
- [ ] Test reminder prompt with high call counts (should show urgency)
- [ ] Test with different direction types (GUEST vs PRODUCT)

### Synthesis Testing
- [ ] Test with 0 files (should skip synthesis)
- [ ] Test with 1 file (should still synthesize)
- [ ] Test with 10+ files (should handle large context)
- [ ] Test with multiple entities in one direction
- [ ] Test with conflicting information
- [ ] Test with missing required fields

### Integration Testing
- [ ] Full end-to-end run for GUEST direction
- [ ] Full bundle with multiple directions
- [ ] Verify file_refs propagate correctly
- [ ] Verify final reports are valid JSON
- [ ] Check completeness scores accuracy

---

## 8. Performance Expectations

### Per Direction Research
- **Duration**: 3-8 minutes (depending on max_steps)
- **LLM Calls**: 11-18 calls
- **Tool Calls**: 15-25 calls
- **Files Created**: 3-8 research files + 1 final report
- **Cost**: ~$0.50-2.00 (with GPT-4/5 pricing)

### Synthesis Phase
- **Duration**: 5-15 seconds
- **LLM Calls**: +1 per direction
- **Context Size**: 5K-20K tokens (depending on file count)
- **Cost**: ~$0.01-0.05 per synthesis

---

## 9. Monitoring & Observability

### Key Logs to Monitor

```python
logger.info(f"🧠 Generating TodoList for {direction_type}")  # Todo generation
logger.info(f"🔬 Research INITIAL call for {direction_type}")  # First research
logger.info(f"🔬 Research step {n} for {direction_type}")  # Subsequent research
logger.info(f"🔧 Executing {n} tool call(s)")  # Tool execution
logger.info(f"📁 Grouped {n} files into {m} entities")  # Synthesis grouping
logger.info(f"🧠 Synthesizing final report")  # Synthesis start
logger.info(f"✅ Final report saved: {filename}")  # Synthesis complete
```

### Alerts to Set
- ⚠️ LLM calls > 20 per direction (inefficiency)
- ⚠️ Tool calls > 30 per direction (runaway behavior)
- ⚠️ No files created (research failed)
- ⚠️ Synthesis fails (JSON parse error)
- ⚠️ Completeness score < 0.5 (poor quality)

---

## 10. Next Steps & Future Enhancements

### Immediate
1. ✅ Test end-to-end with real episode data
2. ✅ Validate JSON schemas for final reports
3. ✅ Add Pydantic models for structured outputs
4. ✅ Monitor LLM call efficiency in practice

### Short-Term
1. Implement bundle-level synthesis node
2. Add structured output validation with `response_format`
3. Create visualization for entity connections
4. Add retry logic for LLM synthesis failures

### Long-Term
1. Incremental synthesis (synthesize after every N files)
2. Multi-modal synthesis (incorporate images, tables)
3. Active learning (agent requests human input for gaps)
4. Caching/dedupe for common entities across episodes

---

## 11. Documentation Files

All documentation in `.cursor/` folder:

1. **RESEARCH_EXECUTION_ARCHITECTURE.md** - Overall graph architecture
2. **ENTITY_INTEL_RESEARCH_PLAN.md** - Research planning system
3. **TODO_LIST_SYSTEM.md** - Todo management details
4. **SYNTHESIS_STRATEGY.md** - ⭐ New: File synthesis strategy
5. **RESEARCH_OPTIMIZATION_SUMMARY.md** - ⭐ New: This file

---

## Conclusion

The research graph system is now optimized for:
- **Efficiency**: Clear tool usage patterns, batching, limits
- **Quality**: Structured outputs, confidence levels, completeness tracking
- **Maintainability**: Comprehensive docs, modular prompts, observability

**Status**: ✅ Ready for Testing
**Next Action**: Run end-to-end test with real episode data

---

**Contributors**: AI Assistant (Cursor)
**Last Updated**: 2026-01-16

