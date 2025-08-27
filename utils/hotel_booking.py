import requests
from datetime import datetime
from dotenv import load_dotenv
import os
import json

load_dotenv()

# ====== CONFIGURATION ======
API_TOKEN = os.getenv("TRAVELPAYOUTS_API_KEY")
MARKER = "659627"
CURRENCY = "USD"
HOTEL_LIMIT = 5
HOTEL_CURRENCY = "USD"


def get_hotels_by_budget(
    HOTEL_CHECKIN, HOTEL_CHECKOUT, HOTEL_DESTINATION, budget_preference=None
):
    """Get hotel details for a specific destination, date range, and budget preference"""
    print(
        f"\n===== Hotels for {HOTEL_DESTINATION} ({HOTEL_CHECKIN} to {HOTEL_CHECKOUT}) ====="
    )

    if budget_preference:
        print(f"Budget preference: {budget_preference}")

    if not HOTEL_CHECKIN or not HOTEL_CHECKOUT:
        print("Missing check-in or check-out dates.")
        return []

    url = "https://engine.hotellook.com/api/v2/cache.json"
    params = {
        "location": HOTEL_DESTINATION,
        "currency": HOTEL_CURRENCY,
        "checkIn": HOTEL_CHECKIN,
        "checkOut": HOTEL_CHECKOUT,
        "limit": 20,  # Get more hotels for filtering
        "token": API_TOKEN,
    }

    try:
        res = requests.get(url, params=params).json()
        if not res:
            print("No hotel data found.")
            return []

        all_hotels = []
        for hotel in res:
            name = hotel.get("hotelName", "Unknown Hotel")
            stars = hotel.get("stars", 0)
            price = hotel.get("priceFrom")
            hotel_id = hotel.get("hotelId", "")

            link = f"https://search.hotellook.com/?marker={MARKER}&currency={HOTEL_CURRENCY}&destination={HOTEL_DESTINATION}&checkIn={HOTEL_CHECKIN}&checkOut={HOTEL_CHECKOUT}"
            if hotel_id:
                link += f"&hotelId={hotel_id}"

            hotel_info = {
                "name": name,
                "stars": stars,
                "price": price or 0,
                "currency": HOTEL_CURRENCY if price else "",
                "link": link,
                "hotel_id": hotel_id,
            }
            all_hotels.append(hotel_info)

        # Filter hotels based on budget preference
        filtered_hotels = filter_hotels_by_budget(all_hotels, budget_preference)

        # Limit to top 5 after filtering
        filtered_hotels = filtered_hotels[:HOTEL_LIMIT]

        for hotel in filtered_hotels:
            print(
                f"{hotel['name']} ({hotel['stars']}⭐) | From {hotel['price']} {hotel['currency'] if hotel['price'] else ''} | Link: {hotel['link']}"
            )

        return filtered_hotels

    except Exception as e:
        print(f"Error fetching hotel data for {HOTEL_DESTINATION}:", e)
        return []


def filter_hotels_by_budget(hotels, budget_preference):
    """Filter hotels based on budget preference"""
    if not budget_preference or not hotels:
        return hotels

    # Remove hotels with no price data
    hotels_with_price = [h for h in hotels if h["price"] > 0]

    if not hotels_with_price:
        return hotels[:5]  # Return original if no price data

    # Sort by price
    hotels_with_price.sort(key=lambda x: x["price"])

    budget_lower = budget_preference.lower()

    if any(
        word in budget_lower
        for word in ["budget", "cheap", "affordable", "low cost", "economical"]
    ):
        # Budget-friendly: lowest 60% of prices
        budget_count = max(1, int(len(hotels_with_price) * 0.6))
        return hotels_with_price[:budget_count]

    elif any(
        word in budget_lower
        for word in [
            "luxury",
            "premium",
            "high-end",
            "expensive",
            "5 star",
            "five star",
        ]
    ):
        # Luxury: highest 40% of prices
        luxury_count = max(1, int(len(hotels_with_price) * 0.4))
        return hotels_with_price[-luxury_count:]

    elif any(word in budget_lower for word in ["mid", "medium", "moderate", "average"]):
        # Mid-range: middle 60% of prices
        total = len(hotels_with_price)
        start = int(total * 0.2)  # Skip bottom 20%
        end = int(total * 0.8)  # Skip top 20%
        return hotels_with_price[start:end]

    # Check for specific price ranges (e.g., "under 100", "less than 150", "below 200")
    price_keywords = ["under", "less than", "below", "maximum", "max", "up to"]
    for keyword in price_keywords:
        if keyword in budget_lower:
            try:
                # Extract number from the budget preference
                import re

                numbers = re.findall(r"\d+", budget_preference)
                if numbers:
                    max_price = int(numbers[0])
                    return [h for h in hotels_with_price if h["price"] <= max_price]
            except:
                pass

    # Default: return all hotels sorted by price
    return hotels_with_price


