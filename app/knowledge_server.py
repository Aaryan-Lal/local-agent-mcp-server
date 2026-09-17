"""The hand: an MCP server exposing your local GraphRAG index as a tool."""
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import StorageContext, load_index_from_storage, Settings

mcp = FastMCP("GraphRAG-Knowledge-Server")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
Settings.llm = Ollama(model="llama3.1", base_url=OLLAMA_URL, request_timeout=600.0)
Settings.embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url=OLLAMA_URL)

PERSIST_DIR = Path(__file__).parent / "storage"


def get_query_engine():
    """Validates the local database files and spins up the search engine."""
    required_file = PERSIST_DIR / "docstore.json"
    if not required_file.exists():
        return None
    storage_context = StorageContext.from_defaults(persist_dir=str(PERSIST_DIR))
    index = load_index_from_storage(storage_context)
    return index.as_query_engine(include_text=True, response_mode="tree_summarize")


@mcp.tool()
def search_knowledge_graph(query: str) -> str:
    """
    Searches your private GraphRAG knowledge base for intricate document details,
    deep entities, structural nodes, and conceptual connections.
    """
    engine = get_query_engine()
    if not engine:
        return "Error: The knowledge database files are empty or missing."

    response = engine.query(query)
    return str(response)


if __name__ == "__main__":
    mcp.run(transport="stdio")
