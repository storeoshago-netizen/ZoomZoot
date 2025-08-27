from openai import AsyncOpenAI
from core.config import settings
from core.logging import logger
import json
import datetime


# get this year
current_year = datetime.datetime.now().year


async def create_day_by_day_itinerary(summary: str) -> str:
    """Generate a day-by-day itinerary from a trip summary string.

    The `summary` parameter should follow the format produced by the chat assistant,
    for example:
    "Summary: Destination: Sri Lanka, Duration: 10 days, Dates: 20 August, Preferences: Mountains, Flight Needs: Yes, Origin: Chennai, Hotel Needs: Yes, Special Requirements: None"

    Returns a plain-text itinerary with one numbered day per line-block including
    morning/afternoon/evening suggestions, approximate durations, and short notes
    about transport or accommodations where appropriate.
    """

    logger.info("Generating day-by-day itinerary from summary")

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
    )

    system_prompt = f"""Current year is {current_year}
You are TripPlanner, an expert travel itinerary generator that creates beautifully formatted markdown documents.

CRITICAL OUTPUT REQUIREMENT: Return ONLY a single, valid JSON object with exactly two keys: 'response' and 'days'.

RESPONSE CONTENT STRUCTURE - CLEAN MARKDOWN FORMAT:
The 'response' field must contain well-structured markdown text following this EXACT format:

# ✈️ Flight Information
- **Book Your Flight:** [✈️ Book Flight](flight_url_here)

# 📅 Your Travel Itinerary

## Day 1 — Location Name

### 🌅 Morning
Detailed morning activities and recommendations with natural flowing text.

### ☀️ Afternoon  
Detailed afternoon activities and recommendations with natural flowing text.

### 🌆 Evening
Detailed evening activities and recommendations with natural flowing text.

### 🏨 Accommodation
**Overnight in:** City Name
- **Book Hotel:** [🏨 Hotel Name](hotel_booking_url)

---

## Day 2 — Location Name
(Continue same format for each day)

MARKDOWN FORMATTING RULES:
- Use # for main sections (Flight Info, Itinerary)
- Use ## for day headers with — separator and location
- Use ### for time periods with proper emoji icons
- Use **bold** for important labels like "Book Your Flight:", "Overnight in:"
- Use [Link Text](URL) format for all clickable links
- Use --- as horizontal dividers between days
- Write content as flowing paragraphs, NOT bullet points
- Only use bullet points for booking links

FLIGHT DETAILS:
- Always include flight section at the top with ✈️ emoji
- Construct URLs: https://www.aviasales.com/search/[ORIGIN][DDMM][DEST][DDMM]?marker=659627&currency=USD
- Use IATA airport codes and 2-digit day/month format based on: {summary}
- Format as: [✈️ Book Flight](URL)

CONTENT REQUIREMENTS:
- Each day should have 100+ words of detailed, helpful content
- Write activities as natural paragraphs, not bullet lists
- Include specific attractions, activities, and practical details
- Provide clear timing and logistics information
- Add accommodation recommendations with booking links
- Use natural, flowing prose

DAYS MAPPING REQUIREMENTS:
- 'days' must be an object mapping each day number to hotel booking details
- Each day must include: HOTEL_CHECKIN, HOTEL_CHECKOUT, and HOTEL_DESTINATION
- Use format: {{"Day 1": {{"HOTEL_CHECKIN": "YYYY-MM-DD", "HOTEL_CHECKOUT": "YYYY-MM-DD", "HOTEL_DESTINATION": "CityName"}}}}
- Calculate dates based on the trip start date and duration from the summary
- For multi-night stays, keep same destination but adjust checkout dates

JSON FORMAT REQUIREMENTS:
- Output must be valid JSON only - no additional text before or after
- Properly escape all strings, including newlines (use \\n)
- Escape quotes and special characters properly
- Only include 'response' and 'days' keys in the root object

Generate ALL content dynamically based on the input summary. Calculate dates accurately and ensure logical hotel check-in/checkout alignment.
Focus on creating clean, readable markdown that will convert beautifully to PDF in the frontend."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": summary},
    ]

    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=1500,
            temperature=0.7,
        )

        content = response.choices[0].message.content.strip()

        # Validate that the response is valid JSON
        try:
            parsed = json.loads(content)

            if "response" not in parsed or "days" not in parsed:
                raise ValueError("Missing required keys 'response' or 'days'")

            for day_key, day_info in parsed.get("days", {}).items():
                if not isinstance(day_info, dict):
                    raise ValueError(
                        f"Day {day_key} must be an object with hotel details"
                    )

                required_keys = ["HOTEL_CHECKIN", "HOTEL_CHECKOUT", "HOTEL_DESTINATION"]
                for key in required_keys:
                    if key not in day_info:
                        raise ValueError(f"Missing {key} in {day_key}")

            return content

        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {str(e)}")
            logger.error(f"Raw content: {content}")
            return json.dumps(
                {
                    "response": f"Error: The AI returned invalid JSON format. Raw response: {content}",
                    "days": {},
                }
            )
        except ValueError as e:
            logger.error(f"Invalid days structure: {str(e)}")
            logger.error(f"Raw content: {content}")
            return json.dumps(
                {
                    "response": f"Error: Invalid days structure - {str(e)}. Raw response: {content}",
                    "days": {},
                }
            )

    except Exception as e:
        logger.error(f"Trip planner API error: {str(e)}")
        return json.dumps(
            {"response": f"Error generating itinerary: {str(e)}", "days": {}}
        )
