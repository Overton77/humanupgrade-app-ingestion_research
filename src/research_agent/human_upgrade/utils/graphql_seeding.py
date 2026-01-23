"""
Helper functions for seeding the database with extraction graph outputs.

These functions transform the structured extraction outputs into GraphQL mutations
to upsert businesses, products, compounds, and update episodes.
"""

from typing import Any, Dict, List, Optional
from graphql_client.client import Client
from graphql_client.input_types import (
    BusinessUpsertRelationFieldsInput,
    BusinessOwnerNestedInput,
    BusinessExecutiveNestedInput,
    BusinessExecutiveRelationInput,
    ProductUpsertRelationFieldsInput,
    ProductCompoundNestedInput,
    EpisodeUpdateRelationFieldsInput,
    MediaLinkInput,
)
from research_agent.clients.graphql_client import make_client_from_env


def _convert_media_links(media_links: Optional[List[Dict[str, Any]]]) -> List[MediaLinkInput]:
    """Convert media links from extraction format to GraphQL input format.
    
    Returns an empty list if no media links are provided (never returns None).
    """
    if not media_links:
        return []
    
    result = [
        MediaLinkInput(
            url=link.get("url", ""),
            description=link.get("label"),
            poster_url=None,  # Not in extraction output
        )
        for link in media_links
        if link.get("url")
    ]
    
    return result


