import os
from openai import OpenAI

# Load API key from environment (recommended way)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize the new OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Model name for your usage
MODEL_NAME = "gpt-4.1-nano"

