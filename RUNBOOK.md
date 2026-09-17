# Implementation Runbook

Follow these steps sequentially in **VS Code** to initialize the environment:

### Step 1: Spin Up Containers
Open a terminal inside the workspace directory and execute:
```bash
docker compose up -d graphdb ollama
```

`mongodb`/`webprotege` are only needed for ontology design work in WebProtégé — skip them for ingestion/querying to leave more RAM for Ollama. Start them separately (`docker compose up -d mongodb webprotege`) only when you actually need the WebProtégé UI. On machines with limited RAM (e.g. 16-18GB), running all four services plus Ollama's model at once can starve Ollama's `llama-server` process and cause it to be OOM-killed mid-request.

### Step 2: Download AI Model Weights (Free & Local)
Run the following commands to download the models into the local Ollama volume storage:
```bash
# Pull the reasoning LLM (Llama 3.1 8B)
docker exec -it my-kb-ollama ollama run llama3.1

# (Once download reaches 100%, type /exit to leave the chat prompt)

# Pull the high-performance embedding engine
docker exec -it my-kb-ollama ollama pull nomic-embed-text
```

### Step 3: Configure Your GraphDB Repository
1. Open your browser and navigate to `http://localhost:7200`.
2. Go to **Setup** -> **Repositories** -> **Create new repository**.
3. Select **GraphDB Repository**.
4. Set the **Repository ID** exactly to: `myknowledgebase`
5. Click **Create**.

### Step 4: Load Documents and Ingest
1. Add text files or PDFs to the `./documents/` folder.
2. Trigger the automated Python extraction engine:
```bash
docker compose up app --build
```
