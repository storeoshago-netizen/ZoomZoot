import requests
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
# ====== CONFIGURATION ======
API_TOKEN = os.getenv("TRAVELPAYOUTS_API_KEY")
# print("Travelpayouts API Token:", API_TOKEN)
MARKER = "659627"
CURRENCY = "USD"

# ====== FLIGHT DEFAULTS ======
FLIGHT_ORIGIN = "MOW"
FLIGHT_DESTINATION = "HKT"
FLIGHT_DEPART_DATE = "2025-09-10"
FLIGHT_RETURN_DATE = "2025-09-15"

# ====== HOTEL DEFAULTS ======
HOTEL_CITY = "Bangkok"
HOTEL_LIMIT = 5
HOTEL_CHECKIN = "2025-09-10"
HOTEL_CHECKOUT = "2025-09-15"
HOTEL_CURRENCY = "USD"
HOTEL_DESTINATION = "Bangkok"

# ====== TOURS DEFAULTS ======
TOUR_CITY_ID = "1"  # Bangkok
TOUR_CAMPAIGN_ID = "89"  # Tiqets campaign ID
TOUR_P_ID = "2074"  # Default p parameter (verify this value)
TOUR_TRS = "445060"  # Tracking source (verify this value)
# Dictionary for city-specific p values (update based on dashboard or data file)
TOUR_P_IDS = {
    "1": "2074",  # Bangkok (example, replace with correct value)
    # Add more city IDs and p values as needed
}


def build_flight_link(origin, departure_at, destination, return_at=None):
    dep_str = ""
    if departure_at:
        try:
            dep_date = datetime.fromisoformat(departure_at.replace("Z", ""))
        except ValueError:
            try:
                dep_date = datetime.strptime(departure_at, "%Y-%m-%d")
            except ValueError:
                dep_date = None
        if dep_date:
            dep_str = f"{dep_date.day:02}{dep_date.month:02}"

    link = f"https://www.aviasales.com/search/{origin}{dep_str}{destination}"

    ret_str = ""
    if return_at:
        try:
            ret_date = datetime.fromisoformat(return_at.replace("Z", ""))
        except ValueError:
            try:
                ret_date = datetime.strptime(return_at, "%Y-%m-%d")
            except ValueError:
                ret_date = None
        if ret_date:
            ret_str = f"{ret_date.day:02}{ret_date.month:02}"
            link += ret_str

    link += f"?marker={MARKER}&currency={CURRENCY}"
    return link


def get_cheapest_flight():
    print("\n===== Cheapest Flight =====")
    url = (
        f"https://api.travelpayouts.com/v1/prices/cheap?"
        f"origin={FLIGHT_ORIGIN}&destination={FLIGHT_DESTINATION}"
        f"&depart_date={FLIGHT_DEPART_DATE}&return_date={FLIGHT_RETURN_DATE}"
        f"&currency={CURRENCY}&token={API_TOKEN}"
    )
    res = requests.get(url).json()
    if not res.get("success"):
        print("Error:", res)
        return
    flights = list(res["data"].get(FLIGHT_DESTINATION, {}).values())
    if flights:
        f = flights[0]
        airline = f.get("airline") or "Unknown Airline"
        price = f.get("price") or "N/A"
        link = build_flight_link(
            FLIGHT_ORIGIN, f.get("departure_at"), FLIGHT_DESTINATION, f.get("return_at")
        )
        print(
            f"{FLIGHT_ORIGIN} → {FLIGHT_DESTINATION} | Airline: {airline} | Price: {price} {CURRENCY} | Link: {link}"
        )
    else:
        print("No flights found.")


def get_multiple_flights():
    print("\n===== Multiple Flight Options =====")
    beginning_of_period = FLIGHT_DEPART_DATE[:7] + "-01"
    url = (
        f"https://api.travelpayouts.com/v2/prices/latest?"
        f"origin={FLIGHT_ORIGIN}&destination={FLIGHT_DESTINATION}"
        f"&currency={CURRENCY}&token={API_TOKEN}&limit=5"
        f"&period_type=month&beginning_of_period={beginning_of_period}"
        f"&one_way=false&show_to_affiliates=true"
    )
    res = requests.get(url).json()
    if not res.get("success"):
        print("Error:", res)
        return
    for f in res.get("data", []):
        airline = "N/A"
        price = f.get("value") or "N/A"
        link = build_flight_link(
            FLIGHT_ORIGIN,
            f.get("depart_date"),
            FLIGHT_DESTINATION,
            f.get("return_date"),
        )
        print(
            f"{FLIGHT_ORIGIN} → {FLIGHT_DESTINATION} | Airline: {airline} | Price: {price} {CURRENCY} | Link: {link}"
        )


def get_hotels():
    print("\n===== Hotels =====")
    if not HOTEL_CHECKIN or not HOTEL_CHECKOUT:
        print("Missing check-in or check-out dates.")
        return

    url = "https://engine.hotellook.com/api/v2/cache.json"
    params = {
        "location": HOTEL_DESTINATION,
        "currency": HOTEL_CURRENCY,
        "checkIn": HOTEL_CHECKIN,
        "checkOut": HOTEL_CHECKOUT,
        "limit": 5,
        "token": API_TOKEN,
    }

    try:
        res = requests.get(url, params=params).json()
        if not res:
            print("No hotel data found.")
            return

        for hotel in res:
            name = hotel.get("hotelName", "Unknown Hotel")
            stars = hotel.get("stars", "N/A")
            price = hotel.get("priceFrom")
            hotel_id = hotel.get("hotelId", "")
            link = f"https://search.hotellook.com/?marker={MARKER}&currency={HOTEL_CURRENCY}&destination={HOTEL_DESTINATION}"
            if hotel_id:
                link += f"&hotelId={hotel_id}"
            print(
                f"{name} ({stars}⭐) | From {price} {HOTEL_CURRENCY if price else ''} | Link: {link}"
            )
    except Exception as e:
        print("Error fetching hotel data:", e)


def get_tours(city_id=TOUR_CITY_ID, city_name="Bangkok"):
    print(f"\n===== Tours for {city_name} =====")
    if not TOUR_CAMPAIGN_ID:
        print(
            "Tours provider not enabled. Please join Tiqets in Travelpayouts dashboard."
        )
        return
    if not city_id or not city_id.isdigit():
        print(f"Invalid city ID: {city_id}")
        return

    p_id = TOUR_P_IDS.get(city_id, TOUR_P_ID)  # Use city-specific p value or default
    link = (
        f"https://tp.media/r?marker={MARKER}"
        f"&campaign_id={TOUR_CAMPAIGN_ID}"
        f"&locale=en&city_id={city_id}"
        f"&p={p_id}"
        f"&sub_id=zoomzoot_travel_planner"
        f"&trs={TOUR_TRS}"
        f"&u=https%3A%2F%2Ftiqets.com"
    )
    print(f"Tours link for {city_name} (city ID {city_id}): {link}")
    print(
        "(Tiqets currently only supports deeplinks via Travelpayouts — no JSON API data.)"
    )


if __name__ == "__main__":
    get_cheapest_flight()
    get_multiple_flights()
    get_hotels()
    get_tours(city_id="1", city_name="Bangkok")
