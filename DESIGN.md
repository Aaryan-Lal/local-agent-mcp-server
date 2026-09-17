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
         ┌───────────────────────────┼───────────────────────────┐
         ▼ (Local File Read)         ▼ (SPARQL / Port 7200)      ▼ (HTTP / Port 11434)
┌──────────────────────────────┐  ┌──────────────────────┐  ┌──────────────────────────────┐
│    LOCAL DATABASE STORAGE    │  │  ONTOTEXT GRAPHDB     │  │        OLLAMA SERVER         │
│                              │  │  (RDF triple store)   │  │                              │
│   ┌──────────────────────┐   │  │  repo: myknowledgebase│  │   ┌──────────────────────┐   │
│   │  ./storage directory │   │  │  entities/relations   │  │   │     LLM BRAIN        │   │
│   │  - docstore.json     │   │  │  as rdfs:label'd URIs │  │   │    (llama3.1)        │   │
│   │  - index_store.json  │   │  └──────────────────────┘  │   └──────────────────────┘   │
│   └──────────────────────┘   │                             └──────────────────────────────┘
└──────────────────────────────┘
```

`search_knowledge_graph` queries **both** the local vector index and GraphDB on every call and merges the results — see "Hybrid retrieval" below.

Note: two independent HTTP connections land on the same Ollama instance — one from `AgenticWorkspace` (tool-routing decisions, `temperature=0`), one from inside `knowledge_server.py` (RAG answer synthesis). The diagram draws a single Ollama box because it's the same physical model/server; the two callers just have different jobs.

## Sequence of a query

1. User types a question into the Streamlit UI (`app/gui.py`) and clicks **Run Agentic Search**.
2. `gui.py` calls `AgenticWorkspace.run_reasoning_loop(user_query)`.
3. `AgenticWorkspace` spawns `knowledge_server.py` as a subprocess and opens an MCP `ClientSession` over its stdin/stdout (JSON-RPC).
4. It calls `session.list_tools()` to discover the tool schema for `search_knowledge_graph` — tools are *discovered at runtime*, not hardcoded in the orchestrator.
5. It sends the conversation + tool schema to Ollama (brain call #1). Ollama either returns a final answer, or a `tool_calls` request.
6. If a tool call is requested, `AgenticWorkspace` invokes it via `session.call_tool(...)`. Inside `knowledge_server.py`, `search_knowledge_graph` does two lookups in parallel intent (sequentially in code, but independent of each other):
   - **Semantic:** loads the LlamaIndex `StorageContext` from `./storage`, builds a query engine, and calls `.query()` — which itself calls Ollama a second time (brain call #2) to embed the query and synthesize a natural-language answer from retrieved nodes.
   - **Relational:** runs a SPARQL `SELECT` against GraphDB, matching the query text against entity `rdfs:label`s, returning `subject --[relation]--> object` facts.

   Both results are merged into one string. Either side failing (GraphDB down, empty index) degrades gracefully instead of failing the whole tool call — see "Guardrails" below.
7. The tool's merged text result is appended back into the conversation as a `role: tool` message.
8. The loop repeats (up to `MAX_STEPS = 8`): `AgenticWorkspace` calls Ollama again with the updated history. It can call the tool again, or stop and return a final answer.
9. The final answer propagates back up to `gui.py`, which renders it in the UI.

## Hybrid retrieval: how triples reach GraphDB

`app/main.py` (ingestion) builds the same `KnowledgeGraphIndex` as before — LlamaIndex extracts `(subject, relation, object)` triplets from `./documents` via the LLM into a `SimpleGraphStore` — but now also pushes those triplets into GraphDB as real RDF, via `app/graphdb_utils.py`:

- Each entity becomes a URI under `http://local-kb.example/resource/<slug>`, each relation a URI under `http://local-kb.example/relation/<slug>`.
- An `rdfs:label` triple is attached to every entity URI holding its original readable text, so results stay human-readable.
- The whole batch is sent as one SPARQL `INSERT DATA` to `{GRAPHDB_URL}/repositories/{GRAPHDB_REPOSITORY}/statements`.

