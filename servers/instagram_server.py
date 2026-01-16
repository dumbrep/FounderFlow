import base64
from io import BytesIO
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv
import requests
import os
from mcp.server.fastmcp import FastMCP

from pydantic import BaseModel

class InstagramPostResponse(BaseModel):
    success: bool
    message: str

    
mcp = FastMCP("Instagram", port=8000)

load_dotenv()

long_lived_token = os.getenv("long_lived_token")
ig_user_id = os.getenv("ig_user_id")

client = OpenAI()

@mcp.tool()
def post_image(user_query: str) -> InstagramPostResponse:
    """
    This tool creates an image using DALL·E and posts it to Instagram.
    """
    try:
        # 1️ Generate image
        result = client.images.generate(
            model="dall-e-3",
            prompt=user_query,
            size="1024x1024"
        )

        image_url = result.data[0].url
        if not image_url:
            return InstagramPostResponse(
                success=False,
                message="Image generation failed"
            )

        # 2️ Create media container
        media_url = f"https://graph.facebook.com/v17.0/{ig_user_id}/media"

        payload = {
            "image_url": image_url,
            "caption": "Sample content",
            "access_token": long_lived_token
        }

        response = requests.post(media_url, params=payload)
        data = response.json()

        if "id" not in data:
            return InstagramPostResponse(
                success=False,
                message=f"Failed to create media container: {data}"
            )

        creation_id = data["id"]

        # 3️ Publish media
        publish_url = f"https://graph.facebook.com/v17.0/{ig_user_id}/media_publish"

        publish_payload = {
            "creation_id": creation_id,
            "access_token": long_lived_token
        }

        publish_response = requests.post(publish_url, params=publish_payload)
        publish_data = publish_response.json()

        if "id" not in publish_data:
            return InstagramPostResponse(
                success=False,
                message=f"Failed to publish media: {publish_data}"
            )

        #  Success
        return InstagramPostResponse(
            success=True,
            message="Image successfully posted to Instagram"
        )

    except Exception as e:
        return InstagramPostResponse(
            success=False,
            message=f"Unexpected error: {str(e)}"
        )

    

if __name__== "__main__":
    print("Starting MCP server with tools:")
    mcp.run(transport="streamable-http")