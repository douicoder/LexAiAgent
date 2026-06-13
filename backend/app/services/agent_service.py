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
                    return json.loads(text[start : i + 1])
    raise ValueError("No valid JSON object found in text")


def _generate_doc_id() -> str:
    return str(uuid.uuid4())


class AgentService:
    def __init__(self, rag: IRagService):
        self.client = AsyncOpenAI(
            api_key=settings.GITHUB_TOKEN,
            base_url="https://models.github.ai/inference",
        )
        # Second client with separate token for update_evidence (avoids rate limits)
        self.client2 = AsyncOpenAI(
            api_key=settings.GITHUB_TOKEN_2 or settings.GITHUB_TOKEN,
            base_url="https://models.github.ai/inference",
        )
        self.rag = rag
        self.legal = LegalHelper()
        self.text = TextHelper()

    async def _call_llm(
        self, model: str, messages: list, max_tokens: int, max_retries: int = 2, client=None
    ) -> str:
        timeout = httpx.Timeout(120.0, connect=15.0)
        use_client = client or self.client
        for attempt in range(max_retries):
            try:
                response = await use_client.chat.completions.create(
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
            return "No specific law sections matched."
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
                lines.append(f'   - Relevant excerpt: "{excerpt[:200]}..."')
        return "\n".join(lines)

    async def analyze_case(self, request: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        description = request.description
        if request.language == "hi":
            description = await self.text.translate_to_english(description)
        return await self._run_llm_analysis(description)

    async def update_evidence(
        self,
        description: str,
        evidence_available: list[str],
        evidence_missing: list[str],
    ) -> AnalyzeResponseDTO:
        evidence_context = (
            f"The user has confirmed they have the following evidence:\n"
            + "\n".join(f"- {e}" for e in evidence_available)
            + "\n\nThe following evidence is still missing:\n"
            + "\n".join(f"- {e}" for e in evidence_missing)
        )
        full_prompt = (
            f"Original case description:\n{description}\n\n"
            f"Updated evidence status:\n{evidence_context}\n\n"
            f"Regenerate the full legal analysis with updated documents reflecting the confirmed evidence. "
            f"Strengthen the legal documents by referencing the confirmed evidence. "
            f"Recalculate the case_readiness_score based on the evidence now available."
        )
        return await self._run_llm_analysis(full_prompt, use_client=self.client2)

    async def _run_llm_analysis(self, description: str, use_client=None) -> AnalyzeResponseDTO:
        reasoning_trace = []
        today = datetime.now(timezone.utc).strftime("%d %B %Y")
        client = use_client or self.client

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 1: Classify + Vagueness check (parallel, fast model)
        # ═══════════════════════════════════════════════════════════════════
        classify_prompt = (
            f"Problem: {description}\n\n"
            f"Classify this legal problem into a JSON object:\n"
            f'{{"case_type": "tenancy_dispute|property_ownership|property_registration|consumer_dispute|employment_dispute|family_dispute|criminal|other", '
            f'"severity": "low|medium|high|urgent", '
            f'"legal_domain": "Landlord-Tenant|Consumer Protection|Employment|Property|Criminal|Family|Other", '
            f'"user_role": "landlord|tenant|employer|employee|buyer|seller|complainant|respondent|other", '
            f'"reasoning": "brief reason"}}'
        )
        vague_prompt = (
            f"Problem: {description}\n\n"
            f"Is this too vague for legal advice? Return JSON:\n"
            f'{{"is_vague": true/false, "clarifying_questions": [{{"question": "...", "key": "..."}}]}}\n'
            f"Return is_vague: false if it mentions who the user is, what happened, or has 20+ words."
        )

        # Run classify and vagueness in parallel
        classify_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": classify_prompt},
        ], 1000, client=client)
        vague_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": vague_prompt},
        ], 1000, client=client)

        classify_text, vague_text = await asyncio.gather(classify_task, vague_task)

        try:
            classification = _extract_json(classify_text)
        except ValueError:
            classification = {"case_type": "other", "severity": "medium", "legal_domain": "Other", "user_role": "other", "reasoning": "Failed"}

        try:
            vague_result = _extract_json(vague_text)
        except ValueError:
            vague_result = {"is_vague": False, "clarifying_questions": []}

        is_vague = vague_result.get("is_vague", False)
        vague_questions = vague_result.get("clarifying_questions", [])
        reasoning_trace.append(f"[classify] {classification.get('case_type')} / {classification.get('user_role')}")

        if is_vague and vague_questions:
            return AnalyzeResponseDTO(
                case_type="other", severity="low", legal_domain="Other",
                relevant_sections=[], summary=[], next_steps=[],
                reasoning_trace="\n".join(reasoning_trace),
                clarifying_questions=[ClarifyingQuestion(question=q["question"], key=q["key"]) for q in vague_questions],
                ai_message="I need more information. Please answer these questions.",
                case_readiness_score=0, is_sufficient=False,
                law_docs_available=AVAILABLE_LAW_DOCS, law_docs_coverage="",
            )

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 2: Search RAG for relevant laws
        # ═══════════════════════════════════════════════════════════════════
        query = description  # default: use raw description
        try:
            search_text = await self._call_llm(FAST_MODEL, [
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": f"Given this legal case: {description}\n\nReturn ONLY a JSON: {{\"query\": \"search terms for Indian law\"}}"},
            ], 500, client=client)
            query = _extract_json(search_text).get("query", description)
        except ValueError:
            pass

        try:
            law_sections = await self.rag.search(query=query, top_k=5)
        except Exception as e:
            reasoning_trace.append(f"[rag] error: {e}")
            law_sections = []

        reasoning_trace.append(f"[rag] query='{query}' -> {len(law_sections)} results")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 3: Generate all parts in PARALLEL (small individual calls)
        # ═══════════════════════════════════════════════════════════════════
        section_refs = self._build_section_refs(law_sections)
        case_type = classification.get("case_type", "other")
        user_role = classification.get("user_role", "other")
        severity = classification.get("severity", "medium")
        legal_domain = classification.get("legal_domain", "")

        base_context = (
            f"Case: {description}\n"
            f"Type: {case_type} | Role: {user_role} | Severity: {severity}\n"
            f"Laws:\n{section_refs}\n"
            f"Date: {today}\n"
        )

        # --- Call A: Evidence + Readiness + Summary + Risk ---
        evidence_prompt = (
            f"{base_context}\n"
            f"Return ONLY valid JSON with these keys:\n"
            f'{{"summary": "2-3 sentence case summary", '
            f'"ai_message": "warm 2-3 sentence message to the user", '
            f'"evidence_missing": ["evidence item 1", ...], '
            f'"evidence_suggestions": ["suggestion 1", ...], '
            f'"evidence_available": ["likely evidence 1", ...], '
            f'"case_readiness_score": 0-100, '
            f'"risk_level": "low|medium|high", '
            f'"recommended_actions": ["action 1", ...]}}\n'
            f"Readiness: 0-10 vague, 15-30 short, 30-50 detailed, 50-80+detailed with evidence, 80-100 fully documented."
        )

        # --- Call B: Legal Notice ---
        notice_prompt = (
            f"{base_context}\n"
            f"Generate a formal LEGAL NOTICE in Indian legal format.\n"
            f"Write FROM the user ({user_role}) TO the opposing party.\n"
            f"Include: TO, FROM, Date, Subject, body with legal grounds, demand clause, signature.\n"
            f"Reference the law sections above. Be specific to this case.\n"
            f"Return ONLY the plain text of the legal notice. No JSON."
        )

        # --- Call C: Other Documents (demand letter + complaint) ---
        docs_prompt = (
            f"{base_context}\n"
            f"Generate TWO documents as JSON:\n"
            f'1. A formal DEMAND LETTER from the {user_role} to the opposing party.\n'
            f"2. A COMPLAINT/PETITION for filing with the appropriate authority.\n"
            f"Both must reference the law sections above and be specific to this case.\n"
            f"Return ONLY valid JSON:\n"
            f'{{"other_documents": [{{"doc_type": "demand_letter", "title": "...", "content": "..."}}, {{"doc_type": "complaint", "title": "...", "content": "..."}}]}}'
        )

        # --- Call D: Action Plan ---
        plan_prompt = (
            f"{base_context}\n"
            f"Generate a concrete action plan as JSON.\n"
            f"Each step: number, text, action_type ('generate_document'|'info_gathering'|'wait'), action_config ({{doc_type, title}} if generate_document).\n"
            f"Return ONLY valid JSON:\n"
            f'{{"next_steps": [{{"number": 1, "text": "...", "action_type": "...", "action_config": {{}}}}], '
            f'"action_buttons": [{{"label": "...", "message": "...", "style": "primary"}}]}}'
        )

        # Fire all 4 in parallel
        notice_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": notice_prompt},
        ], 4000, client=client)

        evidence_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": evidence_prompt},
        ], 2000, client=client)

        docs_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": docs_prompt},
        ], 6000, client=client)

        plan_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": plan_prompt},
        ], 2000, client=client)

        notice_text, evidence_text, docs_text, plan_text = await asyncio.gather(
            notice_task, evidence_task, docs_task, plan_task
        )

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 4: Parse all results
        # ═══════════════════════════════════════════════════════════════════
        # Parse evidence/summary
        try:
            evidence_data = _extract_json(evidence_text)
        except ValueError:
            evidence_data = {}

        # Parse legal notice (plain text, no JSON)
        legal_notice = notice_text.strip()

        # Parse other documents
        try:
            docs_data = _extract_json(docs_text)
        except ValueError:
            docs_data = {}

        other_documents = []
        for doc in docs_data.get("other_documents", []):
            other_documents.append(DocumentDTO(
                id=_generate_doc_id(), case_id="",
                doc_type=doc.get("doc_type", "document"),
                title=doc.get("title", "Legal Document"),
                content=doc.get("content", ""), status="draft",
            ))

        # Parse action plan
        try:
            plan_data = _extract_json(plan_text)
        except ValueError:
            plan_data = {}

        action_steps = []
        for s in plan_data.get("next_steps", []):
            action_steps.append(ActionStep(
                number=s.get("number", 1),
                text=s.get("text", ""),
                action_type=s.get("action_type", "info_gathering"),
                action_config=s.get("action_config", {}),
                status="pending",
            ))

        action_buttons = [
            ActionButton(label=ab.get("label", ""), message=ab.get("message", ""), style=ab.get("style", "default"))
            for ab in plan_data.get("action_buttons", [])
        ]

        reasoning_trace.append(f"[done] notice={len(legal_notice)} chars, docs={len(other_documents)}, steps={len(action_steps)}")

        return AnalyzeResponseDTO(
            case_type=case_type,
            severity=severity,
            legal_domain=legal_domain,
            relevant_sections=law_sections,
            legal_notice_draft=legal_notice,
            other_documents=other_documents,
            summary=evidence_data.get("summary", ""),
            next_steps=action_steps,
            reasoning_trace="\n".join(reasoning_trace),
            clarifying_questions=[ClarifyingQuestion(question=q.get("question", ""), key=q.get("key", "")) for q in vague_questions],
            action_buttons=action_buttons or [ActionButton(label="Download Documents", message="Download all generated documents", style="primary")],
            ai_message=evidence_data.get("ai_message", "I've analyzed your case. Here's a step-by-step plan to help you resolve this matter."),
            case_readiness_score=evidence_data.get("case_readiness_score", 0),
            evidence_available=evidence_data.get("evidence_available", []),
            evidence_missing=evidence_data.get("evidence_missing", []),
            evidence_suggestions=evidence_data.get("evidence_suggestions", []),
            risk_level=evidence_data.get("risk_level", "medium"),
            recommended_actions=evidence_data.get("recommended_actions", []),
            is_sufficient=True,
            law_docs_available=AVAILABLE_LAW_DOCS,
            law_docs_coverage=self._get_coverage(case_type),
        )

    def _get_coverage(self, case_type: str) -> str:
        tenancy_types = ["tenancy_dispute", "property_ownership", "property_registration"]
        if case_type in tenancy_types:
            return (
                "This case is within our knowledge base. The following law documents "
                "have been ingested and were used for legal analysis: "
                + ", ".join(AVAILABLE_LAW_DOCS)
                + ". These cover tenancy, property transfer, and registration matters."
            )
        return (
            "[!] Limited law documents available in the database. "
            "Currently ingested: "
            + ", ".join(AVAILABLE_LAW_DOCS)
            + ". Your case type may not be fully covered by the available legal corpus. "
            "Consider consulting a qualified legal professional for case-specific advice."
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
            return ExecuteActionResponse(reply="Case not found.", done=True)

        steps = case.get("next_steps", []) or []
        step = None
        for s in steps:
            if s.get("number") == request.step_number:
                step = s
                break
        if not step:
            return ExecuteActionResponse(reply="Step not found.", done=True)

        action_type = step.get("action_type", "")
        if action_type != "generate_document":
            return ExecuteActionResponse(
                reply=f"Step {request.step_number}: {step.get('text', '')}",
                done=False,
                action_buttons=[
                    ActionButton(
                        label="Mark as done",
                        message=f"Mark step {request.step_number} as completed",
                        style="primary",
                    )
                ],
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

        missing = [
            f for f in doc_config["required_info"] if f not in request.collected_info
        ]
        if missing:
            questions = [
                ClarifyingQuestion(
                    question=doc_config["info_labels"].get(
                        f, f.replace("_", " ").title()
                    ),
                    key=f,
                )
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
            supabase_service.create_document(
                {
                    "id": doc_id,
                    "case_id": request.case_id,
                    "doc_type": doc_type,
                    "title": doc_config["title"],
                    "content": doc_content,
                    "status": "draft",
                }
            )
        except Exception as e:
            return ExecuteActionResponse(
                reply=f"I generated the document but could not save it. Error: {e}",
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

        messages = [{"role": "system", "content": system_content}]
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
            clarifying_questions=[
                ClarifyingQuestion(**cq) for cq in data.get("clarifying_questions", [])
            ],
            suggested_actions=[
                ActionButton(**ab) for ab in data.get("action_buttons", [])
            ],
            document=document,
        )


# Needed for execute_action
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
