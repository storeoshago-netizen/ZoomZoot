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
from io import BytesIO
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT

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
    """Download trip itinerary as markdown text file"""
    print(f"\n[ZZ-DEBUG] Markdown download requested for session: {session_id}")

    try:
        # Get the itinerary from database
        stmt = select(Itinerary).where(Itinerary.session_id == session_id)
        result = await db.execute(stmt)
        itinerary = result.scalar_one_or_none()

        if not itinerary:
            print(f"\n[ZZ-DEBUG] No itinerary found for session: {session_id}")
            raise HTTPException(status_code=404, detail="Trip plan not found")

        # Parse the JSON response to get clean markdown
        try:
            import json

            itinerary_data = json.loads(itinerary.itinerary)
            markdown_content = itinerary_data.get("response", itinerary.itinerary)
        except json.JSONDecodeError:
            # If not JSON, use raw content
            markdown_content = itinerary.itinerary

        # Create temporary text file with markdown content
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".txt", mode="w", encoding="utf-8"
        )
        temp_file.write(markdown_content)
        temp_file.close()

        print(
            f"\n[ZZ-DEBUG] Markdown file generated successfully for session: {session_id}"
        )

        return FileResponse(
            path=temp_file.name,
            filename=f"ZoomZoot-TripPlan-{session_id}.txt",
            media_type="text/plain",
        )

    except Exception as e:
        print(f"\n[ZZ-DEBUG] Error generating markdown file: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to generate markdown file: {str(e)}"
        )


