from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

for model in client.models.list().data:
    print(model.id)