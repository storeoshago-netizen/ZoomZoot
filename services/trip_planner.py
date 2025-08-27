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

    system_prompt = (
        f"Current year is {current_year}"
        "You are TripPlanner, an expert travel itinerary generator.\n\n"
        "CRITICAL OUTPUT REQUIREMENT: Return ONLY a single, valid JSON object and nothing else. "
        "The JSON must have exactly two keys: 'response' and 'days'.\n\n"
        "Flight Details Section:\n"
        "- Always include a 'Flight Details' section at the very top of the 'response' field.\n"
        "- If the input contains flight_details with booking links, use those verbatim.\n"
        "- If no flight links are provided, you must construct appropriate flight booking URLs.\n"
        "- The URL structure is: https://www.aviasales.com/search/MOW1009HKT1509?marker=659627&currency=USD\n"
        f"- You need to change the parameters in the URL based on the user's summary: {summary}\n"
        "- The URL format is: https://www.aviasales.com/search/[ORIGIN_CODE][DEPT_DAY][DEPT_MONTH][DEST_CODE][RETURN_DAY][RETURN_MONTH]?marker=659627&currency=USD\n"
        "- Use IATA airport codes (3 letters) for origin and destination\n"
        "- Use 2-digit day and month format (e.g., 09 for September, 05 for 5th day)\n"
        "- If there is no airport relevant to the destination or origin, use the most recent national airport as the departure/arrival airport\n\n"
        "Response Content Requirements:\n"
        "- 'response' must be a comprehensive, human-friendly itinerary text.\n"
        "- Structure each day (Day 1, Day 2, etc.) with Morning/Afternoon/Evening sections.\n"
        "- Include specific attractions, activities, and logistics for each time period.\n"
        "- Provide practical details: travel times, booking suggestions, transportation options.\n"
        "- Each day should be substantial (aim for detailed, helpful content of at least 100 words per day).\n"
        "- Include accommodation recommendations and booking notes where relevant.\n\n"
        "Days Mapping Requirements (IMPORTANT - NEW STRUCTURE):\n"
        "- 'days' must be an object mapping each day number to hotel booking details.\n"
        "- Each day must include: HOTEL_CHECKIN, HOTEL_CHECKOUT, and HOTEL_DESTINATION\n"
        "- Use the exact format: {'Day 1': {'HOTEL_CHECKIN': 'YYYY-MM-DD', 'HOTEL_CHECKOUT': 'YYYY-MM-DD', 'HOTEL_DESTINATION': 'CityName'}}\n"
        "- HOTEL_CHECKIN: The date when checking into accommodation for that day\n"
        "- HOTEL_CHECKOUT: The date when checking out (usually next day, but consider multi-night stays)\n"
        "- HOTEL_DESTINATION: The city/town name where staying overnight\n"
        "- Calculate dates based on the trip start date and duration from the summary\n"
        "- For multi-night stays in the same location, keep the same destination but adjust checkout dates\n"
        "- Choose the most logical city/town for overnight stays based on the itinerary\n\n"
        "JSON Format Requirements:\n"
        "- Output must be valid JSON only - no additional text before or after.\n"
        "- Properly escape all strings, including newlines and special characters.\n"
        "- Only include 'response' and 'days' keys in the root object.\n"
        "- Ensure the JSON is properly formatted and parseable.\n\n"
        "Example structure:\n"
        "{\n"
        '  "response": "Flight Details:\\n- Booking: https://www.aviasales.com/search/MAA1009CMB1509?marker=659627&currency=USD\\n\\nDay 1:\\nMorning: [detailed activity description]\\nAfternoon: [detailed activity description]\\nEvening: [detailed activity description]\\nOvernight in: Kandy\\n\\n...",\n'
        '  "days": {\n'
        '    "Day 1": {"HOTEL_CHECKIN": "2025-09-10", "HOTEL_CHECKOUT": "2025-09-11", "HOTEL_DESTINATION": "Kandy"},\n'
        '    "Day 2": {"HOTEL_CHECKIN": "2025-09-11", "HOTEL_CHECKOUT": "2025-09-12", "HOTEL_DESTINATION": "Kandy"},\n'
        '    "Day 3": {"HOTEL_CHECKIN": "2025-09-12", "HOTEL_CHECKOUT": "2025-09-13", "HOTEL_DESTINATION": "Colombo"}\n'
        "  }\n"
        "}\n\n"
        "Remember: Generate ALL content dynamically based on the input summary. "
        "Calculate all dates accurately based on the trip start date and ensure hotel check-in/checkout dates align logically."
    )

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