def generate_pdf(itinerary_text: str, session_id: str) -> bytes:
    """Generate a beautiful, professional PDF from itinerary text"""

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    # Define beautiful color scheme
    brand_blue = HexColor("#0066cc")
    dark_blue = HexColor("#003d7a")
    light_blue = HexColor("#e6f2ff")
    dark_gray = HexColor("#2c3e50")
    medium_gray = HexColor("#7f8c8d")
    light_gray = HexColor("#f8f9fa")
    success_green = HexColor("#27ae60")
    warning_orange = HexColor("#f39c12")

    # Create elegant styles
    styles = getSampleStyleSheet()

    # Brand title style
    brand_title_style = ParagraphStyle(
        "BrandTitle",
        parent=styles["Title"],
        fontSize=28,
        textColor=brand_blue,
        spaceAfter=10,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        letterSpacing=2,
    )

    # Elegant subtitle
    elegant_subtitle_style = ParagraphStyle(
        "ElegantSubtitle",
        parent=styles["Normal"],
        fontSize=14,
        textColor=medium_gray,
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName="Helvetica-Oblique",
    )

    # Section title style
    section_title_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading1"],
        fontSize=18,
        textColor=dark_blue,
        spaceAfter=15,
        spaceBefore=25,
        fontName="Helvetica-Bold",
        borderWidth=0,
        borderPadding=0,
    )

    # Day title style
    day_title_style = ParagraphStyle(
        "DayTitle",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=white,
        spaceAfter=12,
        spaceBefore=20,
        fontName="Helvetica-Bold",
        backColor=brand_blue,
        borderPadding=12,
        borderRadius=8,
    )

    # Activity text style
    activity_text_style = ParagraphStyle(
        "ActivityText",
        parent=styles["Normal"],
        fontSize=11,
        textColor=dark_gray,
        spaceAfter=8,
        leftIndent=25,
        fontName="Helvetica",
        leading=18,
        bulletIndent=15,
    )

    # Link style
    link_style = ParagraphStyle(
        "LinkStyle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=success_green,
        spaceAfter=12,
        leftIndent=25,
        fontName="Helvetica-Bold",
    )

    # Summary text style
    summary_text_style = ParagraphStyle(
        "SummaryText",
        parent=styles["Normal"],
        fontSize=12,
        textColor=dark_gray,
        spaceAfter=15,
        fontName="Helvetica",
        alignment=TA_JUSTIFY,
        leading=20,
        borderPadding=15,
        backColor=light_gray,
        borderRadius=5,
    )

    # Build beautiful PDF content
    story = []

    # Beautiful header
    story.append(Paragraph("ZOOMZOOT", brand_title_style))
    story.append(
        Paragraph("Your Personalized Travel Itinerary", elegant_subtitle_style)
    )

    # Elegant divider line (using table)
    divider_table = Table([[""], [""]], colWidths=[6.5 * inch], rowHeights=[2, 2])
    divider_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, 0), 2, brand_blue),
                ("LINEBELOW", (0, 1), (-1, 1), 1, light_blue),
            ]
        )
    )
    story.append(divider_table)
    story.append(Spacer(1, 20))

    # Document info in elegant table
    info_data = [
        ["Session ID", session_id],
        ["Generated", datetime.now().strftime("%B %d, %Y at %I:%M %p")],
    ]

    info_table = Table(info_data, colWidths=[2 * inch, 4.5 * inch])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("TEXTCOLOR", (0, 0), (0, -1), dark_blue),
                ("TEXTCOLOR", (1, 0), (1, -1), dark_gray),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [light_gray, white]),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dee2e6")),
                ("PADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )

    story.append(info_table)
    story.append(Spacer(1, 30))

    # Parse the itinerary data (handle both JSON and text formats)
    try:
        # Try to parse as JSON first (from trip planner)
        import json

        itinerary_data = json.loads(itinerary_text)
        response_text = itinerary_data.get("response", itinerary_text)
    except json.JSONDecodeError:
        # If not JSON, treat as plain text
        response_text = itinerary_text

    # Process and format the content with professional structure
    formatted_content = process_structured_itinerary(response_text)

    # Add formatted content to story with proper spacing and indentation
    for item in formatted_content:
        if item["type"] == "section_title":
            story.append(Spacer(1, 15))  # Space before section
            story.append(Paragraph(item["content"], section_title_style))
            story.append(Spacer(1, 10))  # Space after section
        elif item["type"] == "day_title":
            story.append(Spacer(1, 20))  # Extra space before new day
            story.append(Paragraph(item["content"], day_title_style))
            story.append(Spacer(1, 8))  # Space after day title
        elif item["type"] == "activity":
            # Add left margin for better visual hierarchy
            indented_content = f"&nbsp;&nbsp;&nbsp;&nbsp;{item['content']}"
            story.append(Paragraph(indented_content, activity_text_style))
            story.append(Spacer(1, 5))  # Small space between activities
        elif item["type"] == "link":
            # Extra indentation for booking links
            indented_content = (
                f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{item['content']}"
            )
            story.append(Paragraph(indented_content, link_style))
            story.append(Spacer(1, 8))  # More space after links
        elif item["type"] == "summary":
            story.append(Spacer(1, 15))  # Space before summary
            story.append(Paragraph(item["content"], summary_text_style))
        elif item["type"] == "spacer":
            story.append(Spacer(1, item["height"]))

    # Beautiful footer
    story.append(Spacer(1, 50))

    footer_divider = Table([[""], [""]], colWidths=[6.5 * inch], rowHeights=[1, 1])
    footer_divider.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 1, light_blue),
                ("LINEABOVE", (0, 1), (-1, 1), 2, brand_blue),
            ]
        )
    )
    story.append(footer_divider)
    story.append(Spacer(1, 20))

    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=11,
        textColor=medium_gray,
        alignment=TA_CENTER,
        fontName="Helvetica",
        spaceAfter=8,
    )

    story.append(Paragraph("<b>Thank you for choosing ZoomZoot!</b>", footer_style))
    story.append(Paragraph("For support and inquiries: www.zoomzoot.com", footer_style))

    # Build the PDF
    doc.build(story)

    pdf_value = buffer.getvalue()
    buffer.close()
    return pdf_value


