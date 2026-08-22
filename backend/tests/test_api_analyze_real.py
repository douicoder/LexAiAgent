import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import httpx

BACKEND = "http://localhost:8000"

# Shared test scenario from PLAN.md
SCENARIO = (
    "Landlord locked me out and won't return my ₹50,000 deposit "
    "after 11 months; no written agreement, only UPI rent proofs."
)


@pytest.mark.asyncio
async def test_api_analyze_real():
    async with httpx.AsyncClient(timeout=180) as client:
        start = time.monotonic()
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
        elapsed = time.monotonic() - start
        print(f"\n[Part 4] analyze elapsed: {elapsed:.1f}s")
        assert r.status_code == 200, f"status {r.status_code}: {r.text[:300]}"
        data = r.json()

    # Performance gate
    assert elapsed < 150, f"analyze too slow: {elapsed:.1f}s (target <150s)"

    # Options structure
    opts = data.get("legal_options", [])
    assert len(opts) >= 3, f"expected >=3 options, got {len(opts)}"
    recommended = [o for o in opts if o.get("recommended")]
    assert len(recommended) == 1, f"expected exactly 1 recommended, got {len(recommended)}"
    assert data.get("option_comparison_note"), "option_comparison_note empty"

    # First option field validation
    o = opts[0]
    assert 0 <= o.get("success_likelihood", 0) <= 100, "success_likelihood out of range"
    assert o.get("pros"), "pros empty"
    assert o.get("cons"), "cons empty"
    assert o.get("best_for") in {"cost", "time", "success", "risk", "control"}, "best_for invalid"
    assert o.get("interoperability_note"), "interoperability_note empty"
