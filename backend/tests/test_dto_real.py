"""Real (no-mock) round-trip test for the options data schema.

Verifies LegalOptionDTO construction, serialization, and reconstruction,
plus AnalyzeResponseDTO carrying a list of options with exactly one recommended.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dto.agent_dto import AnalyzeResponseDTO, LegalOptionDTO

VALID_BEST_FOR = {"cost", "time", "success", "risk", "control"}


def _make_option(option_id: str, name: str, recommended: bool) -> LegalOptionDTO:
    return LegalOptionDTO(
        id=option_id,
        name=name,
        forum="District Rent Court",
        tagline="Fastest, cheapest first step",
        recommended=recommended,
        cost_range="₹500–2,000",
        time_range="7–15 days",
        effort="Low",
        success_likelihood=70,
        risk_level="low",
        pros=["Cheap", "Fast", "Signals seriousness"],
        cons=["No binding order", "Can be ignored"],
        evidence_required=["UPI transaction proofs", "Legal notice copy"],
        best_for="time",
        interoperability_note="Notice is a prerequisite for a civil suit; can run parallel to mediation.",
        next_steps=[
            "Draft notice with facts + 15-day deadline",
            "Send via registered post (AD)",
        ],
        applicable_documents=["Legal Notice Template", "Model Tenancy Act Section 11"],
    )


def test_legal_option_round_trip():
    opt = _make_option("opt-001", "Legal Notice", recommended=True)

    # Serialize and reconstruct
    data = opt.model_dump()
    rebuilt = LegalOptionDTO(**data)

    assert rebuilt.id == opt.id
    assert rebuilt.name == opt.name
    assert rebuilt.forum == opt.forum
    assert rebuilt.tagline == opt.tagline
    assert rebuilt.recommended is True
    assert rebuilt.cost_range == "₹500–2,000"
    assert rebuilt.time_range == "7–15 days"
    assert rebuilt.effort == "Low"
    assert isinstance(rebuilt.success_likelihood, int)
    assert 0 <= rebuilt.success_likelihood <= 100
    assert rebuilt.risk_level == "low"
    assert len(rebuilt.pros) > 0
    assert len(rebuilt.cons) > 0
    assert rebuilt.best_for in VALID_BEST_FOR
    assert rebuilt.interoperability_note != ""
    assert len(rebuilt.next_steps) > 0
    assert len(rebuilt.evidence_required) > 0
    assert len(rebuilt.applicable_documents) > 0


def test_analyze_response_carries_options():
    options = [
        _make_option("opt-001", "Legal Notice", recommended=True),
        _make_option("opt-002", "Rent Authority / Civil Suit", recommended=False),
        _make_option("opt-003", "Mediation / Settlement", recommended=False),
        _make_option("opt-004", "Consumer Forum Complaint", recommended=False),
    ]
    note = (
        "Notice is fastest/cheapest; suit is strongest but slowest; "
        "mediation is a low-risk parallel path; consumer forum is cheapest "
        "but limited to service deficiency."
    )

    response = AnalyzeResponseDTO(
        case_type="tenancy_dispute",
        severity="medium",
        legal_domain="Landlord-Tenant",
        relevant_sections=[],
        summary="Tenant deposit dispute.",
        next_steps=[],
        reasoning_trace="",
        ai_message="Analyzed.",
        case_readiness_score=20,
        is_sufficient=True,
        law_docs_available=[],
        law_docs_coverage="",
        legal_options=options,
        option_comparison_note=note,
    )

    assert len(response.legal_options) >= 3
    assert sum(1 for o in response.legal_options if o.recommended) == 1
    assert response.option_comparison_note != ""
