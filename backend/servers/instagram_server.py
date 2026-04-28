import base64
from io import BytesIO
import logging
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv
import requests
import os
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

    
mcp = FastMCP("Instagram", port=8000)

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Instagram] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("instagram_server")

long_lived_token = os.getenv("long_lived_token")
ig_user_id = os.getenv("ig_user_id")

client = OpenAI()





@mcp.tool(name = "createImage")
def createImage(user_instrucion:str):
    """ This tool creates an image using DALL·E """
    logger.info("[createImage] TOOL CALLED — prompt=%r", user_instrucion)
    try:
        result = client.images.generate(
                model="dall-e-3",
                prompt=user_instrucion,
                size="1024x1024"
            )
    except Exception as e:
        logger.exception("[createImage] OpenAI image generation failed: %s", e)
        return {"success": False, "message": f"Image generation failed: {e}"}

    image_url = result.data[0].url
    if not image_url:
        logger.error("[createImage] No URL returned by OpenAI")
        return {
                "success" : False,
                "message" :"Image generation failed"
            }
    logger.info("[createImage] SUCCESS — url=%s", image_url)
    return image_url
    
@mcp.tool(name = "postImage")
def post_image(image_url):
    """
    This tool posts image on instagram based on it's link to Instagram.
    """
    logger.info("[postImage] TOOL CALLED — image_url=%s", image_url)
    try:       

        # 2️ Create media container
        media_url = f"https://graph.facebook.com/v17.0/{ig_user_id}/media"

        payload = {
            "image_url": image_url,
            "caption": "Sample content",
            "access_token": long_lived_token
        }

        logger.info("[postImage] Creating media container")
        response = requests.post(media_url, params=payload)
        data = response.json()
        logger.info("[postImage] Media container response status=%s", response.status_code)

        if "id" not in data:
            logger.error("[postImage] Failed to create media container: %s", data)
            return {
                "success" : False,
                "message" : f"Failed to create media container: {data}"
            }

        creation_id = data["id"]
        logger.info("[postImage] Media container created id=%s", creation_id)

        # 3️ Publish media
        publish_url = f"https://graph.facebook.com/v17.0/{ig_user_id}/media_publish"

        publish_payload = {
            "creation_id": creation_id,
            "access_token": long_lived_token
        }

        logger.info("[postImage] Publishing media")
        publish_response = requests.post(publish_url, params=publish_payload)
        publish_data = publish_response.json()
        logger.info("[postImage] Publish response status=%s", publish_response.status_code)

        if "id" not in publish_data:
            logger.error("[postImage] Failed to publish media: %s", publish_data)
            return {
                "success" : False,
                "message" : f"Failed to publish media: {publish_data}"
            }

        #  Success
        logger.info("[postImage] SUCCESS — published id=%s", publish_data.get("id"))
        return {
            "success" : True,
            "message" : "Image successfully posted to Instagram"
        }

    except Exception as e:
        logger.exception("[postImage] FAILED — %s", e)
        return {
            "success" : False,
            "message" : f"Unexpected error: {str(e)}"
        }

    

if __name__== "__main__":
    logger.info("Starting Instagram MCP server on port 8000")
    mcp.run(transport="streamable-http")