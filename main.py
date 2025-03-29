import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
api_key=os.getenv("GEMINI_API_KEY")

client = OpenAI(
    api_key=api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

response = client.chat.completions.create(
    model="gemini-2.0-flash",
    n=1,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": "hello, how are you"
        }
    ]
)

print(response.choices[0].message)