def process_days_hotels(days_map, budget_preference=None):
    """
    Process the days map and get hotel details for each day

    Args:
        days_map: Dictionary containing day information with hotel details
                 Format: {
                     "Day 1": {
                         "HOTEL_CHECKIN": "2025-09-10",
                         "HOTEL_CHECKOUT": "2025-09-11",
                         "HOTEL_DESTINATION": "Kandy"
                     },
                     ...
                 }
        budget_preference: String describing budget preference (e.g., "budget-friendly", "luxury", "under 100")

    Returns:
        Dictionary with hotel details for each day
    """
    if not days_map:
        print("No days data provided.")
        return {}

    all_hotels_data = {}
    processed_stays = set()  # Track unique stays to avoid duplicates

    print("Processing hotel search for each day...")
    if budget_preference:
        print(f"Budget preference: {budget_preference}")
    print("=" * 50)

    for day_key, day_info in days_map.items():
        try:
            # Validate day_info structure
            if not isinstance(day_info, dict):
                print(f"Warning: {day_key} data is not a dictionary. Skipping.")
                continue

            checkin = day_info.get("HOTEL_CHECKIN")
            checkout = day_info.get("HOTEL_CHECKOUT")
            destination = day_info.get("HOTEL_DESTINATION")

            # Validate required fields
            if not all([checkin, checkout, destination]):
                print(f"Warning: Missing hotel data for {day_key}. Skipping.")
                print(
                    f"  Check-in: {checkin}, Check-out: {checkout}, Destination: {destination}"
                )
                continue

            # Create a unique stay identifier to avoid duplicate API calls
            stay_key = f"{destination}_{checkin}_{checkout}"

            if stay_key in processed_stays:
                print(
                    f"Skipping {day_key} - already processed stay in {destination} ({checkin} to {checkout})"
                )
                # Copy hotel data from the first day with same stay details
                for existing_day, existing_data in all_hotels_data.items():
                    if (
                        existing_data.get("destination") == destination
                        and existing_data.get("checkin") == checkin
                        and existing_data.get("checkout") == checkout
                    ):
                        all_hotels_data[day_key] = existing_data.copy()
                        break
                continue

            # Get hotel data for this stay
            hotels = get_hotels_by_budget(
                checkin, checkout, destination, budget_preference
            )

            # Store the results
            all_hotels_data[day_key] = {
                "destination": destination,
                "checkin": checkin,
                "checkout": checkout,
                "hotels": hotels,
                "hotel_count": len(hotels),
            }

            processed_stays.add(stay_key)

        except Exception as e:
            print(f"Error processing {day_key}: {e}")
            all_hotels_data[day_key] = {
                "destination": day_info.get("HOTEL_DESTINATION", "Unknown"),
                "checkin": day_info.get("HOTEL_CHECKIN", "Unknown"),
                "checkout": day_info.get("HOTEL_CHECKOUT", "Unknown"),
                "hotels": [],
                "hotel_count": 0,
                "error": str(e),
            }

    print("\n" + "=" * 50)
    print("Hotel processing completed!")
    print(
        f"Processed {len(all_hotels_data)} days with {len(processed_stays)} unique stays."
    )

    return all_hotels_data


def print_hotels_summary(hotels_data):
    """Print a summary of all hotel data"""
    if not hotels_data:
        print("No hotel data to display.")
        return

    print("\n" + "=" * 50)
    print("HOTEL SEARCH SUMMARY")
    print("=" * 50)

    for day_key, day_data in hotels_data.items():
        print(f"\n{day_key}:")
        print(f"  Location: {day_data.get('destination', 'Unknown')}")
        print(
            f"  Dates: {day_data.get('checkin', 'Unknown')} to {day_data.get('checkout', 'Unknown')}"
        )
        print(f"  Hotels found: {day_data.get('hotel_count', 0)}")

        if day_data.get("error"):
            print(f"  Error: {day_data['error']}")
        elif day_data.get("hotels"):
            print("  Top hotel:")
            top_hotel = day_data["hotels"][0]
            print(f"    - {top_hotel['name']} ({top_hotel['stars']}⭐)")
            if top_hotel["price"]:
                print(f"    - From {top_hotel['price']} {top_hotel['currency']}")


# Example usage function
def main():
    """Example of how to use the hotel processing functions"""

    # Example days_map (this would come from your trip planner)
    example_days_map = {
        "Day 1": {
            "HOTEL_CHECKIN": "2025-09-10",
            "HOTEL_CHECKOUT": "2025-09-11",
            "HOTEL_DESTINATION": "Kandy",
        },
        "Day 2": {
            "HOTEL_CHECKIN": "2025-09-11",
            "HOTEL_CHECKOUT": "2025-09-12",
            "HOTEL_DESTINATION": "Kandy",
        },
        "Day 3": {
            "HOTEL_CHECKIN": "2025-09-12",
            "HOTEL_CHECKOUT": "2025-09-13",
            "HOTEL_DESTINATION": "Colombo",
        },
    }

    # Process hotels for all days
    hotels_data = process_days_hotels(example_days_map)

    # Print summary
    print_hotels_summary(hotels_data)

    # You can also access individual day data like this:
    # day1_hotels = hotels_data.get("Day 1", {}).get("hotels", [])
    # print(f"Day 1 has {len(day1_hotels)} hotels available")


if __name__ == "__main__":
    main()