async def upsert_business_with_relations(
    client: Client,
    business_data: Dict[str, Any],
    people_data: Optional[List[Dict[str, Any]]] = None,
    *,
    business_id: Optional[str] = None,
    business_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Upsert a Business with executives (no owners - that feature will be added later).
    
    Args:
        client: GraphQL client instance
        business_data: Business data from extraction (has canonical_name, description, website, media_links)
        people_data: List of people/executives from extraction
        business_id: Optional existing business ID to update
        business_name: Optional business name to identify existing business
        
    Returns:
        The upserted business data from GraphQL response
    """
    # Build executives nested input
    executives_nested: Optional[List[BusinessExecutiveNestedInput]] = None
    if people_data:
        executives_nested = []
        for person in people_data:
            if not person.get("canonical_name"):
                continue
            
            # Build executive input - only include media_links if it has values
            exec_input_dict: Dict[str, Any] = {
                "name": person.get("canonical_name"),
            }
            
            if person.get("role"):
                exec_input_dict["title"] = person.get("role")  # Using role as title
                exec_input_dict["role"] = person.get("role")
            
            exec_media_links = _convert_media_links(person.get("media_links"))
            if exec_media_links:
                exec_input_dict["media_links"] = exec_media_links
            
            executives_nested.append(BusinessExecutiveNestedInput(**exec_input_dict))
    
    # Get biography - use description if biography is None
    biography = business_data.get("biography")
    if not biography:
        biography = business_data.get("description")
    
    # Build business input - only include id if it's not None
    business_input_dict: Dict[str, Any] = {
        "name": business_name or business_data.get("canonical_name"),
    }
    
    # Only add optional fields if they have values
    if business_data.get("description"):
        business_input_dict["description"] = business_data.get("description")
    
    if business_data.get("website"):
        business_input_dict["website"] = business_data.get("website")
    
    if biography:
        business_input_dict["biography"] = biography
    
    media_links = _convert_media_links(business_data.get("media_links"))
    if media_links:
        business_input_dict["media_links"] = media_links
    
    if executives_nested:
        business_input_dict["executives_nested"] = executives_nested
    
    # Only add id if provided (don't pass None)
    if business_id is not None:
        business_input_dict["id"] = business_id
    
    business_input = BusinessUpsertRelationFieldsInput(**business_input_dict)
    
    # Execute mutation
    result = await client.upsert_business_with_relations(input=business_input)
    
    if not result.upsert_business_with_relations:
        raise ValueError("Failed to upsert business: no data returned")
    
    # Return the business data
    business = result.upsert_business_with_relations
    
    # Extract IDs for return
    return {
        "business_id": business.id,
        "business_name": business.name,
        "executive_ids": [
            exec.person.id for exec in (business.executives or [])
        ],
    }


async def upsert_products_with_compounds(
    client: Client,
    products_data: List[Dict[str, Any]],
    compounds_data: List[Dict[str, Any]],
    product_compound_links: List[Dict[str, Any]],
    business_id: str,
) -> List[Dict[str, Any]]:
    """
    Upsert Products with their associated Compounds.
    
    Args:
        client: GraphQL client instance
        products_data: List of product data from extraction
        compounds_data: List of compound data from extraction
        product_compound_links: Links between products and compounds
        business_id: The business ID that owns these products
        
    Returns:
        List of upserted product data with their IDs
    """
    # Create a map of compound entity_key to compound data
    compound_map = {
        compound.get("entity_key"): compound
        for compound in compounds_data
    }
    
    # Create a map of product entity_key to its linked compound entity_keys
    product_compound_map: Dict[str, List[str]] = {}
    for link in product_compound_links:
        product_key = link.get("product_entity_key")
        compound_key = link.get("compound_entity_key")
        if product_key and compound_key:
            if product_key not in product_compound_map:
                product_compound_map[product_key] = []
            product_compound_map[product_key].append(compound_key)
    
    results = []
    
    # Upsert each product with its compounds
    for product_data in products_data:
        product_key = product_data.get("entity_key")
        linked_compound_keys = product_compound_map.get(product_key, [])
        
        # Build compounds nested input for this product
        compounds_nested: Optional[List[ProductCompoundNestedInput]] = None
        if linked_compound_keys:
            compounds_nested = []
            for compound_key in linked_compound_keys:
                compound_data = compound_map.get(compound_key)
                if compound_data:
                    # Build compound input - only include media_links if it has values
                    compound_input_dict: Dict[str, Any] = {
                        "name": compound_data.get("canonical_name"),
                        "aliases": compound_data.get("aliases") or [],
                    }
                    
                    if compound_data.get("description"):
                        compound_input_dict["description"] = compound_data.get("description")
                    
                    compound_media_links = _convert_media_links(compound_data.get("media_links"))
                    if compound_media_links:
                        compound_input_dict["media_links"] = compound_media_links
                    
                    compounds_nested.append(ProductCompoundNestedInput(**compound_input_dict))
        
        # Convert price from string to float if needed
        price = product_data.get("price")
        if price is not None:
            if isinstance(price, str):
                try:
                    # Remove currency symbols and parse
                    price_clean = price.replace("$", "").replace(",", "").strip()
                    price = float(price_clean) if price_clean else None
                except (ValueError, AttributeError):
                    price = None
            elif not isinstance(price, (int, float)):
                price = None
        
        # Build product input - only include optional fields if they have values
        product_input_dict: Dict[str, Any] = {
            "name": product_data.get("canonical_name"),
            "business_id": business_id,
            "ingredients": product_data.get("ingredient_list") or [],
        }
        
        if product_data.get("description"):
            product_input_dict["description"] = product_data.get("description")
        
        if price is not None:
            product_input_dict["price"] = price
        
        if product_data.get("product_page_url"):
            product_input_dict["source_url"] = product_data.get("product_page_url")
        
        product_media_links = _convert_media_links(product_data.get("media_links"))
        if product_media_links:
            product_input_dict["media_links"] = product_media_links
        
        if compounds_nested:
            product_input_dict["compounds_nested"] = compounds_nested
        
        product_input = ProductUpsertRelationFieldsInput(**product_input_dict)
        
        # Execute mutation
        result = await client.upsert_product_with_relations(input=product_input)
        
        if not result.upsert_product_with_relations:
            raise ValueError(f"Failed to upsert product {product_data.get('canonical_name')}: no data returned")
        
        product = result.upsert_product_with_relations
        results.append({
            "product_id": product.id,
            "product_name": product.name,
            "compound_ids": [compound.id for compound in (product.compounds or [])],
        })
    
    return results


async def get_person_by_name(
    client: Client,
    name: str,
) -> Optional[str]:
    """
    Get a person ID by name, trying multiple case variations for robustness.
    
    Args:
        client: GraphQL client instance
        name: Person name to search for
        
    Returns:
        Person ID if found, None otherwise
    """
    if not name:
        return None
    
    # Try multiple name variations (case-insensitive search)
    name_variations = [
        name,  # Original
        name.lower(),  # lowercase
        name.title(),  # Title Case
        name.capitalize(),  # First letter capitalized
    ]
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for variation in name_variations:
        if variation not in seen:
            seen.add(variation)
            unique_variations.append(variation)
    
    # Try each variation
    for name_variant in unique_variations:
        try:
            result = await client.person_by_name(name=name_variant)
            if result.person_by_name:
                return result.person_by_name.id
        except Exception:
            # Continue to next variation
            continue
    
    return None


async def update_episode_with_guest(
    client: Client,
    guest_id: str,
    *,
    episode_id: Optional[str] = None,
    episode_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update an Episode to add the guest (person) ID.
    
    Args:
        client: GraphQL client instance
        guest_id: The person ID of the guest to add
        episode_id: Optional episode ID to update
        episode_url: Optional episode URL to identify the episode
        
    Returns:
        The updated episode data
    """
    if not episode_id and not episode_url:
        raise ValueError("Either episode_id or episode_url must be provided")
    
    # Build episode update input
    episode_input = EpisodeUpdateRelationFieldsInput(
        id=episode_id,
        episode_page_url=episode_url,
        guest_ids=[guest_id],  # Add the guest ID
    )
    
    # Execute mutation
    result = await client.update_episode_relations(input=episode_input)
    
    if not result.update_episode_relations:
        raise ValueError("Failed to update episode: no data returned")
    
    episode = result.update_episode_relations
    return {
        "episode_id": episode.id,
        "episode_title": episode.episode_title,
        "guest_ids": [guest.id for guest in (episode.guests or [])],
    }


async def seed_from_extraction_output(
    client: Client,
    guest_business_extraction: Dict[str, Any],
    product_compound_extraction: Dict[str, Any],
    *,
    episode_id: Optional[str] = None,
    episode_url: Optional[str] = None,
    business_id: Optional[str] = None,
    business_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Complete seeding workflow: upsert business, products, compounds, and update episode.
    
    This is a convenience function that orchestrates all the seeding operations.
    
    Args:
        client: GraphQL client instance (caller manages lifecycle)
        guest_business_extraction: Output from guest_business extraction
        product_compound_extraction: Output from product_compound extraction
        episode_id: Optional episode ID to update
        episode_url: Optional episode URL to identify the episode
        business_id: Optional existing business ID to update
        business_name: Optional business name to identify existing business
        
    Returns:
        Dictionary with all created/updated entity IDs
    """
    # Extract data
    guest_data = guest_business_extraction.get("guest")
    business_data = guest_business_extraction.get("business")
    people_data = guest_business_extraction.get("people", [])
    
    products_data = product_compound_extraction.get("products", [])
    compounds_data = product_compound_extraction.get("compounds", [])
    product_compound_links = product_compound_extraction.get("product_compound_links", [])
    
    # Step 1: Upsert business with executives (no owners for now)
    business_result = await upsert_business_with_relations(
        client=client,
        business_data=business_data,
        people_data=people_data,
        business_id=business_id,
        business_name=business_name,
    )
    
    # Step 2: Upsert products with compounds
    products_result = await upsert_products_with_compounds(
        client=client,
        products_data=products_data,
        compounds_data=compounds_data,
        product_compound_links=product_compound_links,
        business_id=business_result["business_id"],
    )
    
    # Step 3: Update episode with guest
    # Get guest ID by looking up guest by name
    guest_id = None
    if guest_data:
        guest_id = await get_person_by_name(
            client=client,
            name=guest_data.get("canonical_name", ""),
        )
    
    episode_result = None
    if guest_id and (episode_id or episode_url):
        episode_result = await update_episode_with_guest(
            client=client,
            guest_id=guest_id,
            episode_id=episode_id,
            episode_url=episode_url,
        )
    
    return {
        "business": business_result,
        "products": products_result,
        "episode": episode_result,
    }

