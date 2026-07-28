"""Ingest approved documents into an Azure AI Search index (documents only).

This is the *document* knowledge source for the Foundry IQ build guide
(docs/student-service-assistant-v0.md). It intentionally does NOT crawl websites —
in that guide the web knowledge source is provided by Foundry IQ, not the index.
(For the combined docs + web-into-index pipeline, use scripts/ingest.py instead.)

Creates (or updates) the index and uploads chunked, embedded markdown documents
from ./data.

Run:
    python scripts/ingest_search.py

Auth uses DefaultAzureCredential (your `az login` identity locally / the CI identity).
Required env vars: AZURE_SEARCH_ENDPOINT, AZURE_OPENAI_ENDPOINT.
Optional: AZURE_SEARCH_INDEX (default "student-knowledge"),
          AZURE_OPENAI_EMBED_DEPLOYMENT (default "text-embedding-3-small"),
          AZURE_OPENAI_API_VERSION (default "2024-10-21").
"""
from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchableField,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from openai import AzureOpenAI

EMBED_DIM = 1536  # text-embedding-3-small

SEARCH_ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"]
INDEX_NAME = os.environ.get("AZURE_SEARCH_INDEX", "student-knowledge")
OPENAI_ENDPOINT = os.environ["AZURE_OPENAI_ENDPOINT"]
EMBED_DEPLOYMENT = os.environ.get("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small")
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

DATA_DIR = Path(__file__).parent.parent / "data"

credential = DefaultAzureCredential()
token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
aoai = AzureOpenAI(
    azure_endpoint=OPENAI_ENDPOINT,
    api_version=API_VERSION,
    azure_ad_token_provider=token_provider,
)


def create_index() -> None:
    client = SearchIndexClient(endpoint=SEARCH_ENDPOINT, credential=credential)
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="url", type=SearchFieldDataType.String),
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=EMBED_DIM,
            vector_search_profile_name="hnsw-profile",
        ),
    ]
    vector_search = VectorSearch(
        algorithms=[HnswAlgorithmConfiguration(name="hnsw-config")],
        profiles=[VectorSearchProfile(name="hnsw-profile", algorithm_configuration_name="hnsw-config")],
    )
    semantic_search = SemanticSearch(
        configurations=[
            SemanticConfiguration(
                name="semantic-config",
                prioritized_fields=SemanticPrioritizedFields(
                    title_field=SemanticField(field_name="title"),
                    content_fields=[SemanticField(field_name="content")],
                ),
            )
        ]
    )
    index = SearchIndex(
        name=INDEX_NAME,
        fields=fields,
        vector_search=vector_search,
        semantic_search=semantic_search,
    )
    client.create_or_update_index(index)
    print(f"Index '{INDEX_NAME}' created/updated.")


def chunk_text(text: str, max_words: int = 220) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, current, count = [], [], 0
    for para in paragraphs:
        words = len(para.split())
        if count + words > max_words and current:
            chunks.append("\n\n".join(current))
            current, count = [], 0
        current.append(para)
        count += words
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def embed(texts: list[str]) -> list[list[float]]:
    resp = aoai.embeddings.create(model=EMBED_DEPLOYMENT, input=texts)
    return [d.embedding for d in resp.data]


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Extract a leading `---` front-matter block of simple `key: value` lines."""
    if not text.startswith("---"):
        return {}, text
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, text[match.end():]


def load_documents() -> list[dict]:
    docs: list[dict] = []
    for path in sorted(DATA_DIR.glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        title = meta.get("title") or path.stem.replace("-", " ").title()
        url = meta.get("source_url", "")
        for i, chunk in enumerate(chunk_text(body)):
            docs.append({
                "id": f"doc-{path.stem}-{i}",
                "title": title,
                "content": chunk,
                "source": "document",
                "url": url,
            })
    print(f"Loaded {len(docs)} document chunks from {DATA_DIR}.")
    return docs


def upload(records: list[dict]) -> None:
    if not records:
        print("No documents to upload.")
        return
    client = SearchClient(endpoint=SEARCH_ENDPOINT, index_name=INDEX_NAME, credential=credential)
    batch_size = 16
    total = 0
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        vectors = embed([r["content"] for r in batch])
        payload = []
        for record, vector in zip(batch, vectors):
            payload.append({
                "id": record.get("id") or str(uuid.uuid4()),
                "title": record["title"],
                "content": record["content"],
                "source": record["source"],
                "url": record["url"],
                "contentVector": vector,
            })
        client.upload_documents(documents=payload)
        total += len(payload)
    print(f"Uploaded {total} chunks to '{INDEX_NAME}'.")


def main() -> None:
    create_index()
    upload(load_documents())
    print("Document ingestion complete.")


if __name__ == "__main__":
    try:
        main()
    except KeyError as exc:
        print(f"Missing environment variable: {exc}. Run inside `azd` or set values manually.")
        sys.exit(1)
