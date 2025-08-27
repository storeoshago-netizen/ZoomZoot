ZoomZoot Travel Planner Backend
A FastAPI-based backend for the ZoomZoot Travel Planner, providing a chatbot for Southeast Asia trip planning.
Setup

Install dependencies:
pip install -r requirements.txt

Set up PostgreSQL and update .env with your DATABASE_URL and OPENAI_API_KEY.

Run the application:
uvicorn app.main:app --host 0.0.0.0 --port 8000

Testing
Run tests with:
pytest

API Endpoints

POST /api/v1/chat: Handles user queries and returns itineraries with mock affiliate links.



Test
cd ui
python -m http.server 8080