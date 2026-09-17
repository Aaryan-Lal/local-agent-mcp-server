# Design: Local Agentic GraphRAG Workspace

## Overview

This workspace runs a fully local, agentic Retrieval-Augmented Generation system. A Streamlit UI drives an agent (`AgenticWorkspace`) that reasons over a locally hosted LLM (Ollama / Llama 3.1) and calls out to an MCP server exposing your private knowledge base (a LlamaIndex GraphRAG index) as a tool. Nothing leaves the machine/LAN — no cloud LLM, no cloud vector store.

The mental model is **hand, brain, loop**:

- **The hand** (`app/knowledge_server.py`) — an MCP server. It can *act*: it reads the persisted index off disk and can query it. It has no judgment of its own; it just exposes capabilities as tools.
- **The brain** (`app/agent_orchestrator.py` → `AgenticWorkspace`) — talks to Ollama to decide what to do: call a tool, or answer directly.
- **The loop** — also `AgenticWorkspace`: repeatedly asks the brain for its next move, executes whatever the hand can do, feeds the result back, until the brain produces a final answer.

## Architecture Diagram

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

Note: two independent HTTP connections land on the same Ollama instance — one from `AgenticWorkspace` (tool-routing decisions, `temperature=0`), one from inside `knowledge_server.py` (RAG answer synthesis). The diagram draws a single Ollama box because it's the same physical model/server; the two callers just have different jobs.

## Sequence of a query

1. User types a question into the Streamlit UI (`app/gui.py`) and clicks **Run Agentic Search**.
2. `gui.py` calls `AgenticWorkspace.run_reasoning_loop(user_query)`.
3. `AgenticWorkspace` spawns `knowledge_server.py` as a subprocess and opens an MCP `ClientSession` over its stdin/stdout (JSON-RPC).
4. It calls `session.list_tools()` to discover the tool schema for `search_knowledge_graph` — tools are *discovered at runtime*, not hardcoded in the orchestrator.
5. It sends the conversation + tool schema to Ollama (brain call #1). Ollama either returns a final answer, or a `tool_calls` request.
6. If a tool call is requested, `AgenticWorkspace` invokes it via `session.call_tool(...)`. Inside `knowledge_server.py`, this loads the LlamaIndex `StorageContext` from `./storage`, builds a query engine, and calls `.query()` — which itself calls Ollama a second time (brain call #2) to embed the query and synthesize a natural-language answer from retrieved nodes.
7. The tool's text result is appended back into the conversation as a `role: tool` message.
8. The loop repeats (up to `MAX_STEPS = 8`): `AgenticWorkspace` calls Ollama again with the updated history. It can call the tool again, or stop and return a final answer.
9. The final answer propagates back up to `gui.py`, which renders it in the UI.

## Why MCP instead of a direct function call?

- **Process isolation** — the knowledge server crashing or hanging (e.g. a bad index file) doesn't take down the Streamlit process.
- **Standardized tool discovery** — `AgenticWorkspace` doesn't hardcode what `knowledge_server.py` can do; it asks at runtime via `list_tools()`. Adding a new tool to the server requires no orchestrator changes.
- **Reusability** — the same `knowledge_server.py` can be plugged into any MCP-speaking client (Claude Desktop, another agent), not just this Streamlit app.

## Design decisions & known gaps

- **`SimpleGraphStore`, not GraphDB.** `docker-compose.yml` still runs Ontotext GraphDB and WebProtégé containers, but `main.py`/`knowledge_server.py` currently persist to a flat-file `SimpleGraphStore` under `./storage`, not the real triple store. GraphDB/WebProtégé are provisioned but unused — a natural next step is swapping the graph store implementation.
- **No caching in `knowledge_server.py`.** `get_query_engine()` reloads the index from disk on every tool call. Fine for a demo-sized `./storage`; will get slow as the index grows.
- **Single tool today.** Only `search_knowledge_graph` is exposed. The loop structure (`MAX_STEPS`, repeated `list_tools()`/`call_tool()`) already supports adding more tools to `knowledge_server.py` without changing `agent_orchestrator.py`.
- **Hardcoded LAN Ollama endpoint.** `OLLAMA_URL` defaults to `http://192.168.0.32:11434` (set via `docker-compose.yml`), pointing at a natively-running Ollama app on the host Mac (for GPU/Metal acceleration) rather than the containerized `ollama` service — hence the `extra_hosts: host.docker.internal` entry in `docker-compose.yml`.

## Repo map

```
app/
├── main.py                # Ingestion: builds the LlamaIndex GraphRAG index from ./documents into ./storage
├── knowledge_server.py    # The hand: MCP server exposing search_knowledge_graph
├── agent_orchestrator.py  # The brain + loop: AgenticWorkspace
├── gui.py                 # The UI: Streamlit front end
├── requirements.txt
└── Dockerfile
docker-compose.yml          # graphdb, mongodb, webprotege, ollama, app services
documents/                   # Source text files to index
storage/                     # Generated index (gitignored, not committed)
```
