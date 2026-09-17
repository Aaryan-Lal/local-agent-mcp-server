import streamlit as st
import asyncio
import os
from agent_orchestrator import AgenticWorkspace

st.set_page_config(page_title="GraphRAG Agent Studio", page_icon="📚", layout="wide")
st.title("📚 My Private Agentic GraphRAG Knowledge Base")
st.markdown("---")

PERSIST_DIR = "./storage"
required_file = os.path.join(PERSIST_DIR, "docstore.json")

if not os.path.exists(required_file):
    st.warning("⚠ **Your database is currently empty!**")
    st.info("Please compile your documents first using your ingestion pipeline.")
else:
    agent_workspace = AgenticWorkspace(server_script="knowledge_server.py")
    user_query = st.text_input("Ask an intricate question about your documents:")

    if st.button("Run Agentic Search") and user_query:
        status_placeholder = st.empty()
        def update_status(text: str):
            status_placeholder.markdown(text)

        with st.spinner("Processing Agent reasoning blocks..."):
            answer = asyncio.run(
                agent_workspace.run_reasoning_loop(
                    user_query=user_query,
                    status_callback=update_status
                )
            )
            status_placeholder.empty()
            st.markdown("### 💬 System Answer:")
            st.info(answer)
