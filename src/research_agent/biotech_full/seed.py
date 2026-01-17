import os
from dotenv import load_dotenv 
import asyncio 
load_dotenv()

from research_agent.biotech_full.graphql_seed_helpers import (
    make_client_from_env, 
    seed_from_directory,
    seed_one_entity_file
)

# Seed directory path
seed_dir = r"C:\Users\Pinda\Proyectos\humanupgradeapp\ingestion\src\research_agent\entities_seed"

# Individual seed file names
NATHAN_BRYAN = "nathan_bryan.json"
ENERGY_BITS = "energy_bits.json"
QUALIA = "qualia.json"
EWOT = "ewot.json"
BEN_AZADI = "ben_azadi.json"
ROXIVA = "roxiva.json"
VINIA = "vinia.json"
AURO_WELLNESS = "auro_wellness.json"
BIOLONGEVITY = "biolongevity.json"

# List of all seed files
ALL_SEED_FILES = [
    NATHAN_BRYAN,
    ENERGY_BITS,
    QUALIA,
    EWOT,
    BEN_AZADI,
    ROXIVA,
    VINIA,
    AURO_WELLNESS,
    BIOLONGEVITY,
]

gql = make_client_from_env()


async def seed_single_file(filename: str):
    """Seed a single entity file by filename."""
    print(f"Seeding {filename}...")
    result = await seed_one_entity_file(gql, filename)
    print(f"✓ Completed {filename}")
    print(f"  - Episode: {result.get('episode_url', 'N/A')}")
    print(f"  - Businesses: {len(result.get('businesses', []))}")
    print(f"  - People: {len(result.get('people', []))}")
    print(f"  - Products: {len(result.get('products', []))}")
    print(f"  - Case Studies: {len(result.get('case_studies', []))}")
    if result.get('skipped_products_no_business'):
        print(f"  - Skipped Products: {len(result['skipped_products_no_business'])}")
    return result


async def main(): 
    # To seed all files from directory:
    # df = await seed_from_directory(gql, seed_dir) 
    # return df
    
    # To seed a single file, uncomment one of these:
    # result = await seed_single_file(NATHAN_BRYAN)
    # result = await seed_single_file(ENERGY_BITS)
    # result = await seed_single_file(QUALIA)
    # result = await seed_single_file(EWOT)
    # result = await seed_single_file(BEN_AZADI)
    # result = await seed_single_file(ROXIVA)
    # result = await seed_single_file(VINIA)
    # result = await seed_single_file(AURO_WELLNESS)
    # result = await seed_single_file(BIOLONGEVITY)
    
    # To seed all files individually (one at a time):
    # for filename in ALL_SEED_FILES:
    #     await seed_single_file(filename)
    
    # return None 
    return None  

if __name__ == "__main__":
    asyncio.run(main())