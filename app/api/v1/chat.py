from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from utils.create_response import create_user_friendly_response
from utils.hotel_booking import process_days_hotels
from utils.flight_booking import get_cheapest_flight, get_multiple_flights
from utils.extract_params import extract_params_with_llm
from schemas.chat import ChatRequest, ChatResponse
from db.database import get_db
from db.models import Session, Itinerary
from services.ai_services import generate_ai_response
from services.trip_planner import create_day_by_day_itinerary
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import blue, black
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
import tempfile
import re

import json

router = APIRouter()


def extract_budget_preference(message):
    """Extract budget preference from user message"""
    message_lower = message.lower()

    # Check for specific price ranges
    price_match = re.search(r"\$(\d+)", message)
    if price_match:
        price = int(price_match.group(1))
        if price < 100:
            return "budget"
        elif price > 300:
            return "luxury"
        else:
            return "mid-range"

    # Check for budget keywords
    budget_keywords = ["budget", "cheap", "affordable", "economical", "low cost"]
    luxury_keywords = [
        "luxury",
        "expensive",
        "premium",
        "high-end",
        "deluxe",
        "upscale",
    ]

    if any(keyword in message_lower for keyword in budget_keywords):
        return "budget"
    elif any(keyword in message_lower for keyword in luxury_keywords):
        return "luxury"

    return "mid-range"  # Default to mid-range if no preference detected


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    print("\n[ZZ-DEBUG] Received chat request:", request)
    if not request.message:
        print("\n[ZZ-DEBUG] No message in request, returning 400.")
        raise HTTPException(status_code=400, detail="Message required")

    try:
        print("\n[ZZ-DEBUG] Looking up session for sessionId:", request.sessionId)
        stmt = select(Session).where(Session.session_id == request.sessionId)
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        print("\n[ZZ-DEBUG] Session found:", session is not None)
        if not session:
            print("\n[ZZ-DEBUG] Creating new session.")
            session = Session(session_id=request.sessionId, history=[])
            db.add(session)
            await db.commit()
            await db.refresh(session)

        print("\n[ZZ-DEBUG] Updating session fields.")
        session.last_message = request.message
        session.destination = request.destination
        session.days = request.days
        session.preferences = request.preferences

        print("\n[ZZ-DEBUG] Appending user message to history.")
        session.history.append({"role": "user", "content": request.message})

        flag_modified(session, "history")

        print("\n[ZZ-DEBUG] Generating AI response.")
        ai_response = await generate_ai_response(session.history)
        print("\n[ZZ-DEBUG] AI response content:", ai_response)

        print("\n[ZZ-DEBUG] Appending AI response to history.")
        session.history.append({"role": "assistant", "content": ai_response})
        flag_modified(session, "history")

        # Check if the response is a summary to set the 'finished' flag
        is_finished = ai_response.startswith("Summary:")

        if is_finished:
            print(
                "\n[ZZ-DEBUG] Detected summary - generating itinerary and saving to file."
            )
            summary_dir = "summaries"
            os.makedirs(summary_dir, exist_ok=True)
            try:
                # Get required params
                params = await extract_params_with_llm(ai_response)
                print("[Test params]:", params)

                # Get Flight details
                flight_details_params = {
                    "origin": params.get("FLIGHT_ORIGIN", ""),
                    "destination": params.get("FLIGHT_DESTINATION", ""),
                    "depart_date": params.get("FLIGHT_DEPART_DATE", ""),
                    "return_date": params.get("FLIGHT_RETURN_DATE", ""),
                }

                cheapest_flight_link = get_cheapest_flight(
                    flight_details_params["origin"],
                    flight_details_params["destination"],
                    flight_details_params["depart_date"],
                    flight_details_params["return_date"],
                )
                print("\n[ZZ-DEBUG] Cheapest flight link:", cheapest_flight_link)
                additional_flight_links = get_multiple_flights(
                    flight_details_params["depart_date"],
                    flight_details_params["origin"],
                    flight_details_params["destination"],
                )
                print("\n[ZZ-DEBUG] Additional flight links:", additional_flight_links)

                flight_details = {
                    "cheapest": cheapest_flight_link,
                    "additional": additional_flight_links,
                }
                response_and_flight_details = {
                    "response": ai_response,
                    "flight_details": flight_details,
                }
                print("\n[ZZ-DEBUG] Response and flight details prepared:")
                print(type(response_and_flight_details))

                # Generate a day-by-day itinerary (expected to return JSON only)
                itinerary_text = await create_day_by_day_itinerary(
                    str(response_and_flight_details)
                )
                print("\n\n\n[ZZ-DEBUG] Itinerary JSON generated:", itinerary_text)

                parsed = None
                try:
                    parsed = json.loads(itinerary_text)
                except Exception as je:
                    print(f"[ZZ-DEBUG] Failed to parse itinerary JSON: {je}")

                if parsed and isinstance(parsed, dict):
                    human_response = parsed.get("response", "")
                    days_map = parsed.get("days", {})
                else:
                    # Fallback: treat whole output as human text
                    human_response = itinerary_text
                    days_map = {}

                # Extract budget preference from user message
                budget_preference = extract_budget_preference(request.message)

                # hotel Booking
                booking_details = process_days_hotels(days_map, budget_preference)

                # combine all details
                final_response = await create_user_friendly_response(
                    trip_text=human_response, hotels_text=str(booking_details)
                )

                timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
                itinerary_file = os.path.join(
                    summary_dir, f"{request.sessionId}_itinerary_{timestamp}.txt"
                )

                with open(itinerary_file, "w", encoding="utf-8") as f:
                    f.write(final_response)
                print(f"\n[ZZ-DEBUG] Itinerary saved to {itinerary_file}")

                # Save itinerary in DB (Itinerary table)
                try:
                    # Try to get existing itinerary for this session

                    stmt = select(Itinerary).where(
                        Itinerary.session_id == request.sessionId
                    )
                    result = await db.execute(stmt)
                    itinerary_obj = result.scalar_one_or_none()
                    if itinerary_obj:
                        itinerary_obj.itinerary = final_response
                    else:
                        itinerary_obj = Itinerary(
                            session_id=request.sessionId, itinerary=final_response
                        )
                        db.add(itinerary_obj)
                    print(
                        f"[ZZ-DEBUG] Itinerary saved to DB for session {request.sessionId}"
                    )
                except Exception as db_err:
                    print(f"[ZZ-DEBUG] Failed to save itinerary to DB: {db_err}")

                # Persist days mapping into session.trip_details for later hotel booking
                try:
                    if not session.trip_details:
                        session.trip_details = {}
                    session.trip_details["days"] = days_map
                    flag_modified(session, "trip_details")
                    print("[ZZ-DEBUG] Stored days mapping in session.trip_details")
                except Exception as se:
                    print(f"[ZZ-DEBUG] Failed to store trip_details: {se}")
            except Exception as file_err:
                print(
                    f"\n[ZZ-DEBUG] Failed to generate or save itinerary: {str(file_err)} - Check logs and ensure trip_planner is configured."
                )

        print("\n[ZZ-DEBUG] Committing session to DB.")
        await db.commit()

        print("\n[ZZ-DEBUG] Returning response to client.")
        return ChatResponse(message=ai_response, finished=is_finished)
    except Exception as e:
        print(f"\n[ZZ-DEBUG] Exception occurred: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate response: {str(e)}"
        )


