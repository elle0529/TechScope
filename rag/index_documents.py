#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from openai import OpenAI


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--jsonl", required=True)
    p.add_argument("--search-endpoint", required=True)
    p.add_argument("--index-name", required=True)
    p.add_argument("--openai-endpoint", required=True)
    p.add_argument("--embedding-deployment", required=True)
    args = p.parse_args()

    credential = DefaultAzureCredential()
    search = SearchClient(
        endpoint=args.search_endpoint,
        index_name=args.index_name,
        credential=credential,
    )
    token_provider = get_bearer_token_provider(
        credential,
        "https://ai.azure.com/.default",
    )
    openai = OpenAI(
        base_url=args.openai_endpoint.rstrip("/") + "/openai/v1/",
        api_key=token_provider,
    )

    docs = []
    for line in Path(args.jsonl).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        embedding = openai.embeddings.create(
            model=args.embedding_deployment,
            input=row["content"],
        ).data[0].embedding
        docs.append(
            {
                "chunk_id": row["chunk_id"],
                "content": row["content"],
                "source_id": row.get("source_id"),
                "technology": row.get("technology") or [],
                "technology_ids": row.get("technology_ids") or [],
                "category": row.get("category") or [],
                "architecture_layer": row.get("architecture_layer") or [],
                "evidence_type": row.get("evidence_type"),
                "company": row.get("company") or [],
                "content_vector": embedding,
            }
        )

    if not docs:
        raise SystemExit("No RAG documents found")

    result = search.upload_documents(documents=docs)
    failed = [x for x in result if not x.succeeded]
    if failed:
        raise SystemExit(f"Search upload failed for {len(failed)} documents")

    print(f"SEARCH_INDEX_UPLOAD=PASS DOCUMENTS={len(docs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
