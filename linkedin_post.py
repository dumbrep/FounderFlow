# # linkedin_post.py
# import asyncio
# import json
# import os
# from fastmcp import Client
# from fastmcp.client.transports import StreamableHttpTransport

# MCP_API_KEY = os.getenv("MCP_API_KEY")
# MCP_SERVER_URL = "https://mcp.zapier.com/api/v1/connect"

# transport = StreamableHttpTransport(
#     MCP_SERVER_URL,
#     headers={"Authorization": f"Bearer {MCP_API_KEY}"}
# )
# client = Client(transport=transport)

# async def post_to_linkedin(comment, company_id="111128288"):
#     """
#     Sends a post to LinkedIn Company Page using MCP
#     """
#     async with client:
#         result = await client.call_tool(
#             "linkedin_create_company_update",
#             {
#                 "comment": comment,
#                 "company_id": company_id,
#                 "visibility__code": "PUBLIC"
#             }
#         )
#         return json.loads(result.content[0].text)

# 111128288

# linkedin_post.py
import json
import os
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

MCP_API_KEY = os.getenv("MCP_API_KEY")
MCP_SERVER_URL = "https://mcp.zapier.com/api/v1/connect"

if not MCP_API_KEY:
    raise ValueError("MCP_API_KEY not found")

async def post_to_linkedin(comment, company_id="111128288"):
    transport = StreamableHttpTransport(
        MCP_SERVER_URL,
        headers={"Authorization": f"Bearer {MCP_API_KEY}"}
    )

    client = Client(transport=transport)

    async with client:
        result = await client.call_tool(
            "linkedin_create_company_update",
            {
                "instructions": "Create a LinkedIn company page update",  # ✅ REQUIRED
                "comment": comment,
                "company_id": company_id,
                "visibility__code": "PUBLIC"
            }
        )

        return json.loads(result.content[0].text)