@router.get("/download-pdf/{session_id}")
async def download_pdf(session_id: str, db: AsyncSession = Depends(get_db)):
    """Download trip itinerary as PDF"""
    print(f"\n[ZZ-DEBUG] PDF download requested for session: {session_id}")

    try:
        # Get the itinerary from database
        stmt = select(Itinerary).where(Itinerary.session_id == session_id)
        result = await db.execute(stmt)
        itinerary = result.scalar_one_or_none()

        if not itinerary:
            print(f"\n[ZZ-DEBUG] No itinerary found for session: {session_id}")
            raise HTTPException(status_code=404, detail="Trip plan not found")

        # Create PDF in memory
        pdf_buffer = generate_pdf(itinerary.itinerary, session_id)

        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file.write(pdf_buffer)
        temp_file.close()

        print(f"\n[ZZ-DEBUG] PDF generated successfully for session: {session_id}")

        return FileResponse(
            path=temp_file.name,
            filename=f"ZoomZoot-TripPlan-{session_id}.pdf",
            media_type="application/pdf",
        )

    except Exception as e:
        print(f"\n[ZZ-DEBUG] Error generating PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")


def generate_pdf(itinerary_text: str, session_id: str) -> bytes:
    """Generate PDF from itinerary text with working clickable links"""
    from io import BytesIO
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import blue, black, grey

    # Custom PDF class that handles links properly
    class LinkEnabledDocTemplate(SimpleDocTemplate):
        def __init__(self, *args, **kwargs):
            SimpleDocTemplate.__init__(self, *args, **kwargs)

        def afterPage(self):
            """Called after each page is rendered - this is where we add link functionality"""
            canvas = self.canv
            # Enable proper link handling
            canvas.setAuthor("ZoomZoot Travel Planner")
            canvas.setTitle("Travel Itinerary")
            canvas.setSubject("Trip Planning Document")

    buffer = BytesIO()
    doc = LinkEnabledDocTemplate(buffer, pagesize=letter, topMargin=1 * inch)

    # Create styles
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=20,
        spaceAfter=30,
        textColor=blue,
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceAfter=12,
        textColor=black,
        spaceBefore=6,
    )
    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=6,
        leading=14,
        textColor=black,
    )

    # Build PDF content
    story = []

    # Title
    story.append(Paragraph("🌍 ZoomZoot Travel Plan", title_style))
    story.append(Spacer(1, 20))

    # Session info
    story.append(Paragraph(f"Session ID: {session_id}", normal_style))
    story.append(
        Paragraph(
            f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
            normal_style,
        )
    )
    story.append(Spacer(1, 20))

    # Process itinerary text line by line
    lines = itinerary_text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            story.append(Spacer(1, 6))
            continue

        # Process the line for formatting and links
        processed_line = process_line_with_working_links(line)

        # Determine if it's a heading
        if is_heading_line(processed_line):
            story.append(Paragraph(processed_line, heading_style))
        else:
            story.append(Paragraph(processed_line, normal_style))

    # Add footer
    story.append(Spacer(1, 30))
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=9,
        textColor=grey,
        alignment=1,  # Center alignment
    )
    story.append(Paragraph("Generated by ZoomZoot AI Travel Assistant", footer_style))
    story.append(Paragraph("www.zoomzoot.com", footer_style))

    # Build PDF
    doc.build(story)

    pdf_value = buffer.getvalue()
    buffer.close()

    return pdf_value


