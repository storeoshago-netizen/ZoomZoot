import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_chat_endpoint():
    response = client.post(
        "/api/v1/chat",
        json={
            "sessionId": "test-123",
            "message": "Plan a 5-day trip to Thailand",
            "destination": "Thailand",
            "days": 5,
            "preferences": ["food", "culture"],
        },
    )
    assert response.status_code == 200
    assert "reply" in response.json()
    assert "itinerary" in response.json()
    assert "links" in response.json()
