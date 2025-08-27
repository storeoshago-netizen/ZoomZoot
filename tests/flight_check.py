import requests
import json
import time
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()

# ====== CONFIGURATION ======
API_TOKEN = os.getenv("TRAVELPAYOUTS_API_KEY")
MARKER = "659627"
CURRENCY = "USD"

# ====== FLIGHT SEARCH CONFIGURATION ======
FLIGHT_ORIGIN = "CMB"
FLIGHT_DESTINATION = "DEL"
FLIGHT_DEPART_DATE = "2025-08-20"
FLIGHT_RETURN_DATE = "2025-08-30"


class RealTimeFlightSearch:
    def __init__(self, token, marker=None, currency="USD"):
        self.token = token
        self.marker = marker or "659627"
        self.currency = currency
        self.base_url = "https://api.travelpayouts.com/aviasales/v3"

    def create_search(
        self, origin, destination, departure_date, return_date=None, passengers=None
    ):
        """
        Step 1: Create a new search session (Real-time API)
        This initiates the search and returns a search_id
        """
        url = f"{self.base_url}/search"

        # Default passengers if not specified
        if passengers is None:
            passengers = {"adults": 1, "children": 0, "infants": 0}

        payload = {
            "marker": self.marker,
            "host": "aviasales.com",  # Required for the real-time API
            "user_ip": "127.0.0.1",  # Your server IP (required)
            "locale": "en",
            "trip_class": "Y",  # Y = Economy, C = Business, F = First
            "passengers": passengers,
            "segments": [
                {
                    "origin": origin,
                    "destination": destination,
                    "departure_at": departure_date,
                }
            ],
        }

        # Add return segment if round trip
        if return_date:
            payload["segments"].append(
                {
                    "origin": destination,
                    "destination": origin,
                    "departure_at": return_date,
                }
            )

        headers = {"X-Access-Token": self.token, "Content-Type": "application/json"}

        print(f"Creating search for {origin} → {destination}")
        print(f"Departure: {departure_date}, Return: {return_date}")
        print(f"API URL: {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            print(f"Response Status: {response.status_code}")
            print(f"Response Headers: {dict(response.headers)}")

            if response.status_code == 200:
                result = response.json()
                print(f"Search created successfully!")
                print(f"Response: {json.dumps(result, indent=2)}")
                return result
            else:
                print(f"❌ Error creating search: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Exception creating search: {e}")
            return None

    def get_search_results(self, search_id, max_wait_time=60):
        """
        Step 2: Poll the search results using the search_id
        """
        url = f"{self.base_url}/search_results"
        headers = {"X-Access-Token": self.token}
        params = {"uuid": search_id, "marker": self.marker}

        print(f"\nPolling search results for ID: {search_id}")
        print(f"API URL: {url}")

        start_time = time.time()
        attempt = 1

        while time.time() - start_time < max_wait_time:
            try:
                print(f"Attempt {attempt} - Checking for results...")
                response = requests.get(url, params=params, headers=headers, timeout=15)

                if response.status_code == 200:
                    result = response.json()

                    # Check if search is complete
                    if result.get("search_id") and result.get("proposals"):
                        print(
                            f"✅ Search completed! Found {len(result.get('proposals', []))} flight options"
                        )
                        return result
                    else:
                        print(
                            f"Search still in progress... (Status: {result.get('status', 'unknown')})"
                        )

                elif response.status_code == 204:
                    print("Search still processing (204 No Content)...")

                else:
                    print(f"❌ Error getting results: {response.status_code}")
                    print(f"Response: {response.text}")

            except Exception as e:
                print(f"❌ Exception polling results: {e}")

            attempt += 1
            time.sleep(3)  # Wait 3 seconds between attempts

        print(f"❌ Search timed out after {max_wait_time} seconds")
        return None

    def parse_flight_results(self, results):
        """Parse and display the flight results in a readable format"""
        if not results or not results.get("proposals"):
            print("No flight proposals found")
            return

        proposals = results["proposals"]
        print(f"\n{'='*60}")
        print(f"FOUND {len(proposals)} FLIGHT OPTIONS")
        print(f"{'='*60}")

        for i, proposal in enumerate(proposals[:10]):  # Show top 10 results
            try:
                price = (
                    proposal.get("unified_price", {})
                    .get("total", {})
                    .get("amount", "N/A")
                )
                currency = (
                    proposal.get("unified_price", {})
                    .get("total", {})
                    .get("currency", self.currency)
                )

                segments = proposal.get("segment", [])

                print(f"\n--- Flight Option {i+1} ---")
                print(f"Price: {price} {currency}")

                for j, segment in enumerate(segments):
                    flight = segment.get("flight", [{}])[0]
                    departure = flight.get("departure", {})
                    arrival = flight.get("arrival", {})

                    dep_airport = departure.get("airport", "Unknown")
                    arr_airport = arrival.get("airport", "Unknown")
                    dep_time = departure.get("at", "Unknown")
                    arr_time = arrival.get("at", "Unknown")
                    airline = flight.get("airline", "Unknown")
                    flight_number = flight.get("number", "Unknown")

                    print(f"  Segment {j+1}: {dep_airport} → {arr_airport}")
                    print(f"    Flight: {airline} {flight_number}")
                    print(f"    Departure: {dep_time}")
                    print(f"    Arrival: {arr_time}")

                # Generate booking link
                search_id = results.get("search_id", "")
                proposal_id = proposal.get("id", "")
                booking_link = f"https://www.aviasales.com/search?search_id={search_id}&proposal_id={proposal_id}&marker={self.marker}"
                print(f"    Booking Link: {booking_link}")

            except Exception as e:
                print(f"Error parsing proposal {i+1}: {e}")

    def search_flights(self, origin, destination, departure_date, return_date=None):
        """Complete flight search workflow"""
        print(f"\n🔍 STARTING REAL-TIME FLIGHT SEARCH")
        print(f"Route: {origin} → {destination}")
        print(f"Departure: {departure_date}")
        if return_date:
            print(f"Return: {return_date}")
        print("-" * 50)

        # Step 1: Create search
        search_response = self.create_search(
            origin, destination, departure_date, return_date
        )

        if not search_response:
            print("❌ Failed to create search")
            return None

        search_id = search_response.get("search_id")
        if not search_id:
            print("❌ No search_id received")
            print(f"Response: {search_response}")
            return None

        print(f"✅ Search created with ID: {search_id}")

        # Step 2: Get results
        results = self.get_search_results(search_id)

        if results:
            # Step 3: Parse and display results
            self.parse_flight_results(results)
            return results
        else:
            print("❌ No results received")
            return None


def test_api_access():
    """Test if the API token has access to real-time search"""
    print("🔧 TESTING API ACCESS PERMISSIONS")
    print("-" * 50)

    # Test with a simple endpoint first
    url = "https://api.travelpayouts.com/v2/prices/latest"
    params = {
        "currency": "USD",
        "origin": "MOW",
        "destination": "LED",
        "token": API_TOKEN,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"Test API Status: {response.status_code}")

        if response.status_code == 200:
            print("✅ API Token is valid")
            return True
        elif response.status_code == 401:
            print("❌ API Token is invalid (401 Unauthorized)")
            return False
        else:
            print(f"⚠️ Unexpected response: {response.status_code}")
            print(f"Response: {response.text}")
            return True  # Continue anyway

    except Exception as e:
        print(f"❌ Error testing API: {e}")
        return False


def main():
    print("=" * 70)
    print("TRAVELPAYOUTS REAL-TIME FLIGHT SEARCH")
    print("=" * 70)

    # Test API access first
    if not test_api_access():
        print("\n❌ API access test failed. Please check your token.")
        return

    # Initialize the real-time search client
    search_client = RealTimeFlightSearch(
        token=API_TOKEN, marker=MARKER, currency=CURRENCY
    )

    # Perform the search
    results = search_client.search_flights(
        origin=FLIGHT_ORIGIN,
        destination=FLIGHT_DESTINATION,
        departure_date=FLIGHT_DEPART_DATE,
        return_date=FLIGHT_RETURN_DATE,
    )

    if results:
        print(f"\n✅ Search completed successfully!")
    else:
        print(f"\n❌ Search failed. Possible reasons:")
        print("1. Your API token doesn't have real-time search access")
        print("2. The route/date combination has no available flights")
        print("3. API endpoint or parameters need adjustment")
        print(
            "\nTry contacting Travelpayouts support to enable real-time search API access."
        )


if __name__ == "__main__":
    main()