def process_line_with_working_links(text: str) -> str:
    """Process text with proper ReportLab link syntax that actually works"""

    # Handle bold markdown **text**
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    # Process different link patterns and convert to working ReportLab links
    # Pattern 1: **[link text](url)** (bold links)
    bold_link_pattern = r"<b>\[([^\]]+)\]\(([^)]+)\)</b>"
    # Pattern 2: [link text](url) (regular links)
    link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

    def replace_link(match):
        link_text = match.group(1)
        url = match.group(2)

        # Clean and format the link text
        if "Book" in link_text and (
            "flight" in link_text.lower() or "Flight" in link_text
        ):
            display_text = f"✈️ {link_text}"
        elif any(
            word in link_text for word in ["Hotel", "Resort", "Spa", "Albar", "Diamond"]
        ):
            display_text = f"🏨 {link_text}"
        else:
            display_text = link_text

        # Use proper ReportLab link syntax with escaped URL
        # The key is using 'a' tag instead of 'link' tag
        safe_url = url.replace("&", "&amp;")  # Escape ampersands
        return f'<a href="{safe_url}" color="blue"><u><b>{display_text}</b></u></a>'

    # Replace bold links first, then regular links
    text = re.sub(bold_link_pattern, replace_link, text)
    text = re.sub(link_pattern, replace_link, text)

    # Format specific sections
    if "Flight Summary:" in text:
        text = text.replace("Flight Summary:", "✈️ <b>Flight Summary:</b>")

    if "Trip Summary:" in text:
        text = text.replace("Trip Summary:", "📋 <b>Trip Summary:</b>")

    if "Booking:" in text:
        text = text.replace("Booking:", "🔗 <b>Booking:</b>")

    # Format activities
    if text.startswith("- Morning:"):
        text = text.replace("- Morning:", "🌅 <b>Morning:</b>")
    elif text.startswith("- Afternoon:"):
        text = text.replace("- Afternoon:", "☀️ <b>Afternoon:</b>")
    elif text.startswith("- Evening:"):
        text = text.replace("- Evening:", "🌆 <b>Evening:</b>")

    # Format day headings
    day_pattern = r"Day (\d+) — (.+?):"
    text = re.sub(day_pattern, r"📅 <b>Day \1 — \2</b>", text)

    return text


