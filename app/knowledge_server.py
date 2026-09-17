"""The hand: an MCP server exposing hybrid retrieval (vector + graph) over your local GraphRAG index."""
import os
from pathlib import Path

import requests
from mcp.server.fastmcp import FastMCP
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import StorageContext, load_index_from_storage, Settings

from graphdb_utils import RELATION_NS, RDFS_NS, escape_sparql_literal

mcp = FastMCP("GraphRAG-Knowledge-Server")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
GRAPHDB_URL = os.environ.get("GRAPHDB_URL", "http://localhost:7200")
GRAPHDB_REPOSITORY = os.environ.get("GRAPHDB_REPOSITORY", "myknowledgebase")

Settings.llm = Ollama(model="llama3.1", base_url=OLLAMA_URL, request_timeout=600.0)
Settings.embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url=OLLAMA_URL)

PERSIST_DIR = Path(__file__).parent / "storage"
MAX_ANSWER_CHARS = 4000


def get_query_engine():
    """Validates the local database files and spins up the semantic search engine."""
    required_file = PERSIST_DIR / "docstore.json"
    if not required_file.exists():
        return None
    storage_context = StorageContext.from_defaults(persist_dir=str(PERSIST_DIR))
    index = load_index_from_storage(storage_context)
    return index.as_query_engine(include_text=True, response_mode="tree_summarize")


def query_graphdb(query: str, limit: int = 15) -> list[str]:
    """Search GraphDB for entities/relationships whose labels mention the query.

    The query text is escaped before being embedded in the SPARQL string
    literal (SPARQL-injection guardrail) rather than concatenated raw.
    """
    escaped = escape_sparql_literal(query.strip().lower())
    sparql = f"""
PREFIX rdfs: <{RDFS_NS}>
SELECT ?subjLabel ?relLabel ?objLabel WHERE {{
  ?subj ?rel ?obj .
  ?subj rdfs:label ?subjLabel .
  ?obj rdfs:label ?objLabel .
  BIND(STRAFTER(STR(?rel), "{RELATION_NS}") AS ?relLabel)
  FILTER(CONTAINS(LCASE(STR(?subjLabel)), "{escaped}") || CONTAINS(LCASE(STR(?objLabel)), "{escaped}"))
}}
LIMIT {int(limit)}
"""
    response = requests.get(
        f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPOSITORY}",
        params={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
        timeout=30,
    )
    response.raise_for_status()
    bindings = response.json()["results"]["bindings"]
    return [
        f"{b['subjLabel']['value']} --[{b['relLabel']['value']}]--> {b['objLabel']['value']}"
        for b in bindings
    ]


@mcp.tool()
def search_knowledge_graph(query: str) -> str:
    """
    Searches your private GraphRAG knowledge base for intricate document details,
    deep entities, structural nodes, and conceptual connections. Combines semantic
    (vector) search with graph relationship lookups in GraphDB.
    """
    if not isinstance(query, str) or not query.strip():
        return "Error: query must be a non-empty string."

    vector_answer = None
    try:
        engine = get_query_engine()
        if engine:
            vector_answer = str(engine.query(query))
    except Exception as exc:
        vector_answer = f"(semantic search failed: {exc})"

    try:
        relationships = query_graphdb(query)
    except Exception as exc:
        relationships = [f"(relationship search failed: {exc})"]

    if not vector_answer and not relationships:
        return "Error: no knowledge sources are available yet. Build the index and populate GraphDB first."

    parts = []
    if vector_answer:
        parts.append(f"Semantic answer:\n{vector_answer}")
    if relationships:
        parts.append("Related facts from the knowledge graph:\n" + "\n".join(relationships))

    result = "\n\n".join(parts)
    if len(result) > MAX_ANSWER_CHARS:
        result = result[:MAX_ANSWER_CHARS] + "\n... (truncated)"
    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
