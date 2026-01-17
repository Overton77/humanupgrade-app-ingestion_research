import argparse
import json
import logging
from typing import Any, Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bedrock-model-list")


def list_foundation_models(bedrock_client) -> List[Dict[str, Any]]:
    """Return all foundation model summaries (handles pagination)."""
    models: List[Dict[str, Any]] = []
    token = None

    while True:
        kwargs = {}
        if token:
            kwargs["nextToken"] = token

        resp = bedrock_client.list_foundation_models(**kwargs)
        models.extend(resp.get("modelSummaries", []))
        token = resp.get("nextToken")

        if not token:
            break

    logger.info("Got %s foundation models.", len(models))
    return models


def classify_models(
    models: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Classify:
      - embedding models (outputModalities contains EMBEDDING)
      - frontier/generative models (everything else that can generate content)
      - unknown/other (catch-all)
    """
    embeddings: List[Dict[str, Any]] = []
    frontier: List[Dict[str, Any]] = []
    other: List[Dict[str, Any]] = []

    for m in models:
        out_mods = [x.upper() for x in (m.get("outputModalities") or [])]
        in_mods = [x.upper() for x in (m.get("inputModalities") or [])]

        is_embedding = "EMBEDDING" in out_mods
        # Generative models typically output TEXT/IMAGE/VIDEO (or similar), not EMBEDDING
        is_frontier = any(x in out_mods for x in ("TEXT", "IMAGE", "VIDEO")) and not is_embedding

        if is_embedding:
            embeddings.append(m)
        elif is_frontier:
            frontier.append(m)
        else:
            other.append(m)

    return embeddings, frontier, other


def model_line(m: Dict[str, Any]) -> str:
    model_id = m.get("modelId", "")
    name = m.get("modelName", "")
    provider = m.get("providerName", "")
    in_mods = ",".join(m.get("inputModalities") or [])
    out_mods = ",".join(m.get("outputModalities") or [])
    streaming = m.get("responseStreamingSupported", False)
    return f"{model_id} | {provider} | {name} | in=[{in_mods}] out=[{out_mods}] streaming={streaming}"


def print_group(title: str, models: List[Dict[str, Any]], show_json: bool) -> None:
    print("\n" + "=" * 100)
    print(f"{title} ({len(models)})")
    print("=" * 100)

    # Sort for stable output
    models_sorted = sorted(models, key=lambda x: (x.get("providerName", ""), x.get("modelId", "")))

    for m in models_sorted:
        print(model_line(m))
        if show_json:
            print(json.dumps(m, indent=2, sort_keys=True))
            print("-" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="List Amazon Bedrock foundation models by type.")
    parser.add_argument("--region", default="us-east-1", help="AWS region, e.g. us-east-1")
    parser.add_argument("--json", action="store_true", help="Print full JSON for each model")
    args = parser.parse_args()

    try:
        bedrock = boto3.client("bedrock", region_name=args.region)
        models = list_foundation_models(bedrock)
        embeddings, frontier, other = classify_models(models)

        print_group("Embedding models", embeddings, show_json=args.json)
        print_group("Frontier / generative models", frontier, show_json=args.json)

        # Optional: show anything that didn't match
        if other:
            print_group("Other / unclassified models", other, show_json=args.json)

        logger.info("Done.")

    except ClientError as e:
        logger.error("AWS ClientError: %s", e, exc_info=True)
        raise


if __name__ == "__main__":
    main()