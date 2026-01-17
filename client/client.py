from langchain_mcp_adapters.client import MultiServerMCPClient
#from langgraph.prebuilt import create_react_agent
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from dotenv import load_dotenv
import os
import asyncio
import json
import uuid
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from typing import TypedDict, Annotated
from langgraph.types import interrupt, Command


checkpointer = MemorySaver()

load_dotenv()


os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# model =  ChatGoogleGenerativeAI(model="gemini-2.5-flash")
#model = ChatGroq(model="openai/gpt-oss-120b")
# model = ChatOllama(model="llama3")

class AgentState(TypedDict):
    messages:  Annotated[list, add_messages]
    previous_draft: dict | None
    image_url : str | None

TOOL_STATE_MAP = {
    "composeEmail": "email_draft",
    "createImage": "image_url",
    "scheduleMeet": "meet_result",
}

TOOL_OUTPUT_TYPE = {
    "composeEmail": "json",
    "createImage": "json",
    "scheduleMeet": "json",
    "sendEmail": "text",
}


def get_tool_name(messages, tool_message: ToolMessage) -> str | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                if call["id"] == tool_message.tool_call_id:
                    return call["name"]
    return None

def extract_tool_payload(tool_name: str, content):
    if not isinstance(content, list) or not content:
        return None

    text = content[0].get("text", "").strip()

    if not text:
        return None

    if TOOL_OUTPUT_TYPE.get(tool_name) == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            print(f"[WARN] Invalid JSON from tool {tool_name}")
            print(text)
            return None

    # text output
    return text


def human_review(state: AgentState):
    last = state["messages"][-1]

    if isinstance(last, ToolMessage):
        print("\nPREVIEW OUTPUT")
        print(last.content)

        tool_name = get_tool_name(state["messages"], last)
        print("Resolved tool:", tool_name)

        target_state_key = TOOL_STATE_MAP.get(tool_name)

        payload = extract_tool_payload(tool_name, last.content)

        if target_state_key and payload is not None:
            state[target_state_key] = payload
            print(f"Stored output in state['{target_state_key}']")

        decision = input("Approve? (enter yes for final)").strip().lower()

        if decision == "yes":
            state["messages"].append(
                HumanMessage(content="Approved. Proceed with final actions")
            )
        else:
            state["messages"].append(
                HumanMessage(content=f"Revise based on this feedback: {decision}")
            )

    return state



async def main():
    client = MultiServerMCPClient(
        {
            "Email": {
                "url": "http://localhost:8001/mcp",
                "transport": "streamable_http"
            },
            "Meet_Schedule": {
                "url": "http://localhost:8002/mcp",
                "transport": "streamable_http"
            },
            "Instagram": {
                "url": "http://localhost:8000/mcp",
                "transport": "streamable_http"
            }
        }
    )

    tools = await client.get_tools()

    model = ChatOpenAI(
        model="gpt-5.2",
        temperature=0
    ).bind_tools(tools)

    async def agent_node(state: AgentState):
        response = await model.ainvoke(state["messages"])
        print(f"AGENT responce : \n {response.content}")
        state['messages'].append(response)
        return response

    tool_node = ToolNode(tools)

    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_node("human", human_review)

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools": "tools",
            END: END
        }
    )

    # graph.add_edge("tools", "agent")
    # graph.add_edge("agent", "human")
    graph.add_edge("tools", "human")
    graph.add_edge("human", "agent")

    app = graph.compile(checkpointer=checkpointer)

    SYSTEM_PROMPT = """
    You are an agent that MUST use tools.

    Email flow:
        - Call composeEmail first
        - Wait for human approval
        - If human needs some modification, send previous_draft with human feedback to composeEmail again. Do not forget to send previous draft
        - Then call sendEmail
    
    Meet Scheduling flow
        - Call scheduleMeet tool to schedule meet accorfing to user
    
    Image posting workflow
        - use createImage tool to create image
        - Wait for human approval
        - If human needs some changes, send human human feedback again to createImage tool
        - After confirmation, call postImage tool. postImage requires the image_url parameter

    Never respond with plain text if a tool can be used.
"""

    query = input("Enter your request: ")

    await app.ainvoke(
        {
            "messages": [
                HumanMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=query),
                AIMessage(content = "Excuting ")
            ]
        },
        config={"configurable": {"thread_id": "1"}}
    )

if __name__ == "__main__":
    asyncio.run(main())
