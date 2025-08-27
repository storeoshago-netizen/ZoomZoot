import pytest

from services.ai_services import generate_ai_response
from services.external_service import get_external_data



@pytest.mark.asyncio
async def test_ai_service():
    response = await generate_ai_response("Plan a trip", "Thailand", 5, ["food"])
    assert isinstance(response, str)
    assert len(response) > 0  # Ensure non-empty response from OpenAI


@pytest.mark.asyncio
async def test_external_service():
    data = await get_external_data("Plan a trip", "Thailand")
    assert isinstance(data, dict)
    assert "reddit" in data
