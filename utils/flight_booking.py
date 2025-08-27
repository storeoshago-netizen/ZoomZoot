import requests
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
# ====== CONFIGURATION ======
API_TOKEN = os.getenv("TRAVELPAYOUTS_API_KEY")
MARKER = "659627"
CURRENCY = "USD"

# ====== FLIGHT DEFAULTS ======
# FLIGHT_ORIGIN = "MOW"
# FLIGHT_DESTINATION = "HKT"
# FLIGHT_DEPART_DATE = "2025-09-10"
# FLIGHT_RETURN_DATE = "2025-09-15"


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


def get_cheapest_flight(
    FLIGHT_ORIGIN, FLIGHT_DESTINATION, FLIGHT_DEPART_DATE, FLIGHT_RETURN_DATE
):
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


def get_multiple_flights(FLIGHT_DEPART_DATE, FLIGHT_ORIGIN, FLIGHT_DESTINATION):
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
