# Local Agentic GraphRAG Workspace

A private, zero-cost, fully local **agentic GraphRAG** system running on Docker. It combines a Knowledge Graph + vector index over your own documents with a local LLM agent (via [Ollama](https://ollama.com) + [MCP](https://modelcontextprotocol.io)) that decides when to search that knowledge base and when to answer directly.

See [`DESIGN.md`](./DESIGN.md) for the full architecture write-up, sequence diagram, and design rationale.

## Architecture at a glance

```
┌────────────────────────────────────────────────────────────────────────┐
│                      YOUR USER INTERFACE LAYER                         │
│                                                                        │
│  ┌────────────────────────┐              ┌──────────────────────────┐  │
│  │      Streamlit UI      │ ◄──────────► │    AgenticWorkspace      │  │
│  │        (gui.py)        │              │  (agent_orchestrator.py) │  │
│  └────────────────────────┘              └────────────┬─────────────┘  │
└───────────────────────────────────────────────────────│────────────────┘
                                                         │
                                    JSON-RPC             │ (Python subprocess
                                    via Standard Streams │  IPC: stdio)
                                                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      MODEL CONTEXT PROTOCOL LAYER                      │
│                                                                        │
│                      ┌──────────────────────────┐                      │
│                      │     MCP SERVER FRAMEWORK │                      │
│                      │  (knowledge_server.py)   │                      │
│                      └────────────┬─────────────┘                      │
└───────────────────────────────────│────────────────────────────────────┘
                                     │
         ┌───────────────────────────┴───────────────────────────┐
         ▼ (Local File Read)                                     ▼ (HTTP / Port 11434)
┌──────────────────────────────┐                ┌──────────────────────────────┐
│    LOCAL DATABASE STORAGE    │                │        OLLAMA SERVER         │
│                              │                │                              │
│   ┌──────────────────────┐   │                │   ┌──────────────────────┐   │
│   │  ./storage directory │   │                │   │     LLM BRAIN        │   │
│   │  - docstore.json     │   │                │   │    (llama3.1)        │   │
│   │  - index_store.json  │   │                │   └──────────────────────┘   │
│   └──────────────────────┘   │                └──────────────────────────────┘
└──────────────────────────────┘
```

## Components

| Piece | Role | File |
|---|---|---|
| Streamlit UI | User-facing chat input | `app/gui.py` |
| Agent (brain + loop) | Decides tool calls, drives the reasoning loop | `app/agent_orchestrator.py` (`AgenticWorkspace`) |
| MCP server (hand) | Exposes the knowledge base as a callable tool | `app/knowledge_server.py` |
| Ingestion | Builds the GraphRAG index from `./documents` into `./storage` | `app/main.py` |
| Ollama | Local LLM (`llama3.1`) + embeddings (`nomic-embed-text`) | `docker-compose.yml` |
| GraphDB / WebProtégé | Provisioned for a real RDF triple store & ontology design; not yet wired into the pipeline (see `DESIGN.md`) | `docker-compose.yml` |

## Quick start

**1. Start the supporting services:**

```bash
docker compose up -d graphdb mongodb webprotege ollama
```

**2. Pull the model weights into Ollama:**

```bash
docker exec -it my-kb-ollama ollama run llama3.1
# once download reaches 100%, type /exit

docker exec -it my-kb-ollama ollama pull nomic-embed-text
```

**3. Configure the GraphDB repository:**

Open `http://localhost:7200` → **Setup → Repositories → Create new repository → GraphDB Repository**, set the Repository ID to `myknowledgebase`, and click **Create**.

**4. Add your documents and build the index:**

Drop text files into `./documents/`, then run:

```bash
docker compose run app python main.py
```

This populates `./storage` with the persisted GraphRAG index.

**5. Launch the agent:**

```bash
docker compose up app --build
```

Open `http://localhost:8501` and ask a question. The agent will decide whether to call `search_knowledge_graph` against your documents or answer directly.

## Configuration

- `OLLAMA_URL` (set in `docker-compose.yml`) — where the `app` container reaches Ollama. Defaults to a LAN IP for a natively-running Ollama app (for GPU acceleration); point it at `http://my-kb-ollama:11434` to use the containerized Ollama service instead.
- `OLLAMA_MODEL` (env var, read by `agent_orchestrator.py`) — override the model used for tool-routing decisions.

## Repo layout

```
app/
├── main.py                # Ingestion pipeline
├── knowledge_server.py    # MCP server (the hand)
├── agent_orchestrator.py  # AgenticWorkspace (the brain + loop)
├── gui.py                 # Streamlit UI
├── requirements.txt
└── Dockerfile
docker-compose.yml
documents/                  # Your source documents
storage/                    # Generated index (gitignored)
DESIGN.md                   # Full architecture write-up
```
