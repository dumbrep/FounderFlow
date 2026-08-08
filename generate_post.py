# # generate_post.py
# from openai import OpenAI
# import os

# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# client = OpenAI(api_key=OPENAI_API_KEY)

# def generate_linkedin_post(user_prompt):
#     """
#     Generates a LinkedIn-ready post based on user prompt
#     """
#     response = client.chat.completions.create(
#         model="gpt-4o-mini",
#         messages=[
#             {"role": "system", "content": "You are a professional LinkedIn content writer."},
#             {"role": "user", "content": user_prompt}
#         ],
#         temperature=0.7
#     )
#     return response.choices[0].message.content
# generate_post.py
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # 🔥 THIS WAS MISSING

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found. Check your .env file")

client = OpenAI(api_key=OPENAI_API_KEY)

def generate_linkedin_post(user_prompt):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a professional LinkedIn content writer."},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message.content
