# main.py
import asyncio
from generate_post import generate_linkedin_post
from linkedin_post import post_to_linkedin

async def main():
    user_prompt = input("Enter your LinkedIn post prompt: ")

    # Step 1: Generate post using AI
    post_content = generate_linkedin_post(user_prompt)
    print("\nGenerated Post:\n", post_content)

    # Step 2: Post to LinkedIn via MCP
    response = await post_to_linkedin(post_content)
    print("\nPosted Successfully:\n", response)

if __name__ == "__main__":
    asyncio.run(main())
