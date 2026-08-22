import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from dotenv import load_dotenv

from app.services.agent_service import AgentService
from app.services.rag_service import RagService
from app.dto.agent_dto import LegalOptionDTO

# Shared test scenario from PLAN.md
SCENARIO = (
    "Landlord locked me out and won't return my ₹50,000 deposit "
    "after 11 months; no written agreement, only UPI rent proofs."
)

VALID_BEST_FOR = {"cost", "time", "success", "risk", "control"}


@pytest.mark.asyncio
async def test_generate_options_real():
    load_dotenv()
    rag = RagService()
    agent = AgentService(rag)

    # Real RAG retrieval, then build the same section_refs string the pipeline uses
    law_sections = await rag.search(SCENARIO, top_k=5)
    section_refs = agent._build_section_refs(law_sections)

    options, comparison_note = await agent._generate_options(
        SCENARIO, "tenancy_dispute", section_refs
    )

    print(f"\n[Part 3] generated {len(options)} options")
    for o in options:
        print(f"  - {o.name} (recommended={o.recommended}, best_for={o.best_for})")
    print(f"[Part 3] comparison_note: {comparison_note[:160]}")

    # 3-4 distinct options
    assert 3 <= len(options) <= 4, f"expected 3-4 options, got {len(options)}"

    # Exactly one recommended
    recommended = [o for o in options if o.recommended]
    assert len(recommended) == 1, f"expected exactly 1 recommended, got {len(recommended)}"

    # Comparison note present
    assert comparison_note, "comparison_note missing"

    # Each option structurally valid
    for o in options:
        assert isinstance(o, LegalOptionDTO)
        assert 0 <= o.success_likelihood <= 100, (
            f"success_likelihood {o.success_likelihood} out of range"
        )
        assert o.pros, f"option {o.id} has empty pros"
        assert o.cons, f"option {o.id} has empty cons"
        assert o.best_for in VALID_BEST_FOR, f"best_for {o.best_for!r} invalid"
        assert o.interoperability_note, f"option {o.id} missing interoperability_note"
        assert o.next_steps, f"option {o.id} missing next_steps"
        # lists may be empty but must be present
        assert isinstance(o.evidence_required, list)
        assert isinstance(o.applicable_documents, list)
