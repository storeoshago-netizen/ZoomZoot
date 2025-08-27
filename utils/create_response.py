from openai import AsyncOpenAI
from core.config import settings
from core.logging import logger
import asyncio
import json


async def create_user_friendly_response(
    trip_text: str, hotels_text: str | None = None
) -> str:
    """Combine a free-form trip+flight text and an optional hotels text into
    a concise, user-friendly trip-management document.

    Inputs:
    - trip_text: single plain-text string containing day-by-day trip details and flight info.
    - hotels_text: optional plain-text string containing per-day hotel booking details.

    Returns a plain-text itinerary suitable for emailing or viewing in-app.
    """

    logger.info("Creating user-friendly combined response")

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
    )

    # Minimal: convert inputs to plain strings and let the LLM interpret them.
    # This avoids heavy parsing logic here; chat endpoint can pass either text or
    # a machine-generated dict (stringified). The LLM is instructed below to
    # preserve booking URLs verbatim and extract per-day hotel bookings.
    flight_section = ""  # flight info expected in trip_text
    hotels_section = str(hotels_text) if hotels_text is not None else "(none provided)"

    system_prompt = (
        "You are an expert Trip Assistant.\n"
        "Task: Combine the provided day-by-day trip plan (which also includes flight details) and the hotels text into a single, clear, and actionable itinerary for the traveler.\n\n"
        "Important input note: The second block (HOTELS_TEXT) may be free-form text OR a machine-generated dictionary printed as text. It contains per-day hotel search results and MUST be treated as authoritative: preserve any booking URLs exactly as they appear.\n\n"
        "Output rules (mandatory):\n"
        "- Return PLAIN TEXT only (no JSON, no markdown fences).\n"
        "- Start with a concise Trip Summary (one paragraph) including route and dates.\n"
        "- Include a 'Flight Summary' block with booking links and a clear action (e.g., 'Book this flight').\n"
        "- For each day (Day 1..N) produce a Day header (Day N — Date/Location if available) and include:\n"
        "  * Morning/Afternoon/Evening bullets summarizing activities (use the trip_text content).\n"
        "  * Hotel booking info for that night, using the booking URL exactly as found in HOTELS_TEXT (label as 'Booking: <url>').\n"
        "  * Actionable checklist items (tickets to buy, reservations to confirm, travel time to next location).\n"
        "- If hotels are absent for a day, explicitly write 'Hotel: not available' for that night.\n"
        "- Preserve all URLs from HOTELS_TEXT and do not fabricate booking links. If a hotel entry lacks a URL, state 'Booking link: not available'.\n"
        "- Keep language friendly and concise; use bullets and short sentences.\n"
    )

    user_content = (
        "TRIP_AND_FLIGHT_TEXT:\n"
        + (trip_text or "")
        + "\n\n"
        + "HOTELS_TEXT:\n"
        + (hotels_section or "(none provided)")
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        resp = await client.chat.completions.create(
            model="gpt-3.5-turbo", messages=messages, max_tokens=900
        )
        content = resp.choices[0].message.content.strip()
        if not isinstance(content, str):
            content = str(content)
        return content
    except Exception as e:
        logger.error(f"create_user_friendly_response failed: {e}")
        return f"Error creating user-friendly response: {e}"


def sync_create_user_friendly_response(
    trip_text: str, hotels_text: dict | str | None = None
) -> str:
    """Synchronous wrapper for environments that don't await. Runs the async function in the event loop."""
    try:
        return asyncio.get_event_loop().run_until_complete(
            create_user_friendly_response(trip_text, hotels_text)
        )
    except RuntimeError:
        # If there's no running loop, create a new one
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                create_user_friendly_response(trip_text, hotels_text)
            )
        finally:
            loop.close()
