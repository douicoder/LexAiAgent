import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from dotenv import load_dotenv

from app.services.agent_service import AgentService
from app.services.rag_service import RagService
from app.dto.agent_dto import AnalyzeRequestDTO

# Shared test scenario from PLAN.md
SCENARIO = (
    "Landlord locked me out and won't return my ₹50,000 deposit "
    "after 11 months; no written agreement, only UPI rent proofs."
)


@pytest.mark.asyncio
async def test_pipeline_speed_and_structure():
    load_dotenv()
    rag = RagService()
    agent = AgentService(rag)

    request = AnalyzeRequestDTO(
        case_id="",
        description=SCENARIO,
        user_name="",
        opponent_name="",
        opponent_address="",
        language="en",
    )

    start = time.monotonic()
    result = await agent.analyze_case(request)
    elapsed = time.monotonic() - start
    print(f"\n[Part 2] analyze elapsed: {elapsed:.1f}s")

    # Performance gate (speed target from plan: <150s)
    assert elapsed < 150, f"Pipeline too slow: {elapsed:.1f}s (target <150s)"

    # Structural validity only — options are added in Part 3 (not asserted here)
    assert result.case_type, "case_type missing"
    assert result.summary, "summary missing"
    assert isinstance(result.relevant_sections, list)
    assert result.case_readiness_score >= 0
    assert result.is_sufficient is True
