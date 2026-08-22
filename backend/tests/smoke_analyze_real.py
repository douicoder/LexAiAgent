import sys
import time
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
async def test_smoke_analyze_real():
    async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
        start = time.monotonic()

        # 1. Real API analyze
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
        assert r.status_code == 200, f"analyze status {r.status_code}"
        data = r.json()

        # 2. Frontend page
        fr = await client.get(FRONTEND + "/demo")
        assert fr.status_code == 200, f"frontend status {fr.status_code}"
        html = fr.text

        elapsed = time.monotonic() - start

    print(f"\n[Part 6] end-to-end elapsed: {elapsed:.1f}s")

    # Performance gate (full flow)
    assert elapsed < 150, f"end-to-end too slow: {elapsed:.1f}s (target <150s)"

    # API response structure
    opts = data.get("legal_options", [])
    assert len(opts) >= 3, f"expected >=3 options, got {len(opts)}"
    assert sum(1 for o in opts if o.get("recommended")) == 1, "expected exactly 1 recommended"
    assert data.get("option_comparison_note"), "option_comparison_note empty"

    # Frontend HTML hook
    assert 'id="options-panel"' in html, "frontend missing options-panel"
