import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()


async def test_openai_api():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found in .env file")
        return

    client = AsyncOpenAI(api_key=api_key)

    test_prompt = """
    You are a travel planner for Southeast Asia. Provide a brief 3-day itinerary for a trip to Taiwan focusing on food and culture.
    """

    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",  # Use gpt-4 if your key supports it
            messages=[
                {"role": "system", "content": "You are a travel planning assistant."},
                {"role": "user", "content": test_prompt},
            ],
            max_tokens=200,
        )
        print("API Response:")
        print(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_openai_api())
