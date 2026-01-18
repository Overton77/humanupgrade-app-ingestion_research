from typing import List, Dict, Optional
from research_agent.human_upgrade.structured_outputs.candidates_outputs import (CandidateEntity, SeedExtraction, EntitySourceResult, CandidateSourcesConnected)
from research_agent.human_upgrade.structured_outputs.file_outputs import FileReference
from research_agent.agent_tools.filesystem_tools import read_file

def format_list_for_prompt(items: List[str], bullet: str = "-", empty_msg: str = "(none)") -> str:
    """Format a list of strings for prompt insertion."""
    if not items:
        return empty_msg
    return "\n".join(f"{bullet} {item}" for item in items)


def format_candidate_entity(entity: CandidateEntity) -> str:
    role_str = f" | Role: {entity.role}" if entity.role else ""
    snippets = (entity.contextSnippets or [])[:2]
    snippets_str = ""
    if snippets:
        snippets_str = "\n      Context: " + " | ".join(f'"{s.strip()}"' for s in snippets if s and s.strip())
    return (
        f"  • Name: {entity.name} | Type: {entity.typeHint} | Normalized: {entity.normalizedName}"
        f"{role_str} | Mentions: {entity.mentions}{snippets_str}"
    )

def format_seed_extraction_for_prompt(seed_extraction: Optional[SeedExtraction]) -> Dict[str, str]:
    if seed_extraction is None:
        return {
            "guest_candidates": "(none)",
            "business_candidates": "(none)",
            "product_candidates": "(none)",
            "platform_candidates": "(none)",
            "compound_candidates": "(none)",
            "evidence_claim_hooks": "(none)",
            "notes": "(none)",
        }

    def format_entity_list(entities: List[CandidateEntity]) -> str:
        if not entities:
            return "(none)"
        return "\n".join(format_candidate_entity(e) for e in entities)

    def format_hooks(hooks: List[str]) -> str:
        if not hooks:
            return "(none)"
        return "\n".join(f"  - {hook.strip()}" for hook in hooks if hook and hook.strip())

    return {
        "guest_candidates": format_entity_list(seed_extraction.guest_candidates),
        "business_candidates": format_entity_list(seed_extraction.business_candidates),
        "product_candidates": format_entity_list(seed_extraction.product_candidates),
        "platform_candidates": format_entity_list(seed_extraction.platform_candidates),
        "compound_candidates": format_entity_list(seed_extraction.compound_candidates),
        "evidence_claim_hooks": format_hooks(seed_extraction.evidence_claim_hooks),
        "notes": (seed_extraction.notes or "(none)").strip() or "(none)",
    }


def format_entity_source_result(entity: EntitySourceResult, indent: int = 4) -> str:
    """Format an EntitySourceResult for prompt display."""
    ind = " " * indent
    lines = [
        f"{ind}Name: {entity.inputName} (normalized: {entity.normalizedName})",
        f"{ind}Type: {entity.typeHint}",
    ]
    if entity.canonicalName:
        lines.append(f"{ind}Canonical: {entity.canonicalName} (confidence: {entity.canonicalConfidence:.2f})")
    
    if entity.candidates:
        lines.append(f"{ind}Sources ({len(entity.candidates)}):")
        for i, src in enumerate(entity.candidates[:3], 1):  # Show top 3 sources
            lines.append(f"{ind}  {i}. [{src.sourceType}] {src.label}")
            lines.append(f"{ind}     URL: {src.url}")
            lines.append(f"{ind}     Rank: {src.rank} | Score: {src.score:.2f} | Validation: {src.validationLevel}")
    
    if entity.notes:
        lines.append(f"{ind}Notes: {entity.notes}")
    
    return "\n".join(lines)


def format_connected_candidates_for_prompt(candidate_sources: Optional[CandidateSourcesConnected]) -> str:
    """Format ConnectedCandidates for the research directions prompt."""
    if candidate_sources is None or not candidate_sources.connected:
        return "(no connected candidates found)"
    
    lines: List[str] = []
    
    for bundle_idx, bundle in enumerate(candidate_sources.connected, 1):
        lines.append(f"\n{'='*80}")
        lines.append(f"CONNECTED BUNDLE #{bundle_idx}")
        lines.append(f"{'='*80}\n")
        
        # Guest
        lines.append("GUEST:")
        lines.append(format_entity_source_result(bundle.guest, indent=2))
        lines.append("")
        
        # Businesses
        if bundle.businesses:
            lines.append(f"BUSINESSES ({len(bundle.businesses)}):")
            for biz_idx, biz_bundle in enumerate(bundle.businesses, 1):
                lines.append(f"\n  Business #{biz_idx}:")
                lines.append(format_entity_source_result(biz_bundle.business, indent=4))
                
                # Products under this business
                if biz_bundle.products:
                    lines.append(f"\n    PRODUCTS ({len(biz_bundle.products)}):")
                    for prod_idx, prod_with_compounds in enumerate(biz_bundle.products, 1):
                        lines.append(f"\n      Product #{prod_idx}:")
                        lines.append(format_entity_source_result(prod_with_compounds.product, indent=8))
                        
                        # Compounds linked to this product
                        if prod_with_compounds.compounds:
                            lines.append(f"\n        COMPOUNDS ({len(prod_with_compounds.compounds)}):")
                            for comp_idx, compound in enumerate(prod_with_compounds.compounds, 1):
                                lines.append(f"\n          Compound #{comp_idx}:")
                                lines.append(format_entity_source_result(compound, indent=12))
                            
                            if prod_with_compounds.compoundLinkNotes:
                                lines.append(f"\n        Compound Link Notes: {prod_with_compounds.compoundLinkNotes}")
                                lines.append(f"        Compound Link Confidence: {prod_with_compounds.compoundLinkConfidence:.2f}")
                
                # Platforms under this business
                if biz_bundle.platforms:
                    lines.append(f"\n    PLATFORMS ({len(biz_bundle.platforms)}):")
                    for plat_idx, platform in enumerate(biz_bundle.platforms, 1):
                        lines.append(f"\n      Platform #{plat_idx}:")
                        lines.append(format_entity_source_result(platform, indent=8))
                
                if biz_bundle.notes:
                    lines.append(f"\n    Business Bundle Notes: {biz_bundle.notes}")
        
        if bundle.notes:
            lines.append(f"\n  Bundle Notes: {bundle.notes}")
    
    if candidate_sources.globalNotes:
        lines.append(f"\n{'='*80}")
        lines.append(f"GLOBAL NOTES:")
        lines.append(candidate_sources.globalNotes)
    
    return "\n".join(lines)



async def _concat_direction_files(file_refs: List[FileReference]) -> str:
    """
    Reads every file referenced in file_refs and concatenates them into one block
    with separators, including the file description (if present).
    """
    parts: List[str] = []
    for i, ref in enumerate(file_refs, start=1):
        path = ref.file_path
        desc = ref.description or ""
        parts.append(f"\n\n===== FILE {i}: {path} =====")
        if desc:
            parts.append(f"DESCRIPTION: {desc}")
        try:
            content = await read_file(path)
            parts.append(content)
        except Exception as e:
            parts.append(f"[ERROR READING FILE: {e}]")
    return "\n".join(parts).strip()