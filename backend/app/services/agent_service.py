import asyncio
import json
import re
import uuid
from datetime import datetime, timezone

import httpx
from openai import AsyncOpenAI, APIConnectionError, APITimeoutError, RateLimitError

from app.config import settings
from app.dto.agent_dto import (
    ActionButton,
    ActionStep,
    AnalyzeRequestDTO,
    AnalyzeResponseDTO,
    ChatRequestDTO,
    ChatResponseDTO,
    ClarifyingQuestion,
    DocumentDTO,
    ExecuteActionRequest,
    ExecuteActionResponse,
)
from app.helpers.legal_helper import LegalHelper
from app.helpers.text_helper import TextHelper
from app.interfaces.i_rag_service import IRagService

LLM_MODEL = settings.LLM_MODEL
FAST_MODEL = "gpt-4o"



AVAILABLE_LAW_DOCS = [
    "Model Tenancy Act, 2021",
    "Transfer of Property Act, 1882",
    "Registration Act, 1908",
]
LAW_DOCS_COVERAGE_TENANCY = (
    "This case is within our knowledge base. The following law documents "
    "have been ingested and were used for legal analysis: "
    + ", ".join(AVAILABLE_LAW_DOCS) + ". "
    "These cover tenancy, property transfer, and registration matters."
)
LAW_DOCS_COVERAGE_LIMITED = (
    "[!] Limited law documents available in the database. "
    "Currently ingested: " + ", ".join(AVAILABLE_LAW_DOCS) + ". "
    "These primarily cover tenancy, property, and registration law. "
    "Your case type may not be fully covered by the available legal corpus. "
    "Consider consulting a qualified legal professional for case-specific advice."
)

# ── Document type definitions ───────────────────────────────────────────
# Only ask for personal details NOT already in the case description.
# The LLM receives the full case description and extracts subject, facts, and
# relief details automatically — no need to make users re-enter them.
DOCUMENT_TYPES = {
    "demand_letter": {
        "title": "Formal Demand Letter",
        "required_info": ["sender_name", "sender_address", "recipient_name", "recipient_address"],
        "info_labels": {"sender_name": "Your full name", "sender_address": "Your address", "recipient_name": "Recipient's full name", "recipient_address": "Recipient's address"},
    },
    "legal_notice": {
        "title": "Legal Notice",
        "required_info": ["sender_name", "sender_address", "recipient_name", "recipient_address"],
        "info_labels": {"sender_name": "Your full name", "sender_address": "Your address", "recipient_name": "Recipient's full name", "recipient_address": "Recipient's address"},
    },
    "court_filing": {
        "title": "Court Filing / Petition",
        "required_info": ["petitioner_name", "petitioner_address", "respondent_name", "respondent_address", "court_name"],
        "info_labels": {"petitioner_name": "Your full name (Petitioner)", "petitioner_address": "Your address", "respondent_name": "Respondent's full name", "respondent_address": "Respondent's address", "court_name": "Name of the court"},
    },
    "affidavit": {
        "title": "Affidavit",
        "required_info": ["deponent_name", "deponent_address"],
        "info_labels": {"deponent_name": "Your full name (Deponent)", "deponent_address": "Your address"},
    },
    "complaint": {
        "title": "Formal Complaint",
        "required_info": ["complainant_name", "complainant_address", "respondent_name"],
        "info_labels": {"complainant_name": "Your full name (Complainant)", "complainant_address": "Your address", "respondent_name": "Respondent's name"},
    },
    "agreement": {
        "title": "Legal Agreement",
        "required_info": ["party_a_name", "party_a_address", "party_b_name", "party_b_address"],
        "info_labels": {"party_a_name": "First Party name", "party_a_address": "First Party address", "party_b_name": "Second Party name", "party_b_address": "Second Party address"},
    },
}


def _extract_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("Empty text, no JSON object found")

    for start in range(len(text)):
        if text[start] != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"' and not escaped:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i+1])
    raise ValueError("No valid JSON object found in text")


def _generate_doc_id() -> str:
    return str(uuid.uuid4())


