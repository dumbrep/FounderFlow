

import os
import json
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.client import Client
from fastmcp.client.transports import StreamableHttpTransport
from openai import OpenAI

load_dotenv()

mcp = FastMCP("LinkedIn", port=8003)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MCP_API_KEY = os.getenv("MCP_API_KEY")
MCP_SERVER_URL = "https://mcp.zapier.com/api/v1/connect"

ai_client = OpenAI(api_key=OPENAI_API_KEY)

@mcp.tool(name="generateLinkedInPost")
def generate_linkedin_post(user_prompt: str):
    response = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a professional LinkedIn content writer."},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )

    return {
        "success": True,
        "content": response.choices[0].message.content
    }


@mcp.tool(name="postLinkedIn")
async def post_linkedin(post_content: str, company_id: str = "111128288"):

    transport = StreamableHttpTransport(
        MCP_SERVER_URL,
        headers={"Authorization": f"Bearer {MCP_API_KEY}"}
    )

    client = Client(transport=transport)

    async with client:
        result = await client.call_tool(
            "linkedin_create_company_update",
            {
                "instructions": "Create a LinkedIn company page update",
                "comment": post_content,
                "company_id": company_id,
                "visibility__code": "PUBLIC"
            }
        )

    return {
        "success": True,
        "message": "Posted successfully to LinkedIn"
    }
if __name__ == "__main__":
    print("Starting LinkedIn MCP server...")
    mcp.run(transport="streamable-http")