def process_structured_itinerary(text: str) -> list:
    """Process itinerary text into structured format for beautiful PDF rendering"""
    content_items = []

    # Split into lines and process
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Clean bullets and extra formatting first
        original_line = line
        line = re.sub(r"^[-•*]\s*", "", line)  # Remove bullets
        line = re.sub(r"^Booking:\s*", "", line)  # Remove standalone "Booking:"

        # Skip if line becomes empty after cleaning
        if not line.strip():
            continue

        # Detect and format different content types
        if "Flight Details:" in original_line or (
            "flight" in line.lower() and ("book" in line.lower() or "https://" in line)
        ):
            content_items.append(
                {"type": "section_title", "content": "✈️ FLIGHT INFORMATION"}
            )
            # Process flight links
            flight_content = clean_and_format_line(
                line.replace("Flight Details:", "").strip()
            )
            if flight_content and "book" in flight_content.lower():
                content_items.append({"type": "link", "content": flight_content})

        elif line.startswith("Day ") and (":" in line or "—" in line):
            # Day headers
            day_content = clean_and_format_line(line)
            content_items.append({"type": "day_title", "content": f"📅 {day_content}"})
            content_items.append({"type": "spacer", "height": 5})

        elif "morning" in line.lower() and (
            ":" in line or line.lower().startswith("morning")
        ):
            content = clean_and_format_line(line.replace("Morning:", "").strip())
            if content:
                content_items.append(
                    {"type": "activity", "content": f"🌅 <b>Morning:</b> {content}"}
                )

        elif "afternoon" in line.lower() and (
            ":" in line or line.lower().startswith("afternoon")
        ):
            content = clean_and_format_line(line.replace("Afternoon:", "").strip())
            if content:
                content_items.append(
                    {"type": "activity", "content": f"☀️ <b>Afternoon:</b> {content}"}
                )

        elif "evening" in line.lower() and (
            ":" in line or line.lower().startswith("evening")
        ):
            content = clean_and_format_line(line.replace("Evening:", "").strip())
            if content:
                content_items.append(
                    {"type": "activity", "content": f"🌆 <b>Evening:</b> {content}"}
                )

        elif "https://" in line and (
            "booking" in original_line.lower() or "book" in line.lower()
        ):
            # Booking links - avoid duplication
            content = clean_and_format_line(line)
            if content and not any(
                item.get("content", "").endswith(content) for item in content_items[-3:]
            ):
                content_items.append({"type": "link", "content": content})

        elif "overnight" in line.lower() or "stay" in line.lower():
            # Accommodation info
            content = clean_and_format_line(line)
            if content:
                content_items.append({"type": "activity", "content": f"🏨 {content}"})

        else:
            # Regular content - avoid duplicates and ensure substantial content
            content = clean_and_format_line(line)
            if (
                content
                and len(content) > 15  # Only substantial content
                and not any(
                    "booking" in item.get("content", "").lower()
                    for item in content_items[-2:]
                )  # Avoid booking duplicates
                and content
                not in [
                    item.get("content", "") for item in content_items[-3:]
                ]  # Avoid exact duplicates
            ):
                content_items.append({"type": "activity", "content": content})

    return content_items


def clean_and_format_line(text: str) -> str:
    """Clean and format a line with proper link handling"""
    if not text or text.isspace():
        return ""

    # Clean multiple bullets and extra formatting
    text = re.sub(r"^[-•*]\s*[-•*]\s*", "", text)  # Double bullets
    text = re.sub(r"^[-•*]\s*", "", text)  # Single bullets
    text = re.sub(r"^Booking:\s*", "", text)  # Remove "Booking:" prefix
    text = text.strip()

    if not text:
        return ""

    # Handle bold markdown **text** first
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)

    # Check if text already contains processed links to avoid double processing
    if "<a href=" in text:
        return text

    # Process links with beautiful formatting - but avoid double processing
    def replace_link(match):
        link_text = match.group(1)
        url = match.group(2)

        # Determine link type and apply appropriate styling
        if (
            "flight" in link_text.lower()
            or "aviasales" in url.lower()
            or "Book this flight" in link_text
        ):
            display_text = "✈️ Book Flight"
            color = "#e74c3c"
        elif any(
            word in link_text.lower()
            for word in [
                "hotel",
                "resort",
                "spa",
                "albar",
                "diamond",
                "maison",
                "booking",
            ]
        ):
            display_text = f"🏨 {link_text}"
            color = "#27ae60"
        else:
            display_text = link_text
            color = "#3498db"

        # Create proper clickable link (ReportLab format) with simpler escaping
        safe_url = url.replace("&", "&amp;")
        return f'<a href="{safe_url}" color="{color}"><u><b>{display_text}</b></u></a>'

    # Apply link processing for markdown links
    link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
    text = re.sub(link_pattern, replace_link, text)

    # Handle direct URLs that aren't in markdown format
    def replace_direct_url(match):
        url = match.group(0)
        if "aviasales" in url:
            display_text = "✈️ Book Flight"
            color = "#e74c3c"
        elif "booking.com" in url or "hotel" in url.lower():
            display_text = "🏨 Book Hotel"
            color = "#27ae60"
        else:
            display_text = "🔗 Visit Link"
            color = "#3498db"

        safe_url = url.replace("&", "&amp;")
        return f'<a href="{safe_url}" color="{color}"><u><b>{display_text}</b></u></a>'

    # Process direct URLs only if no links were already processed
    if "<a href=" not in text:
        url_pattern = r"https?://[^\s\)\]\}]+"
        text = re.sub(url_pattern, replace_direct_url, text)

    return text
