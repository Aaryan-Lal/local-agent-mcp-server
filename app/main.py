import os
import sys
import logging
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import (
    SimpleDirectoryReader, 
    KnowledgeGraphIndex, 
    StorageContext,
    Settings
)
from llama_index.core.graph_stores import SimpleGraphStore

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# Fetch settings from your Docker environment variables
# OLLAMA_URL = os.getenv("OLLAMA_URL", "http://docker.internal")
# OLLAMA_URL = "http://docker.internal"
OLLAMA_URL = "http://192.168.0.32:11434"


print(f"🤖 [1/4] Connecting to Local Ollama Models at {OLLAMA_URL}...")

# FIX: Explicitly assign base_url inside the constructors
local_llm = Ollama(model="llama3.1", base_url=OLLAMA_URL, request_timeout=600.0)
local_embed = OllamaEmbedding(model_name="nomic-embed-text", base_url=OLLAMA_URL)

# Attach them directly to the global settings framework
Settings.llm = local_llm
Settings.embed_model = local_embed
Settings.chunk_size = 512

print("📁 [2/4] Reading local materials from documents volume...")
documents = SimpleDirectoryReader("./documents").load_data()

print("🔗 [3/4] Initialising Integrated File Graph Storage Engine...")
graph_store = SimpleGraphStore()
storage_context = StorageContext.from_defaults(graph_store=graph_store)

print("🚀 [4/4] Building Vector + Graph GraphRAG Index (Processing on M3 Pro)...")
# FIX: Inject them right into the index generator call
index = KnowledgeGraphIndex.from_documents(
    documents,
    storage_context=storage_context,
    llm=local_llm,
    embed_model=local_embed,
    max_triplets_per_chunk=5,
    include_embeddings=True
)

# Persist data
PERSIST_DIR = "./storage"
os.makedirs(PERSIST_DIR, exist_ok=True)
index.storage_context.persist(persist_dir=PERSIST_DIR)
print(f"💾 Knowledge base successfully compiled and saved to '{PERSIST_DIR}'!")

print("\n🚀 Executing System Verification Prompt...")
query_engine = index.as_query_engine(llm=local_llm, include_text=True, response_mode="tree_summarize")
response = query_engine.query("Summarise the key relationships found in these documents.")

print("\n================== GRAPH RAG SYSTEM OUTPUT ==================")
print(response)
print("=============================================================\n")
