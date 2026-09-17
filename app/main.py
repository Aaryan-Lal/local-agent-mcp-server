import os
import sys
import logging

import requests
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import (
    SimpleDirectoryReader,
    KnowledgeGraphIndex,
    StorageContext,
    Settings
)
from llama_index.core.graph_stores import SimpleGraphStore

from graphdb_utils import RESOURCE_NS, RELATION_NS, RDFS_NS, to_uri, escape_sparql_literal

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
GRAPHDB_URL = os.environ.get("GRAPHDB_URL", "http://localhost:7200")
GRAPHDB_REPOSITORY = os.environ.get("GRAPHDB_REPOSITORY", "myknowledgebase")


print(f"🤖 [1/5] Connecting to Local Ollama Models at {OLLAMA_URL}...")

local_llm = Ollama(model="llama3.1", base_url=OLLAMA_URL, request_timeout=600.0)
local_embed = OllamaEmbedding(model_name="nomic-embed-text", base_url=OLLAMA_URL)

Settings.llm = local_llm
Settings.embed_model = local_embed
Settings.chunk_size = 512

print("📁 [2/5] Reading local materials from documents volume...")
documents = SimpleDirectoryReader("./documents").load_data()

print("🔗 [3/5] Initialising Integrated File Graph Storage Engine...")
graph_store = SimpleGraphStore()
storage_context = StorageContext.from_defaults(graph_store=graph_store)

print("🚀 [4/5] Building Vector + Graph GraphRAG Index (Processing on M3 Pro)...")
index = KnowledgeGraphIndex.from_documents(
    documents,
    storage_context=storage_context,
    llm=local_llm,
    embed_model=local_embed,
    max_triplets_per_chunk=5,
    include_embeddings=True
)

PERSIST_DIR = "./storage"
os.makedirs(PERSIST_DIR, exist_ok=True)
index.storage_context.persist(persist_dir=PERSIST_DIR)
print(f"💾 Knowledge base successfully compiled and saved to '{PERSIST_DIR}'!")


def push_triplets_to_graphdb(graph_store, graphdb_url: str, repository: str) -> None:
    """Push extracted (subject, relation, object) triples into GraphDB as real RDF,
    so the knowledge graph is queryable via SPARQL, not just LlamaIndex's local file."""
    rel_map = graph_store.get_rel_map(subjs=None, depth=1, limit=10000)
    triples = [
        (subj, rel, obj)
        for subj, rel_obj_pairs in rel_map.items()
        for rel, obj in rel_obj_pairs
    ]

    if not triples:
        print("⚠️  No triplets were extracted; skipping GraphDB push.")
        return

    statements = []
    labeled_uris = set()
    for subj, rel, obj in triples:
        subj_uri = to_uri(RESOURCE_NS, subj)
        obj_uri = to_uri(RESOURCE_NS, obj)
        rel_uri = to_uri(RELATION_NS, rel)
        statements.append(f"{subj_uri} {rel_uri} {obj_uri} .")

        for node_uri, label in ((subj_uri, subj), (obj_uri, obj)):
            if node_uri not in labeled_uris:
                statements.append(f'{node_uri} rdfs:label "{escape_sparql_literal(label)}" .')
                labeled_uris.add(node_uri)

    update_query = (
        f"PREFIX rdfs: <{RDFS_NS}>\n"
        "INSERT DATA {\n" + "\n".join(statements) + "\n}"
    )

    response = requests.post(
        f"{graphdb_url}/repositories/{repository}/statements",
        data={"update": update_query},
        timeout=60,
    )
    response.raise_for_status()
    print(f"🔗 Pushed {len(triples)} triples into GraphDB repository '{repository}'.")


print(f"🔗 [5/5] Pushing extracted triples into GraphDB at {GRAPHDB_URL}...")
try:
    push_triplets_to_graphdb(graph_store, GRAPHDB_URL, GRAPHDB_REPOSITORY)
except requests.RequestException as exc:
    print(f"⚠️  Could not reach GraphDB ({exc}). Skipping graph push; vector index is still usable.")

print("\n🚀 Executing System Verification Prompt...")
query_engine = index.as_query_engine(llm=local_llm, include_text=True, response_mode="tree_summarize")
response = query_engine.query("Summarise the key relationships found in these documents.")

print("\n================== GRAPH RAG SYSTEM OUTPUT ==================")
print(response)
print("=============================================================\n")