At query time, `knowledge_server.py`'s `query_graphdb()` runs a SPARQL `SELECT` with a `CONTAINS(LCASE(...))` filter against those labels — a simple substring match, not true semantic search (that's what the vector side is for).

## Why MCP instead of a direct function call?

- **Process isolation** — the knowledge server crashing or hanging (e.g. a bad index file) doesn't take down the Streamlit process.
- **Standardized tool discovery** — `AgenticWorkspace` doesn't hardcode what `knowledge_server.py` can do; it asks at runtime via `list_tools()`. Adding a new tool to the server requires no orchestrator changes.
- **Reusability** — the same `knowledge_server.py` can be plugged into any MCP-speaking client (Claude Desktop, another agent), not just this Streamlit app.

## Guardrails

- **SPARQL injection.** `query_graphdb()` never concatenates raw user text into a SPARQL string. `graphdb_utils.escape_sparql_literal()` escapes backslashes, quotes, and newlines before the query text is embedded in a double-quoted string literal.
- **Tool-call failures don't crash the loop.** `AgenticWorkspace._safe_call_tool()` wraps `session.call_tool(...)`: malformed arguments (not a dict), an unreachable GraphDB, a missing index, or any other exception is turned into a plain-text tool result fed back to the model, instead of an uncaught exception killing the reasoning loop / Streamlit request.
- **Defense in depth on the hand side too.** Inside `search_knowledge_graph`, the vector lookup and the GraphDB lookup are each wrapped independently — one failing (e.g. GraphDB down) doesn't prevent the other from returning results.
- **Output validation.** `AgenticWorkspace._validate_answer()` guarantees the final answer handed to the UI is always a non-empty string, capped at `MAX_ANSWER_CHARS` (4000). `search_knowledge_graph` applies the same cap to its own merged result before returning it to the model.
- **Not covered (deliberately, for now):** no auth on GraphDB/Streamlit/Ollama/WebProtégé — all four are unauthenticated on the LAN. Fine for a private home network; would need addressing before exposing this beyond that.

## Design decisions & known gaps

- **No caching in `knowledge_server.py`.** `get_query_engine()` reloads the index from disk on every tool call. Fine for a demo-sized `./storage`; will get slow as the index grows.
- **No entity resolution in GraphDB.** Triples are pushed as-is from LLM extraction; "Eve" and "eve" collapse to the same URI (good), but "Eve" and "Dr. Eve" would not (no fuzzy entity linking).
- **GraphDB relationship search is substring matching, not semantic.** `CONTAINS(LCASE(...))` on labels — the vector side is what handles paraphrased/fuzzy questions.
- **Single tool today.** Only `search_knowledge_graph` is exposed. The loop structure (`MAX_STEPS`, repeated `list_tools()`/`call_tool()`) already supports adding more tools to `knowledge_server.py` without changing `agent_orchestrator.py`.
- **Hardcoded LAN Ollama endpoint.** `OLLAMA_URL` defaults to `http://192.168.0.32:11434` (set via `docker-compose.yml`), pointing at a natively-running Ollama app on the host Mac (for GPU/Metal acceleration) rather than the containerized `ollama` service — hence the `extra_hosts: host.docker.internal` entry in `docker-compose.yml`.

## Repo map

```
app/
├── main.py                # Ingestion: builds the index from ./documents, pushes triples into GraphDB
├── knowledge_server.py    # The hand: MCP server exposing search_knowledge_graph (vector + GraphDB)
├── agent_orchestrator.py  # The brain + loop: AgenticWorkspace, with tool-call/output guardrails
├── graphdb_utils.py        # Shared SPARQL/URI helpers, incl. injection-safe escaping
├── gui.py                 # The UI: Streamlit front end
├── requirements.txt
└── Dockerfile
docker-compose.yml          # graphdb, mongodb, webprotege, ollama, app services
documents/                   # Source text files to index
storage/                     # Generated index (gitignored, not committed)
```