def is_heading_line(text: str) -> bool:
    """Check if text should be formatted as a heading"""
    heading_keywords = [
        "📅 <b>Day",
        "✈️ <b>Flight",
        "🏨 <b>Hotel",
        "📋 <b>Trip",
        "Flight Summary",
        "Trip Summary",
        "Itinerary",
    ]
    return any(keyword in text for keyword in heading_keywords)


def process_links_in_text(text: str) -> str:
    """Convert markdown-style links to ReportLab clickable links with better formatting"""

    # First handle bold markdown **text**
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    # Handle different link patterns:
    # Pattern 1: **[link text](url)**
    bold_link_pattern = r"<b>\[([^\]]+)\]\(([^)]+)\)</b>"

    # Pattern 2: [link text](url)
    link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"

    def replace_link(match):
        link_text = match.group(1)
        url = match.group(2)

        # Clean up the link text for better display
        if "Book" in link_text and (
            "flight" in link_text.lower() or "Flight" in link_text
        ):
            display_text = "✈️ Book Flight"
        elif (
            "Hotel" in link_text
            or "Resort" in link_text
            or "Spa" in link_text
            or "Albar" in link_text
            or "Diamond" in link_text
        ):
            display_text = f"🏨 {link_text}"
        else:
            display_text = link_text

        # Create proper clickable link using reportlab link syntax
        return f'<link href="{url}" color="blue"><u>{display_text}</u></link>'

    # Replace bold links first, then regular links
    processed_text = re.sub(bold_link_pattern, replace_link, text)
    processed_text = re.sub(link_pattern, replace_link, processed_text)

    # Improve formatting of specific sections
    if "Flight Summary:" in processed_text:
        processed_text = processed_text.replace(
            "Flight Summary:", "✈️ <b>Flight Summary:</b>"
        )

    if "Trip Summary:" in processed_text:
        processed_text = processed_text.replace(
            "Trip Summary:", "📋 <b>Trip Summary:</b>"
        )

    if "Booking:" in processed_text:
        processed_text = processed_text.replace("Booking:", "🔗 <b>Booking:</b>")

    # Improve day formatting
    day_pattern = r"<b>Day (\d+) — ([^<]+)</b>:"
    processed_text = re.sub(day_pattern, r"📅 <b>Day \1 — \2</b>", processed_text)

    return processed_text
