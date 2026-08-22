import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import httpx

BACKEND = "http://localhost:8000"
FRONTEND = "http://localhost:5000"

# Shared test scenario from PLAN.md
SCENARIO = (
    "Landlord locked me out and won't return my ₹50,000 deposit "
    "after 11 months; no written agreement, only UPI rent proofs."
)


@pytest.mark.asyncio
async def test_frontend_options_panel():
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        # 1. Trigger options generation via the real backend
        r = await client.post(
            BACKEND + "/api/v1/demo/analyze",
            json={
                "case_id": "",
                "description": SCENARIO,
                "user_name": "",
                "opponent_name": "",
                "opponent_address": "",
                "language": "en",
            },
        )
        assert r.status_code == 200, f"analyze failed: {r.status_code}"
        data = r.json()
        opts = data.get("legal_options", [])
        assert len(opts) >= 3, f"expected >=3 options, got {len(opts)}"
        assert sum(1 for o in opts if o.get("recommended")) == 1, "expected exactly 1 recommended"

        # 2. Fetch the frontend page
        fr = await client.get(FRONTEND + "/demo")
        assert fr.status_code == 200, f"frontend GET failed: {fr.status_code}"
        html = fr.text

    # 3. Assert all required UI hooks are present
    required_tokens = [
        'id="options-panel"',
        "renderOptions",
        'id="prev-option"',
        'id="next-option"',
        'id="choose-option"',
        "Try a sample case",
    ]
    for token in required_tokens:
        assert token in html, f"frontend HTML missing required token: {token}"