class AgentService:
    def __init__(self, rag: IRagService):
        self.client = AsyncOpenAI(
            api_key=settings.GITHUB_TOKEN,
            base_url="https://models.github.ai/inference",
        )
        self.rag = rag
        self.legal = LegalHelper()
        self.text = TextHelper()

    async def _call_llm(self, model: str, messages: list, max_tokens: int, max_retries: int = 1) -> str:
        timeout = httpx.Timeout(6.0, connect=4.0)
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                return response.choices[0].message.content.strip() or ""
            except (RateLimitError, APITimeoutError, APIConnectionError):
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** attempt
                await asyncio.sleep(wait)
        return ""

    def _build_section_refs(self, sections: list[dict]) -> str:
        if not sections:
            return ""
        lines = []
        for s in sections:
            act = s.get("act", "")
            sec = s.get("section_number", s.get("section", ""))
            title = s.get("section_title", s.get("title", ""))
            excerpt = s.get("excerpt", "")
            score = s.get("score", 0)
            parts = []
            if act:
                parts.append(act)
            if sec:
                parts.append(f"Section {sec}")
            citation = " — ".join(parts)
            lines.append(f"({citation}, Relevance: {round(score * 100)}%)")
            if title:
                lines.append(f"   - {title}")
            if excerpt:
                lines.append(f"   - Relevant excerpt: \"{excerpt[:150]}...\"")
        return "\n".join(lines)

    DOC_PLACEHOLDERS = {
        "[Landlord's Name]": "the Landlord",
        "[Landlord's Address]": "at their registered address",
        "[Your Name]": "[Your Name]",
        "[Your Address]": "[Your Address]",
        "[Amount]": "the relevant amount",
        "[Property Address]": "the subject property",
        "[City Name]": "[City Name]",
        "[Address]": "the relevant address",
        "[Start Date]": "[Start Date]",
        "[End Date]": "[End Date]",
        "[Date]": "[Date]",
        "[Phone Number]": "[Phone Number]",
        "[Email Address]": "[Email Address]",
        "[Company Name]": "the Employer",
        "[Company Address]": "at their registered address",
        "[Designation]": "[Designation]",
        "[Product/Service]": "the Product/Service",
        "[Recipient Name]": "the Recipient",
        "[Unpaid Period]": "the relevant period",
        "[Describe the issue briefly]": "[Describe the issue briefly]",
        "[Describe defect/deficiency in detail]": "[Describe the defect in detail]",
    }

    def _extract_case_info(self, description: str) -> dict:
        info = {}
        desc_lower = description.lower()

        # Try to extract monetary amount
        m = re.search(r'(?:rs\.?\s*|₹\s*|rupees?\s+)?(\d[\d,]+)\s*(?:rupees?|rs\.?|₹)?', description, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            if raw.isdigit():
                info["amount"] = raw

        # Try to extract landlord name (word after "landlord" or "my landlord")
        m = re.search(r'(?:my\s+)?landlord\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', description)
        if m:
            info["landlord_name"] = m.group(1)
        else:
            m = re.search(r'(?:my\s+)?landlord[,\s]+([A-Z][a-z]+)', description)
            if m:
                info["landlord_name"] = m.group(1)

        # Try to extract company/employer name
        m = re.search(r'(?:my\s+)?(?:employer|company)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})', description)
        if m:
            info["company_name"] = m.group(1)
            info["employer_name"] = m.group(1)

        # Try to extract tenant name
        m = re.search(r'(?:my\s+name\s+is\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', description)
        if m:
            info["your_name"] = m.group(1)

        return info

    def _render_doc_template(self, content: str, info: dict) -> str:
        result = content
        for placeholder, default in self.DOC_PLACEHOLDERS.items():
            key = placeholder.strip("[]").lower().replace("'", "").replace(" ", "_").replace("/", "_or_")
            if key == "your_name":
                value = info.get("your_name", info.get("tenant_name", default))
            elif key == "landlords_name":
                value = info.get("landlord_name", default)
            elif key == "amount":
                value = info.get("amount", default)
            elif key == "company_name":
                value = info.get("company_name", default)
            elif key == "product_or_service":
                value = info.get("product", default)
            else:
                value = info.get(key, default)
            result = result.replace(placeholder, value)
        return result

    def _build_evidence_section(self, ev_available: list[str], ev_missing: list[str], numbered: bool = False) -> str:
        lines = []
        if ev_available:
            lines.append("EVIDENCE IN POSSESSION:")
            for i, item in enumerate(ev_available):
                prefix = f"{i+1}. " if numbered else "- "
                lines.append(f"{prefix}{item}")
        if ev_missing:
            lines.append("\nEVIDENCE TO BE OBTAINED:")
            for i, item in enumerate(ev_missing):
                prefix = f"{len(ev_available)+i+1}. " if numbered else "- "
                lines.append(f"{prefix}{item}")
        if not ev_available and not ev_missing:
            lines.append("[Evidence list to be compiled]")
        return "\n".join(lines)

    def _generate_documents(self, description: str, sections: list[dict], section_refs: str,
                            ev_available: list[str], ev_missing: list[str],
                            evidence_missing_items: list[str], now_str: str) -> tuple[str, list[DocumentDTO]]:
        has_evidence = len(ev_available) > 0

        if has_evidence:
            evidence_summary = (
                f"The complainant has gathered the following evidence to support this claim:\n"
                + "\n".join(f"  {i+1}. {item}" for i, item in enumerate(ev_available))
            )
            if ev_missing:
                evidence_summary += (
                    f"\n\nThe complainant is in the process of obtaining the following additional evidence:\n"
                    + "\n".join(f"  {len(ev_available)+i+1}. {item}" for i, item in enumerate(ev_missing))
                )
            strength_note = (
                "The presence of this documented evidence significantly strengthens the complainant's position "
                "and establishes a clear factual basis for the claims made herein."
            )
        else:
            evidence_summary = (
                "The following evidence will be collected and submitted in support of this claim:\n"
                + "\n".join(f"  {i+1}. {item}" for i, item in enumerate(evidence_missing_items))
            )
            strength_note = (
                "The complainant acknowledges that gathering the above evidence is critical to "
                "strengthening the case before proceeding with formal legal action."
            )

        notice_content = (
            f"LEGAL NOTICE FOR RETURN OF SECURITY DEPOSIT\n\n"
            f"TO:\n[Landlord's Name]\n[Landlord's Address]\n\n"
            f"FROM:\n[Your Name]\n[Your Address]\n\n"
            f"Date: {now_str}\n\n"
            f"SUBJECT: Legal notice demanding return of security deposit of Rs. [Amount]\n\n"
            f"Dear Sir/Madam,\n\n"
            f"I, [Your Name], was a tenant at your property located at [Property Address] "
            f"from [Start Date] to [End Date]. I paid a refundable security deposit of Rs. [Amount].\n\n"
            f"LEGAL GROUNDS (from database search):\n"
            f"{section_refs}\n\n"
            f"{evidence_summary}\n\n"
            f"{strength_note}\n\n"
            f"Your claim of damages is unsubstantiated. YOU ARE HEREBY CALLED UPON to pay Rs. [Amount] "
            f"within 15 days, failing which legal proceedings will be initiated.\n\n"
            f"Yours faithfully,\n[Your Name]\n[Phone Number]\n[Email Address]"
        )

        other_docs = [
            DocumentDTO(id="", case_id="", doc_type="demand_letter", title="Demand Letter for Deposit Refund", content=(
                f"FORMAL DEMAND LETTER\n"
                f"==============================\n\n"
                f"TO:\n[Landlord's Name]\n[Landlord's Address]\n\n"
                f"FROM:\n[Your Name]\n[Your Address]\n\n"
                f"Date: {now_str}\n\n"
                f"SUBJECT: Formal demand for refund of security deposit\n\n"
                f"Dear Sir/Madam,\n\n"
                f"This is a formal demand for the immediate refund of my security deposit. "
                f"This demand is made in conjunction with the Legal Notice served separately.\n\n"
                f"LEGAL GROUNDS:\n"
                f"Your refusal to refund the deposit is contrary to the following laws identified through case analysis from our database:\n"
                f"{section_refs}\n\n"
                f"The primary match ({round(sections[0]['score']*100)}% relevance) is {sections[0]['act']} "
                f"Section {sections[0]['section_number']} ({sections[0]['section_title']}), which governs lessor "
                f"and lessee liabilities. The {sections[2]['act']} Section {sections[2]['section_number']} "
                f"({round(sections[2]['score']*100)}% relevance) specifically addresses security deposit refunds.\n\n"
                f"{evidence_summary}\n\n"
                f"{strength_note}\n\n"
                f"DEMAND:\n"
                f"You are hereby called upon to pay Rs. [Amount] within 7 days of receipt of this letter. "
                f"Failure to comply will result in immediate legal proceedings.\n\n"
                f"Yours faithfully,\n[Your Name]\n[Phone Number]\n[Email Address]"
            )),
            DocumentDTO(id="", case_id="", doc_type="complaint", title="Complaint to Rent Controller", content=(
                f"COMPLAINT BEFORE THE RENT CONTROLLER\n"
                f"==============================\n\n"
                f"BEFORE THE OFFICE OF THE RENT CONTROLLER\n[City Name]\n\n"
                f"COMPLAINT NO: _____\n\n"
                f"IN THE MATTER OF:\n[Your Name] … Complainant\nVS\n[Landlord's Name] … Respondent\n\n"
                f"MOST RESPECTFULLY SHOWETH:\n\n"
                f"1. The complainant was a tenant at [Address] from [Date] to [Date].\n"
                f"2. The complainant paid a security deposit of Rs. [Amount] at the time of tenancy.\n"
                f"3. The complainant vacated the premises on [Date] after proper notice.\n"
                f"4. The respondent has failed to return the security deposit despite repeated demands and a formal legal notice.\n"
                f"5. The respondent alleges damages without providing any evidence or inspection report.\n\n"
                f"LEGAL PROVISIONS INVOKED:\n"
                f"This complaint is grounded in the following legal provisions identified through database search:\n"
                f"{section_refs}\n\n"
                f"The respondent's actions constitute:\n"
                f"a) Breach of contract under {sections[1]['act']} Section {sections[1]['section_number']} "
                f"({sections[1]['section_title']}) — the respondent has failed to return the deposit.\n"
                f"b) Violation of lessor-liability under {sections[0]['act']} Section {sections[0]['section_number']}.\n"
                f"c) Violation of {sections[2]['act']} Section {sections[2]['section_number']} — the specific tenancy "
                f"law provision governing security deposit refunds.\n"
                f"d) Unjust enrichment — the respondent is withholding money without legal basis.\n\n"
                f"EVIDENCE RELIED UPON:\n"
                f"{evidence_summary}\n\n"
                f"{strength_note}\n\n"
                f"PRAYER:\n"
                f"It is therefore most respectfully prayed that this Honourable Court may be pleased to:\n"
                f"a) Direct the respondent to return the security deposit of Rs. [Amount] with interest at 18% per annum.\n"
                f"b) Award costs of the proceedings.\n"
                f"c) Pass any other order deemed fit.\n\n"
                f"Complainant\n[Your Name]\n[Date]"
            )),
        ]

        return notice_content, other_docs

    def _generate_action_plan(self, description: str, ev_available: list[str], ev_missing: list[str], all_items: list[str]) -> tuple[list[ActionStep], list[str]]:
        desc_lower = description.lower()
        steps = []
        num = 1

        # Evidence collection steps — personalized per missing item
        ev_prompts = {
            "Rental agreement / lease contract": "Locate your rental agreement or request a copy from the landlord",
            "Deposit payment receipt or bank transfer record": "Obtain bank statements showing the security deposit transaction",
            "Written communication with landlord about the deposit": "Gather all emails, messages, or letters exchanged with the landlord about the deposit",
            "Photographs/video of apartment condition at move-in and move-out": "Collect dated photographs or video of the property condition at move-in and move-out",
            "Any repair bills or damage estimates the landlord claims": "Request written repair estimates or bills for any damages the landlord alleges",
            "Move-out inspection report (if any)": "Obtain the move-out inspection report from the landlord or building manager",
            "Witness statements from neighbours or building staff": "Speak to neighbours or building staff willing to provide written statements about the property condition",
        }

        # For items still missing, add a collection step
        for item in ev_missing:
            prompt = ev_prompts.get(item, f"Collect the following: {item}")
            steps.append(ActionStep(number=num, text=prompt, action_type="info_gathering", action_config={}, status="pending"))
            num += 1

        # For items already confirmed, add an acknowledgment/organization step
        if ev_available:
            have_list = "; ".join(ev_available[:3])
            suffix = f" and {len(ev_available)-3} more" if len(ev_available) > 3 else ""
            steps.append(ActionStep(number=num, text=f"You already have: {have_list}{suffix}. Organize them in a folder with dates and labels.", action_type="info_gathering", action_config={}, status="pending"))
            num += 1

        # Create a written timeline
        has_dates = any(kw in desc_lower for kw in ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "2023", "2024", "2025", "2026"])
        if has_dates:
            steps.append(ActionStep(number=num, text="Create a written timeline of events using the dates you mentioned — include move-in, vacate, and each communication with the landlord", action_type="info_gathering", action_config={}, status="pending"))
        else:
            steps.append(ActionStep(number=num, text="Create a detailed written timeline of all events — include move-in date, vacate date, and each communication with the landlord", action_type="info_gathering", action_config={}, status="pending"))
        num += 1

        # Demand letter
        steps.append(ActionStep(number=num, text="Send a formal demand letter to the landlord via registered post and email requesting deposit return within 7 days", action_type="generate_document", action_config={"doc_type": "demand_letter", "title": "Demand Letter"}, status="pending"))
        num += 1

        # Lawyer consultation
        steps.append(ActionStep(number=num, text="If no response within 7 days, consult a property lawyer — ask about limitation period, interest on delayed deposit, and jurisdiction for filing a recovery suit", action_type="info_gathering", action_config={}, status="pending"))
        num += 1

        # File complaint
        steps.append(ActionStep(number=num, text="File a complaint with the Rent Controller or file a civil suit for recovery of money with interest and costs", action_type="generate_document", action_config={"doc_type": "complaint", "title": "Legal Complaint"}, status="pending"))
        num += 1

        # Preserve evidence
        steps.append(ActionStep(number=num, text="Preserve all evidence — do not delete emails, messages, or call recordings. Take screenshots and back them up.", action_type="info_gathering", action_config={}, status="pending"))
        num += 1

        recommended = [
            f"Send a formal demand letter to the landlord via registered post AD and email (keep proof of delivery)",
            f"Collect and organize: {', '.join(all_items[:4])}",
            "Consult a property lawyer — ask about: limitation period for recovery suits, eligibility for interest, jurisdiction/forum for filing",
            "File a complaint with the Rent Controller if the landlord is unresponsive after 15 days",
            "Preserve all evidence — do not delete emails, messages, or call recordings",
        ]
        return steps, recommended

    def _mock_analysis(self, description: str, evidence_available_override: list[str] | None = None, evidence_missing_override: list[str] | None = None) -> AnalyzeResponseDTO:
        desc_lower = description.lower().strip()
        now_str = datetime.now(timezone.utc).strftime('%d %B %Y')

        # ── Nonsense / gibberish detection ─────────────────────────────
        nonsense_patterns = ["sigma", "alpha", "rizz", "gyatt", "skibidi", "lol", "xd", "asdf", "qwerty", "test", "123"]
        word_count = len(desc_lower.split())
        if word_count < 3 or any(p in desc_lower for p in nonsense_patterns):
            return AnalyzeResponseDTO(
                case_type="other",
                severity="low",
                legal_domain="Other",
                relevant_sections=[],
                legal_notice_draft="",
                summary="",
                next_steps=[],
                reasoning_trace="[mock] Nonsense or insufficient input detected",
                clarifying_questions=[],
                action_buttons=[],
                ai_message="I'm unable to process this input. Please describe your legal problem in detail so I can provide meaningful assistance.",
                case_readiness_score=0,
                evidence_available=[],
                evidence_missing=[],
                risk_level="low",
                recommended_actions=[],
                is_sufficient=False,
                law_docs_available=AVAILABLE_LAW_DOCS,
                law_docs_coverage="",
            )

        section_refs = ""
        evidence_suggestions = []

        # ── Classify case type ──────────────────────────────────────────
        is_tenancy = any(kw in desc_lower for kw in ["landlord", "tenant", "deposit", "rent", "evict", "lease", "thrown out", "kicked out", "locked out", "changed the lock", "put my stuff out", "illegal eviction"])
        is_consumer = any(kw in desc_lower for kw in ["consumer", "product", "defective", "service", "laptop", "refund", "warranty"])
        is_employment = any(kw in desc_lower for kw in ["salary", "employer", "wage", "termination", "fired", "employment"])

        if is_tenancy:
            case_type = "tenancy_dispute"
            legal_domain = "Landlord-Tenant"
            severity = "medium"
            risk = "medium"
            summary = "This appears to be a tenancy-related dispute. Based on your description, there may be legal grounds to pursue a claim."
            ai_message = "I've analyzed your tenancy issue. Let me outline the legal landscape and what you'll need to build a strong case."
            coverage = LAW_DOCS_COVERAGE_TENANCY
            sections = [
                {"act": "Transfer of Property Act, 1882", "chapter": "", "section_number": "108", "section_title": "Rights and liabilities of lessor and lessee", "score": 0.92, "vector_score": 0.89, "bm25_score": 0.85, "excerpt": "In the absence of a contract or local usage to the contrary, the lessee shall allow the lessor and his agents to enter upon the property and inspect the condition thereof at all reasonable hours."},
                {"act": "Indian Contract Act, 1872", "chapter": "", "section_number": "73", "section_title": "Compensation for loss or damage caused by breach of contract", "score": 0.88, "vector_score": 0.86, "bm25_score": 0.82, "excerpt": "When a contract has been broken, the party who suffers by such breach is entitled to receive, from the party who has broken the contract, compensation for any loss or damage caused to him thereby, which naturally arose in the usual course of business from such breach."},
                {"act": "Model Tenancy Act, 2021", "chapter": "", "section_number": "13", "section_title": "Security deposit and its refund", "score": 0.85, "vector_score": 0.83, "bm25_score": 0.80, "excerpt": "The landlord shall refund the security deposit to the tenant at the time of vacating the premises after deducting any amount due, if any, and shall provide a detailed statement of deductions."},
            ]
            evidence_missing_items = [
                "Rental agreement / lease contract",
                "Deposit payment receipt or bank transfer record",
                "Written communication with landlord about the deposit",
                "Photographs/video of apartment condition at move-in and move-out",
                "Any repair bills or damage estimates the landlord claims",
                "Move-out inspection report (if any)",
                "Witness statements from neighbours or building staff",
            ]
            evidence_suggestions = [
                "Obtain a written estimate from a contractor for any alleged damages",
                "Get a notarized affidavit from a neighbour confirming the property condition",
                "Request a formal move-out inspection report from the landlord in writing",
                "File a police complaint (Non-Cognizable Report) for harassment if applicable",
                "Get a legal consultation from a property lawyer and obtain a written opinion",
                "Collect bank statements showing the deposit payment transaction",
            ]

            section_refs = self._build_section_refs(sections)
            steps = []
            recommended = []

        else:
            # Consumer, employment, and unrecognized case types — not in knowledge base
            domain_map = {"consumer_dispute": "Consumer Protection", "employment_dispute": "Employment", "other": "Civil"}
            type_map = {"consumer_dispute": "consumer", "employment_dispute": "employment", "other": "this type of"}
            case_type = "consumer_dispute" if is_consumer else ("employment_dispute" if is_employment else "other")
            return AnalyzeResponseDTO(
                case_type=case_type,
                severity="low",
                legal_domain=domain_map.get(case_type, "Civil"),
                relevant_sections=[],
                legal_notice_draft="",
                other_documents=[],
                summary="",
                next_steps=[],
                reasoning_trace="[mock] Case type not in knowledge base",
                clarifying_questions=[],
                action_buttons=[],
                ai_message=f"Sorry, the laws for {type_map.get(case_type, 'this')} cases are currently not in our database. I can only assist with tenancy-related matters (landlord-tenant disputes, security deposit recovery, eviction, etc.) using the ingested laws.",
                case_readiness_score=0,
                evidence_available=[],
                evidence_missing=[],
                evidence_suggestions=[],
                risk_level="low",
                recommended_actions=[],
                is_sufficient=False,
                law_docs_available=AVAILABLE_LAW_DOCS,
                law_docs_coverage=LAW_DOCS_COVERAGE_LIMITED,
            )

        # ── Extract case info from description for document filling ────
        info = self._extract_case_info(description)

        # ── Calculate readiness score (brutally honest) ────────────────
        # No free points. Score reflects how ready the case actually is.
        #
        # Description Quality (0-30):
        #   - Has specific monetary amount: +5
        #   - Has specific dates or timeframes: +5
        #   - Has names of parties involved: +5
        #   - Describes specific events/actions taken: +5
        #   - Word count > 25 (not just a sentence): +5
        #   - Word count > 50 (genuinely detailed): +5
        #
        # Evidence Confirmed (0-50):
        #   Only counts when user explicitly confirms having evidence.
        #   Proportion of confirmed items * 50.
        #
        # Legal Strength (0-20):
        #   - Clear remedy sought (refund, repair, reinstatement): +10
        #   - Adverse action documented (eviction notice, refusal, damage): +10

        detail_score = 0

        # Specific monetary amount
        if re.search(r'(?:rs\.?\s*|₹\s*|rupees?\s+)\d+', desc_lower):
            detail_score += 5

        # Dates or timeframes
        date_keywords = ["january", "february", "march", "april", "may", "june",
                         "july", "august", "september", "october", "november", "december",
                         "2023", "2024", "2025", "2026", "2027",
                         "months ago", "weeks ago", "days ago", "year ago", "years ago",
                         "last month", "last week", "last year", "ago"]
        if any(kw in desc_lower for kw in date_keywords):
            detail_score += 5

        # Names of parties (capitalized words after "landlord", "tenant", "name is", etc.)
        name_patterns = [
            r'(?:my\s+)?landlord\s+[A-Z]',
            r'(?:my\s+)?name\s+is\s+[A-Z]',
            r'(?:landlord|tenant|owner|respondent)\s+[A-Z]',
        ]
        if any(re.search(p, description) for p in name_patterns):
            detail_score += 5

        # Specific events/actions described
        action_keywords = ["refusing", "refused", "served", "notified", "filed", "sent",
                           "demanded", "requested", "reported", "complained", "emailed",
                           "called", "visited", "inspected", "terminated", "evicted",
                           "damaged", "broken", "leaked", "flooded", "mold"]
        if sum(1 for kw in action_keywords if kw in desc_lower) >= 2:
            detail_score += 5

        # Word count thresholds
        if word_count > 25:
            detail_score += 5
        if word_count > 50:
            detail_score += 5

        detail_score = min(30, detail_score)

        # Evidence score: only when user confirms what they actually have
        if evidence_available_override is not None:
            ev_available = evidence_available_override
            if evidence_missing_override is not None:
                ev_missing = evidence_missing_override
            else:
                ev_missing = [e for e in evidence_missing_items if e not in ev_available]
            total_ev = len(ev_available) + len(ev_missing)
            ev_confirmed_pct = len(ev_available) / max(total_ev, 1)
            evidence_score = int(ev_confirmed_pct * 50)
        else:
            ev_available = []
            ev_missing = evidence_missing_items
            evidence_score = 0

        # Legal strength: clear grounds for a claim
        legal_score = 0
        remedy_keywords = ["refund", "return", "repair", "compensate", "reinstate",
                           "evict", "eviction", "terminate", "restore", "recover"]
        if any(kw in desc_lower for kw in remedy_keywords):
            legal_score += 10
        adverse_keywords = ["refusing", "refused", "illegally", "without notice",
                            "without consent", "damaged", "harass", "harassment",
                            "threatened", "locked out", "changed the lock"]
        if any(kw in desc_lower for kw in adverse_keywords):
            legal_score += 10

        readiness = min(100, detail_score + evidence_score + legal_score)

        # ── Generate documents with evidence context ──
        notice_content, other_docs = self._generate_documents(
            description, sections, section_refs, ev_available, ev_missing,
            evidence_missing_items, now_str
        )

        # ── Dynamically generate action plan based on description + evidence ──
        steps, recommended = self._generate_action_plan(description, ev_available, ev_missing, evidence_missing_items)

        # Render ready-to-use documents — fill placeholders
        notice = self._render_doc_template(notice_content, info)
        updated_other = []
        for doc in other_docs:
            rendered = self._render_doc_template(doc.content, info)
            updated_other.append(DocumentDTO(
                id=doc.id, case_id=doc.case_id, doc_type=doc.doc_type,
                title=doc.title, content=rendered,
                status=doc.status, created_at=doc.created_at, updated_at=doc.updated_at,
            ))

        return AnalyzeResponseDTO(
            case_type=case_type,
            severity=severity,
            legal_domain=legal_domain,
            relevant_sections=sections,
            legal_notice_draft=notice,
            other_documents=updated_other,
            summary=summary,
            next_steps=steps,
            reasoning_trace="[mock_analysis] API unavailable — using fallback analysis",
            clarifying_questions=[],
            action_buttons=[ActionButton(label="Download Documents", message="Download all generated documents", style="primary")],
            ai_message=ai_message,
            case_readiness_score=readiness,
            evidence_available=ev_available,
            evidence_missing=ev_missing,
            evidence_suggestions=evidence_suggestions,
            risk_level=risk,
            recommended_actions=recommended,
            is_sufficient=True,
            law_docs_available=AVAILABLE_LAW_DOCS,
            law_docs_coverage=coverage,
        )

    async def update_evidence(
        self,
        description: str,
        evidence_available: list[str],
        evidence_missing: list[str],
    ) -> AnalyzeResponseDTO:
        return self._mock_analysis(
            description,
            evidence_available_override=evidence_available,
            evidence_missing_override=evidence_missing,
        )

    async def analyze_case(self, request: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        description = request.description
        if request.language == "hi":
            description = await self.text.translate_to_english(description)

        reasoning_trace = []

        try:
            # ── Round 0: Check for vagueness ───────────────────────────────────
            return await self._run_llm_analysis(description, reasoning_trace)
        except (RateLimitError, APITimeoutError, APIConnectionError):
            reasoning_trace.append("[mock_analysis] API unavailable — using fallback analysis")
            return self._mock_analysis(description)

    async def _run_llm_analysis(self, description: str, reasoning_trace: list) -> AnalyzeResponseDTO:
        vague_prompt = (
            f"Problem: {description}\n\n"
            f"Is this legal problem description too vague to provide "
            f"meaningful legal advice? If yes, generate up to 3 clarifying "
            f"questions that would help understand the situation better.\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{"is_vague": true/false, '
            f'"clarifying_questions": [{{"question": "your question here", '
            f'"key": "short_key_for_this_question"}}]}}'
            f"\nIf not vague, set clarifying_questions to an empty array."
        )
        vague_text = await self._call_llm(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": vague_prompt},
            ],
            max_tokens=1000,
        )
        try:
            vague_result = _extract_json(vague_text)
        except ValueError:
            vague_result = {"is_vague": False, "clarifying_questions": []}
        is_vague = vague_result.get("is_vague", False)
        vague_questions = vague_result.get("clarifying_questions", [])
        reasoning_trace.append(f"[check_vagueness] is_vague={is_vague} questions={len(vague_questions)}")

        # ── Round 1: Classify case ────────────────────────────────────────────
        classify_prompt = (
            f"Problem: {description}\n\n"
            f"Classify this legal problem into a JSON object:\n"
            f'{{"case_type": "tenancy_dispute|property_ownership|property_registration|consumer_dispute|employment_dispute|other", '
            f'"severity": "low|medium|high|urgent", '
            f'"legal_domain": "Landlord-Tenant|Consumer Protection|Employment|Property|Criminal|Family|Other", '
            f'"reasoning": "brief reason"}}'
        )

        classify_text = await self._call_llm(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": classify_prompt},
            ],
            max_tokens=1000,
        )
        classification = _extract_json(classify_text)
        reasoning_trace.append(f"[classify_case] -> {classification}")

        # ── Round 2: Search law ───────────────────────────────────────────────
        search_prompt = (
            f"Case: {classification.get('case_type')} ({classification.get('severity')}). "
            f"{classification.get('reasoning', '')}\n\n"
            f"What specific search query should be used to find relevant Indian law sections?\n\n"
            f"Output a JSON object:\n"
            f'{{"query": "specific legal search terms"}}'
        )

        search_text = await self._call_llm(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": classify_prompt},
                {"role": "assistant", "content": classify_text},
                {"role": "user", "content": search_prompt},
            ],
            max_tokens=1000,
        )
        search_args = _extract_json(search_text)
        query = search_args.get("query", description)

        law_sections = await self.rag.search(query=query, top_k=5)
        reasoning_trace.append(f"[search_law: '{query}'] -> {len(law_sections)} results")

        # ── Round 3: Generate full analysis ───────────────────────────────────
        steps_prompt = (
            f"Problem: {description}\n\n"
            f"Classification: {json.dumps(classification, indent=2)}\n\n"
            f"Relevant laws:\n{json.dumps(law_sections, indent=2, default=str)}\n\n"
            f"Generate a complete legal analysis as JSON. Prefix with 'FINAL_JSON:' then the JSON. No markdown.\n\n"
            f"Keys:\n"
            f'  "ai_message" — warm conversational message (2-3 sentences)\n'
            f'  "summary" — case summary and recommended approach (2-3 sentences)\n'
            f'  "steps" — array of {{number, text, action_type (generate_document|wait|info_gathering), action_config: {{doc_type, title}}}}\n'
            f'  "legal_notice_draft" — plain text string (NOT a JSON object). A complete formal legal notice with TO, FROM, subject, body, legal grounds, demand clause, and signature. Use Indian legal format.\n'
            f'  "case_readiness_score" — integer 0-100. BE BRUTALLY HONEST. A vague one-liner = 0-10. A short description with some detail = 15-30. A detailed description with clear facts = 30-50. Detailed + confirmed evidence = 50-80. Fully documented case with all evidence = 80-100. Do NOT inflate this score.\n'
            f'  "evidence_available" — array of strings (evidence user likely has)\n'
            f'  "evidence_missing" — array of strings (evidence user still needs)\n'
            f'  "risk_level" — "low"|"medium"|"high"\n'
            f'  "recommended_actions" — array of plain text action recommendations\n'
        )

        final_text = await self._call_llm(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": steps_prompt},
            ],
            max_tokens=8000,
        )

        marker = "FINAL_JSON:"
        idx = final_text.rfind(marker)
        if idx >= 0:
            final_data = _extract_json(final_text[idx + len(marker):])
        else:
            final_data = _extract_json(final_text)

        steps_data = final_data.get("steps", [])
        action_steps = []
        for s in steps_data:
            action_steps.append(ActionStep(
                number=s.get("number", 1),
                text=s.get("text", ""),
                action_type=s.get("action_type", "info_gathering"),
                action_config=s.get("action_config", {}),
                status="pending",
            ))

        clarifying_questions = [
            ClarifyingQuestion(question=q.get("question", ""), key=q.get("key", ""))
            for q in (vague_questions + final_data.get("clarifying_questions", []))
        ]

        action_buttons_items = [
            ActionButton(label=ab.get("label", ""), message=ab.get("message", ""), style=ab.get("style", "default"))
            for ab in final_data.get("action_buttons", [])
        ]

        return AnalyzeResponseDTO(
            case_type=classification.get("case_type", "other"),
            severity=classification.get("severity", "medium"),
            legal_domain=classification.get("legal_domain", ""),
            relevant_sections=law_sections,
            legal_notice_draft=final_data.get("legal_notice_draft", ""),
            summary=final_data.get("summary", ""),
            next_steps=action_steps,
            reasoning_trace="\n".join(reasoning_trace),
            clarifying_questions=clarifying_questions,
            action_buttons=action_buttons_items,
            ai_message=final_data.get("ai_message", f"I've analyzed your case. Here's a step-by-step plan to help you resolve this matter."),
            case_readiness_score=final_data.get("case_readiness_score", 0),
            evidence_available=final_data.get("evidence_available", []),
            evidence_missing=final_data.get("evidence_missing", []),
            risk_level=final_data.get("risk_level", "medium"),
            recommended_actions=final_data.get("recommended_actions", []),
        )

    async def execute_action(
        self,
        request: ExecuteActionRequest,
        supabase_service=None,
    ) -> ExecuteActionResponse:
        if not supabase_service:
            return ExecuteActionResponse(
                reply="Internal error: database service not available.",
                done=True,
            )

        case = supabase_service.get_case_by_id(request.case_id)
        if not case:
            return ExecuteActionResponse(
                reply="Case not found.",
                done=True,
            )

        steps = case.get("next_steps", []) or []
        step = None
        for s in steps:
            if s.get("number") == request.step_number:
                step = s
                break
        if not step:
            return ExecuteActionResponse(
                reply="Step not found.",
                done=True,
            )

        action_type = step.get("action_type", "")
        if action_type != "generate_document":
            return ExecuteActionResponse(
                reply=f"Step {request.step_number}: {step.get('text', '')}",
                done=False,
                action_buttons=[ActionButton(label="Mark as done", message=f"Mark step {request.step_number} as completed", style="primary")],
            )

        action_config = step.get("action_config", {}) or {}
        doc_type = action_config.get("doc_type", "")
        doc_config = DOCUMENT_TYPES.get(doc_type)
        if not doc_config:
            doc_config = {
                "title": action_config.get("title", "Legal Document"),
                "required_info": ["details"],
                "info_labels": {"details": "Details of the matter"},
            }

        missing = [f for f in doc_config["required_info"] if f not in request.collected_info]
        if missing:
            questions = [
                ClarifyingQuestion(question=doc_config["info_labels"].get(f, f.replace("_", " ").title()), key=f)
                for f in missing
            ]
            return ExecuteActionResponse(
                reply=f"I need some information to draft the {doc_config['title']}. Please provide the following:",
                clarifying_questions=questions,
                missing_fields=missing,
                done=False,
            )

        description = case.get("description", "")
        case_type = case.get("case_type", "")
        severity = case.get("severity", "")
        relevant_sections = case.get("relevant_sections", []) or []

        gen_prompt = (
            f"You are drafting a legal document for an Indian legal case.\n\n"
            f"Document type: {doc_type}\n"
            f"Title: {doc_config['title']}\n\n"
            f"Case description (extract subject, facts, and relief from here):\n{description}\n"
            f"Case type: {case_type} ({severity})\n\n"
            f"Relevant law sections:\n{json.dumps(relevant_sections, indent=2, default=str)}\n\n"
            f"Personal details provided by the user:\n{json.dumps(request.collected_info, indent=2)}\n\n"
            f"Using the case description for the content and the personal details above for names/addresses, "
            f"generate the complete legal document in proper legal format.\n"
            f"Do NOT ask the user to re-explain their issue — everything needed is in the case description "
            f"and personal details above.\n"
            f"Use appropriate legal language, sections, and references.\n"
            f"Make it formal and ready for use.\n\n"
            f"Return ONLY valid JSON with these exact keys:\n"
            f'{{"content": "the full legal document text"}}\n\n'
            f"No markdown backticks. No extra text."
        )

        response = await self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": gen_prompt},
            ],
            max_tokens=16000,
        )
        gen_text = response.choices[0].message.content.strip() or ""
        try:
            gen_data = _extract_json(gen_text)
        except ValueError:
            gen_data = {"content": gen_text}

        doc_content = gen_data.get("content", gen_text)

        doc_id = _generate_doc_id()
        now = datetime.now(timezone.utc).isoformat()

        try:
            supabase_service.create_document({
                "id": doc_id,
                "case_id": request.case_id,
                "doc_type": doc_type,
                "title": doc_config["title"],
                "content": doc_content,
                "status": "draft",
            })
        except Exception as e:
            return ExecuteActionResponse(
                reply=f"I generated the document but could not save it. The database table `case_documents` may not exist. Error: {e}",
                document=DocumentDTO(
                    id=doc_id,
                    case_id=request.case_id,
                    doc_type=doc_type,
                    title=doc_config["title"],
                    content=doc_content,
                    status="draft",
                    created_at=now,
                ),
                done=True,
            )

        for s in steps:
            if s.get("number") == request.step_number:
                s["status"] = "completed"
                break
        supabase_service.update_case(request.case_id, {"next_steps": steps})

        document = DocumentDTO(
            id=doc_id,
            case_id=request.case_id,
            doc_type=doc_type,
            title=doc_config["title"],
            content=doc_content,
            status="draft",
            created_at=now,
        )

        return ExecuteActionResponse(
            reply=f"I've drafted the {doc_config['title']} for you. You can review and edit it in the document panel on the right.",
            document=document,
            done=True,
        )

    async def chat(self, request: ChatRequestDTO) -> ChatResponseDTO:
        system_content = (
            f"{self.legal.system_prompt()}\n\n"
            f"You are helping the user with their legal case. "
            f"Be conversational and helpful. If the user wants to create or edit a legal document, "
            f"you can generate the document content."
        )

        if request.current_notice_draft:
            system_content += (
                f"\n\nCurrent document draft:\n{request.current_notice_draft}\n\n"
                f"If the user asks to edit the draft, return the updated full text in 'updated_notice'. "
                f"Otherwise 'updated_notice' should be empty."
            )

        system_content += (
            "\n\nRespond with JSON containing these keys:\n"
            '{"reply": "your conversational reply", '
            '"updated_notice": "full updated text or empty string", '
            '"document": {"doc_type": "demand_letter", "title": "...", "content": "..."} or null, '
            '"clarifying_questions": [], '
            '"action_buttons": []}'
            "\nNo markdown backticks. No extra text."
        )

        messages = [
            {"role": "system", "content": system_content},
        ]
        for h in request.history:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": request.message})

        response = await self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            max_tokens=4000,
        )
        reply_text = response.choices[0].message.content or ""

        try:
            data = _extract_json(reply_text)
        except ValueError:
            data = {}

        doc_data = data.get("document")
        document = None
        if doc_data and doc_data.get("content"):
            document = DocumentDTO(
                id=_generate_doc_id(),
                case_id=request.case_id,
                doc_type=doc_data.get("doc_type", "legal_notice"),
                title=doc_data.get("title", "Legal Document"),
                content=doc_data.get("content", ""),
                status="draft",
                created_at=datetime.now(timezone.utc).isoformat(),
            )

        return ChatResponseDTO(
            reply=data.get("reply", reply_text),
            updated_notice=data.get("updated_notice", ""),
            updated_sections=data.get("updated_sections", []),
            clarifying_questions=[ClarifyingQuestion(**cq) for cq in data.get("clarifying_questions", [])],
            suggested_actions=[ActionButton(**ab) for ab in data.get("action_buttons", [])],
            document=document,
        )
