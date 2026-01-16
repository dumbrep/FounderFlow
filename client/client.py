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
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI


load_dotenv()


# api_key = os.getenv("GEMINI_API_KEY")

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# model =  ChatGoogleGenerativeAI(model="gemini-2.5-flash")
#model = ChatGroq(model="openai/gpt-oss-120b")
# model = ChatOllama(model="llama3")
model = ChatOpenAI(model="gpt-5.2")



async def main():
    client = MultiServerMCPClient({
    "Email": {
        "url": "http://localhost:8001/mcp",
        "transport": "streamable_http"
    },
    "Instagram": {
        "url": "http://localhost:8000/mcp",
        "transport": "streamable_http"
    }
})


    tools = await client.get_tools()
    # print("Available tools ", tools)
    agent = create_agent(
        model, tools
    )

    response = await agent.ainvoke(
        {
            "messages":[
                {
                    "role": "system",
                    "content": """You are an assistant that must always use available tools to complete tasks. 
                            You have given the user query, which you have to pass futher tools. Note that, all the tools are dependent on this query, so you have to pass deteailed query with them.

                            The description of the tools is as follows: 
                                1. Email Scheduling. 
                                    For email tasks, use the sendEmail tool and do not reply without using it.The name of the sender is Prajwal.

                                2. Meet Scheduling.
                                    For Meet Scheduling task, you have to choose scheduleMeet tool to schedule the meet. 
                                
                                3. Posting image on Instagram.
                                    For Posting image on Instagram, choose post_image tool
                            """
                },
                {
                    "role": "user",
                    "content": "Schedule meet with prerna for feature review. Her email id is satputeprerna71@gmail.com"
                }
            ]
        }
    )

    final_msg = next(
    (msg.content for msg in response['messages'] if isinstance(msg, AIMessage) and msg.content.strip()),
    None
    )

    print(final_msg)

    

asyncio.run(main())
