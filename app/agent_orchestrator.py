"""The brain + the loop: decides what to do next and drives the reasoning cycle."""
import os
import sys

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
MAX_STEPS = 8
MAX_ANSWER_CHARS = 4000


class AgenticWorkspace:
    def __init__(self, server_script: str = "knowledge_server.py"):
        # Configure connection parameters to locate and boot the MCP Server
        self.server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_script],
        )
        self.client = ollama.Client(host=OLLAMA_URL)

    async def run_reasoning_loop(self, user_query: str, status_callback=None):
        """
        Executes the autonomous agent reasoning loop.
        status_callback is an optional function to update the Streamlit UI logs in real-time.
        """
        # 1. Connect to the local MCP Server via standard streams
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # 2. Discover Tools dynamically via the MCP framework
                mcp_tools = await session.list_tools()

                # Format the tools so they conform to Ollama's Chat API schema
                ollama_tools = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema,
                        },
                    }
                    for tool in mcp_tools.tools
                ]

                # Initialize conversational memory history
                messages = [{"role": "user", "content": user_query}]

                for _ in range(MAX_STEPS):
                    if status_callback:
                        status_callback("🧠 *Agent is analyzing intent and reviewing available tools...*")

                    # 3. Call The Brain (Ollama) to evaluate what action to take next
                    response = self.client.chat(
                        model=MODEL,
                        messages=messages,
                        tools=ollama_tools,
                        options={"temperature": 0.0},  # Force deterministic tool selection
                    )
                    message = response["message"]
                    messages.append(message)

                    # 4. Check if the Brain (Ollama) requested a tool execution
                    tool_calls = message.get("tool_calls")
                    if not tool_calls:
                        if status_callback:
                            status_callback("💡 *Answer formulated without requiring further tool calls.*")
                        return self._validate_answer(message.get("content"))

                    for tool_call in tool_calls:
                        tool_name = tool_call["function"]["name"]
                        tool_args = tool_call["function"]["arguments"]

                        if status_callback:
                            status_callback(f"🛠️ *Agent Decision: Invoking tool '{tool_name}' via MCP context window...*")

                        # Tool execution can fail (bad/hallucinated arguments, the tool's own
                        # internal error, a dead subprocess) - never let that crash the loop.
                        # A failure gets reported back to the model as a tool result instead,
                        # so it can retry, adjust arguments, or answer without the tool.
                        tool_output = await self._safe_call_tool(session, tool_name, tool_args)

                        messages.append(
                            {
                                "role": "tool",
                                "content": tool_output,
                                "name": tool_name,
                            }
                        )

                if status_callback:
                    status_callback("⚠️ *Gave up after too many reasoning steps.*")
                return "Gave up after too many steps without a final answer."

    @staticmethod
    async def _safe_call_tool(session: ClientSession, tool_name: str, tool_args) -> str:
        """Call an MCP tool, turning any failure into a plain-text tool result
        rather than an exception that would kill the whole reasoning loop."""
        if not isinstance(tool_args, dict):
            return f"Tool '{tool_name}' was skipped: arguments must be an object, got {type(tool_args).__name__}."
        try:
            tool_result = await session.call_tool(tool_name, arguments=tool_args)
        except Exception as exc:
            return f"Tool '{tool_name}' failed: {exc}"

        if not tool_result.content:
            return f"Tool '{tool_name}' returned no content."
        return tool_result.content[0].text

    @staticmethod
    def _validate_answer(content) -> str:
        """Guardrail on what actually reaches the UI: always a non-empty, bounded string."""
        if not isinstance(content, str) or not content.strip():
            return "The agent did not produce a usable answer."
        if len(content) > MAX_ANSWER_CHARS:
            return content[:MAX_ANSWER_CHARS] + "\n... (truncated)"
        return content
