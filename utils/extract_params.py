from datetime import datetime, timedelta
import re
import json
import asyncio

from openai import AsyncOpenAI
from core.config import settings
from core.logging import logger
import datetime

current_year = datetime.datetime.now().year


async def extract_params_with_llm(summary: str) -> dict:
    """Use Azure OpenAI to extract flight params from a one-line summary.

    Returns a dict with keys: FLIGHT_ORIGIN, FLIGHT_DESTINATION, FLIGHT_DEPART_DATE, FLIGHT_RETURN_DATE
    Values are strings (ISO dates for dates). On error, returns empty-string values.
    """

    logger.info("LLM extraction requested")

    system_prompt = (
        f"Current year is {current_year}\n"
        "You are a strict JSON extractor. Input is a single-line travel summary.\n"
        "Produce ONLY one JSON object (no surrounding text) with these exact keys: \n"
        "FLIGHT_ORIGIN, FLIGHT_DESTINATION, FLIGHT_DEPART_DATE, FLIGHT_RETURN_DATE.\n\n"
        "Rules:\n"
        "- Dates must be in YYYY-MM-DD. If no year is provided in the input, use the current year.\n"
        "- Use IATA airport codes (3 uppercase letters) for FLIGHT_ORIGIN and FLIGHT_DESTINATION when possible. If the destination is a region, landmark, or mountain (e.g. 'Himalayas', 'Sigiriya'), determine the nearest major commercial airport and return its IATA code. If you cannot determine a valid 3-letter IATA code, return an empty string.\n"
        "- If the input provides a start/depart date but no return date, and the summary includes a number of days (e.g., 'Duration: 5 days'), calculate the return date as depart_date + duration_days and output it in YYYY-MM-DD.\n"
        "- If flight is not needed or a field is unknown, return an empty string for that key.\n"
        "- Return valid JSON only — no markdown, no explanation, no extra fields.\n"
    )

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": summary},
    ]

    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        json_text = m.group(0) if m else raw
        parsed = json.loads(json_text)
        return {
            "FLIGHT_ORIGIN": parsed.get("FLIGHT_ORIGIN", "") or "",
            "FLIGHT_DESTINATION": parsed.get("FLIGHT_DESTINATION", "") or "",
            "FLIGHT_DEPART_DATE": parsed.get("FLIGHT_DEPART_DATE", "") or "",
            "FLIGHT_RETURN_DATE": parsed.get("FLIGHT_RETURN_DATE", "") or "",
        }
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return {
            "FLIGHT_ORIGIN": "",
            "FLIGHT_DESTINATION": "",
            "FLIGHT_DEPART_DATE": "",
            "FLIGHT_RETURN_DATE": "",
        }


def normalize_params(params: dict, summary: str) -> dict:
    """Validate/normalize LLM output:
    - Ensure IATA codes are 3 uppercase letters; if not, try simple mapping from common names in the summary.
    - If depart date year is in the past, roll it forward to the current year preserving month/day.
    - If return date is empty and summary contains a duration (N days), compute return = depart + N days.
    """
    out = params.copy() if isinstance(params, dict) else {}

    # simple IATA sanity check
    def _ensure_iata(code: str) -> str:
        if not code:
            return ""
        code = code.strip().upper()
        if re.fullmatch(r"[A-Z]{3}", code):
            return code
        # try very small heuristics: if code looks like a city name, take first 3 letters
        t = re.split(r"[,\s/()\-]+", code)[0]
        if len(t) >= 3:
            return t[:3].upper()
        return ""

    out["FLIGHT_ORIGIN"] = _ensure_iata(out.get("FLIGHT_ORIGIN", ""))
    out["FLIGHT_DESTINATION"] = _ensure_iata(out.get("FLIGHT_DESTINATION", ""))

    # Normalize depart date year and compute/adjust return date
    depart = out.get("FLIGHT_DEPART_DATE", "")
    return_date = out.get("FLIGHT_RETURN_DATE", "")
    try:
        depart_dt = None
        if depart:
            depart_dt = datetime.fromisoformat(depart)
            now = datetime.utcnow()
            # If depart year is in the past, roll it forward to current year
            if depart_dt.year < now.year:
                depart_dt = depart_dt.replace(year=now.year)
                out["FLIGHT_DEPART_DATE"] = depart_dt.date().isoformat()

        # extract duration if present in the summary
        duration_days = None
        m = re.search(r"Duration\s*:\s*(\d+)", summary, re.IGNORECASE)
        if m:
            try:
                duration_days = int(m.group(1))
            except Exception:
                duration_days = None

        # Compute or validate return date so it is >= depart
        final_ret = None
        if return_date:
            try:
                final_ret = datetime.fromisoformat(return_date)
            except Exception:
                final_ret = None

        # If we have a depart date, ensure return makes sense
        if depart_dt:
            if not final_ret and duration_days:
                final_ret = depart_dt + timedelta(days=duration_days)
            if final_ret:
                # if return is before depart, try replace year with depart year
                if final_ret < depart_dt:
                    try:
                        candidate = final_ret.replace(year=depart_dt.year)
                        if candidate >= depart_dt:
                            final_ret = candidate
                        else:
                            final_ret = depart_dt + timedelta(days=duration_days or 1)
                    except Exception:
                        final_ret = depart_dt + timedelta(days=duration_days or 1)
            # If still no final_ret, but duration exists, compute
            if not final_ret and duration_days:
                final_ret = depart_dt + timedelta(days=duration_days)
        else:
            # no depart date: if final_ret exists, leave it; else empty
            if not final_ret:
                final_ret = None

        out["FLIGHT_RETURN_DATE"] = final_ret.date().isoformat() if final_ret else ""
    except Exception as e:
        logger.error(f"Normalization error: {e}")

    return out
