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
         ┌───────────────────────────┼───────────────────────────┐
         ▼ (Local File Read)         ▼ (SPARQL / Port 7200)      ▼ (HTTP / Port 11434)
┌──────────────────────────────┐  ┌──────────────────────┐  ┌──────────────────────────────┐
│    LOCAL DATABASE STORAGE    │  │  ONTOTEXT GRAPHDB     │  │        OLLAMA SERVER         │
│   ┌──────────────────────┐   │  │  repo: myknowledgebase│  │   ┌──────────────────────┐   │
│   │  ./storage directory │   │  │  entities & relations │  │   │     LLM BRAIN        │   │
│   │  - docstore.json     │   │  │  (RDF triples)        │  │   │    (llama3.1)        │   │
│   │  - index_store.json  │   │  └──────────────────────┘  │   └──────────────────────┘   │
│   └──────────────────────┘   │                             └──────────────────────────────┘
└──────────────────────────────┘
```

`search_knowledge_graph` is a **hybrid** tool: it queries the vector index (semantic similarity) and GraphDB (structural relationships) on every call and merges both into one answer. See [`DESIGN.md`](./DESIGN.md#hybrid-retrieval-how-triples-reach-graphdb) for why, and for the guardrails around it (SPARQL-injection escaping, tool-call error handling, output validation).

## Components

| Piece | Role | File |
|---|---|---|
| Streamlit UI | User-facing chat input | `app/gui.py` |
| Agent (brain + loop) | Decides tool calls, drives the reasoning loop, validates output | `app/agent_orchestrator.py` (`AgenticWorkspace`) |
| MCP server (hand) | Hybrid retrieval tool: vector search + GraphDB SPARQL | `app/knowledge_server.py` |
| Ingestion | Builds the vector/graph index from `./documents`, pushes triples into GraphDB | `app/main.py` |
| Shared helpers | URI/SPARQL utilities, incl. injection-safe escaping | `app/graphdb_utils.py` |
| Ollama | Local LLM (`llama3.1`) + embeddings (`nomic-embed-text`) | `docker-compose.yml` |
| GraphDB | Real RDF triple store holding extracted entities/relationships | `docker-compose.yml` |
| WebProtégé | Provisioned for ontology design; not yet wired into the pipeline (see `DESIGN.md`) | `docker-compose.yml` |

## Quick start

**1. Start the supporting services:**

```bash
docker compose up -d graphdb ollama
```

`mongodb`/`webprotege` are only needed for ontology design in WebProtégé and aren't used by ingestion or querying — skip them unless you're using that UI, especially on lower-RAM machines (running all four services plus Ollama's model can OOM-kill Ollama's `llama-server`; `docker-compose.yml` also caps GraphDB's JVM heap to 1GB to leave Ollama more headroom).

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

This populates `./storage` with the persisted vector/graph index, and pushes the extracted entities/relationships into GraphDB as RDF triples (viewable via GraphDB's workbench at `http://localhost:7200`).

**5. Launch the agent:**

```bash
docker compose up app --build
```

Open `http://localhost:8501` and ask a question. The agent will decide whether to call `search_knowledge_graph` against your documents or answer directly.

**Troubleshooting:** if `docker compose run`/`up` fails with `Conflict. The container name "..." is already in use`, a previous container was left behind. Run `docker compose down --remove-orphans` and retry.

## Configuration

- `OLLAMA_URL` (set in `docker-compose.yml`) — where the `app` container reaches Ollama. Defaults to a LAN IP for a natively-running Ollama app (for GPU acceleration); point it at `http://my-kb-ollama:11434` to use the containerized Ollama service instead.
- `OLLAMA_MODEL` (env var, read by `agent_orchestrator.py`) — override the model used for tool-routing decisions.

## Repo layout

```
app/
├── main.py                # Ingestion pipeline (builds index, pushes triples to GraphDB)
├── knowledge_server.py    # MCP server (the hand): hybrid vector + GraphDB search
├── agent_orchestrator.py  # AgenticWorkspace (the brain + loop), with guardrails
├── graphdb_utils.py        # Shared SPARQL/URI helpers (incl. injection escaping)
├── gui.py                 # Streamlit UI
├── requirements.txt
└── Dockerfile
docker-compose.yml
documents/                  # Your source documents
storage/                    # Generated index (gitignored)
DESIGN.md                   # Full architecture write-up
```
