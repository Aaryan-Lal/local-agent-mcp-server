# Implementation Runbook

Follow these steps sequentially in **VS Code** to initialize the environment:

### Step 1: Spin Up Containers
Open a terminal inside the workspace directory and execute:
```bash
docker compose up -d graphdb mongodb webprotege ollama
```

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
