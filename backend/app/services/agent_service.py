import asyncio
from dataclasses import dataclass
import json
import logging
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
    LegalOptionDTO,
)
from app.helpers.legal_helper import LegalHelper
from app.helpers.text_helper import TextHelper
from app.interfaces.i_rag_service import IRagService
logger = logging.getLogger(__name__)


@dataclass
class MetaResult:
    classification: dict
    is_vague: bool
    clarifying_questions: list


LLM_MODEL = settings.LLM_MODEL
FAST_MODEL = settings.FAST_MODEL

AVAILABLE_LAW_DOCS = [
    "Model Tenancy Act, 2021",
    "Transfer of Property Act, 1882",
    "Registration Act, 1908",
]


def _extract_json(text: str) -> dict:
    text = text.strip()
    if not text:
        return {}
        
    import json
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
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        pass
                        
    # FALLBACK: If JSON is truncated or invalid, manually extract fields via regex
    import re
    result = {}
    
    # 1. Extract string fields ("key": "value")
    for match in re.finditer(r'"([^"]+)"\s*:\s*"([^"]+)"', text):
        result[match.group(1)] = match.group(2)
        
    # 2. Extract integer/boolean fields ("key": 123)
    for match in re.finditer(r'"([^"]+)"\s*:\s*(\d+|true|false)', text, re.IGNORECASE):
        key = match.group(1)
        val = match.group(2).lower()
        if val == "true": result[key] = True
        elif val == "false": result[key] = False
        else: result[key] = int(val)
        
    # 3. Extract string arrays ("key": ["val1", "val2"]) even if truncated
    # Append ] to satisfy the non-greedy match if truncated
    for match in re.finditer(r'"([^"]+)"\s*:\s*\[(.*?)\]', text + "]", re.DOTALL):
        key = match.group(1)
        if key not in result: # Don't overwrite if parsed differently
            arr_text = match.group(2)
            # Find all strings in the array content
            items = re.findall(r'"([^"]+)"', arr_text)
            if items:
                result[key] = items
                
    return result


def _generate_doc_id() -> str:
    return str(uuid.uuid4())


class AgentService:
    def __init__(self, rag: IRagService):
        self._api_key = settings.LLM_API_KEY or settings.GITHUB_TOKEN
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))
        self.client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=settings.LLM_BASE_URL,
            http_client=http_client,
        )
        http_client2 = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0))
        self.client2 = AsyncOpenAI(
            api_key=self._api_key,
            base_url=settings.LLM_BASE_URL,
            http_client=http_client2,
        )
        self.rag = rag
        self.legal = LegalHelper()
        self.text = TextHelper()

    async def _call_llm(
        self, model: str, messages: list, max_tokens: int, max_retries: int = 2, client=None
    ) -> str:
        timeout = httpx.Timeout(120.0, connect=15.0)
        use_client = client or self.client
        logger.debug(f"LLM call: model={model}, max_tokens={max_tokens}")
        for attempt in range(max_retries):
            try:
                response = await use_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    extra_body={"reasoning": {"enabled": True}},
                    timeout=timeout,
                )
                content = response.choices[0].message.content.strip() or ""
                logger.debug(f"LLM response: {len(content)} chars")
                return content
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
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

    async def improve_prompt(self, description: str) -> str:
        prompt = (
            f"Improve this legal case description for better analysis.\n\n"
            f"Original: {description}\n\n"
            f"Rules:\n"
            f"1. Add [SQUARE BRACKETS] for any missing personal details (names, addresses, phone numbers, emails)\n"
            f"2. Add [SQUARE BRACKETS] for missing dates, amounts, or property details\n"
            f"3. Add helpful hints inside brackets like [Your Name], [Landlord Name], [Property Address]\n"
            f"4. Keep the original meaning and facts intact\n"
            f"5. Make the language clearer and more specific\n"
            f"6. Structure it logically: who, what, when, where, how much\n"
            f"7. Do NOT invent any facts — only add placeholders for missing info\n\n"
            f"Return ONLY the improved description. No explanation, no JSON."
        )
        return await self._call_llm(FAST_MODEL, [
            {"role": "system", "content": "You are a legal assistant that improves case descriptions."},
            {"role": "user", "content": prompt},
        ], 2000)

    async def update_evidence(
        self,
        description: str,
        evidence_available: list[str],
        evidence_missing: list[str],
        document_modifications: dict[str, str] | None = None,
    ) -> AnalyzeResponseDTO:
        confirmed_list = "\n".join(f"- {e}" for e in evidence_available) if evidence_available else "None"
        missing_list = "\n".join(f"- {e}" for e in evidence_missing) if evidence_missing else "None"

        mod_context = ""
        if document_modifications:
            mod_parts = []
            for doc_type, content in document_modifications.items():
                if content.strip():
                    mod_parts.append(f"User's modified {doc_type}:\n{content[:2000]}")
            if mod_parts:
                mod_context = "\n\nUser has modified these documents. Preserve their changes and strengthen the rest:\n" + "\n\n".join(mod_parts)

        full_prompt = (
            f"Original case description:\n{description}\n\n"
            f"=== EVIDENCE STATUS (USE THIS EXACTLY) ===\n"
            f"CONFIRMED evidence (user HAS these — treat as FACTS, reference in documents):\n{confirmed_list}\n\n"
            f"MISSING evidence (user does NOT have these — do NOT reference as available):\n{missing_list}\n"
            f"=== END EVIDENCE STATUS ===\n"
            f"{mod_context}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Treat CONFIRMED evidence as factual. Reference them in legal documents.\n"
            f"2. Do NOT generate new evidence items. Use ONLY the lists above.\n"
            f"3. evidence_missing in your response should ONLY contain items from the MISSING list above.\n"
            f"4. evidence_available in your response should ONLY contain items from the CONFIRMED list above.\n"
            f"5. Strengthen legal documents by referencing confirmed evidence specifically.\n"
            f"6. Recalculate case_readiness_score: more confirmed evidence = higher score.\n"
            f"7. Preserve any user modifications to documents.\n"
            f"8. Use simple, clear language."
        )
        return await self._run_llm_analysis(full_prompt, use_client=self.client2)

    async def meta_call(self, description: str, client=None) -> "MetaResult":
        """Single LLM call that classifies the case AND checks vagueness."""
        meta_prompt = (
            f"Problem: {description}\n\n"
            f"Analyze this legal problem and return ONE JSON object:\n"
            f'{{"case_type": "tenancy_dispute|property_ownership|property_registration|consumer_dispute|employment_dispute|family_dispute|criminal|other", '
            f'"severity": "low|medium|high|urgent", '
            f'"legal_domain": "Landlord-Tenant|Consumer Protection|Employment|Property|Criminal|Family|Other", '
            f'"user_role": "landlord|tenant|employer|employee|buyer|seller|complainant|respondent|other", '
            f'"reasoning": "brief reason", '
            f'"is_vague": true/false, '
            f'"clarifying_questions": [{{"question": "...", "key": "..."}}]}}\n'
            f"Set is_vague: false if the problem mentions who the user is, what happened, or has 20+ words."
        )
        text = await self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": meta_prompt},
        ], 1200, client=client)
        try:
            data = _extract_json(text)
        except ValueError:
            data = {}
        classification = {
            "case_type": data.get("case_type", "other"),
            "severity": data.get("severity", "medium"),
            "legal_domain": data.get("legal_domain", "Other"),
            "user_role": data.get("user_role", "other"),
            "reasoning": data.get("reasoning", "Failed"),
        }
        return MetaResult(
            classification=classification,
            is_vague=bool(data.get("is_vague", False)),
            clarifying_questions=data.get("clarifying_questions", []) or [],
        )

    async def _rewrite_query(self, description: str, client=None) -> str:
        """Improve the RAG search query. Runs in parallel with meta_call."""
        try:
            search_text = await self._call_llm(FAST_MODEL, [
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": f"Given this legal case: {description}\n\nReturn ONLY a JSON: {{\"query\": \"search terms for Indian law\"}}"},
            ], 500, client=client)
            return _extract_json(search_text).get("query", description)
        except Exception:
            return description

    async def _generate_options(
        self, description: str, case_type: str, section_refs: str
    ) -> tuple[list[LegalOptionDTO], str]:
        """Generate 3-4 distinct Indian legal remedies with a comparison note."""
        opts_prompt = (
            "You are a practical Indian legal advisor. For the case below, propose "
            "3 to 4 DISTINCT legal remedies or forums the user can pursue (e.g., "
            "Legal Notice, Rent Authority / Civil Suit, Mediation, Consumer Forum).\n\n"
            "For EACH option return an object with exactly these fields:\n"
            "- id: short id like 'opt-001'\n"
            "- name: remedy name\n"
            "- forum: where it is pursued\n"
            "- tagline: one-line summary (optional)\n"
            "- recommended: boolean — EXACTLY ONE option must be true\n"
            "- cost_range: e.g. 'Rs.500-2,000'\n"
            "- time_range: e.g. '7-15 days'\n"
            "- effort: one of 'Low' | 'Medium' | 'High'\n"
            "- success_likelihood: integer 0-100\n"
            "- risk_level: one of 'low' | 'medium' | 'high'\n"
            "- pros: list of strings (non-empty)\n"
            "- cons: list of strings (non-empty)\n"
            "- evidence_required: list of strings\n"
            "- best_for: one of 'cost' | 'time' | 'success' | 'risk' | 'control'\n"
            "- interoperability_note: string explaining how this option relates to the others\n"
            "- next_steps: list of actionable strings (non-empty)\n"
            "- applicable_documents: list of strings\n\n"
            "Also return a top-level 'comparison_note' string (one sentence) summarizing "
            "trade-offs across all options.\n\n"
            "Return ONLY valid JSON of the form:\n"
            '{"options": [ ... ], "comparison_note": "..."}\n\n'
            f"Case type: {case_type}\n\n"
            f"Case description:\n{description}\n\n"
            f"Relevant laws:\n{section_refs}\n"
        )
        try:
            raw = await self._call_llm(
                FAST_MODEL,
                [
                    {"role": "system", "content": self.legal.system_prompt()},
                    {"role": "user", "content": opts_prompt},
                ],
                3000,
                client=self.client,
            )
            data = _extract_json(raw)
            options: list[LegalOptionDTO] = []
            for o in data.get("options", []):
                if not isinstance(o, dict):
                    continue
                opt = LegalOptionDTO(
                    id=str(o.get("id", f"opt-{len(options) + 1:03d}")),
                    name=str(o.get("name", "Legal Option")),
                    forum=str(o.get("forum", "")),
                    tagline=str(o.get("tagline", "")),
                    recommended=bool(o.get("recommended", False)),
                    cost_range=str(o.get("cost_range", "")),
                    time_range=str(o.get("time_range", "")),
                    effort=str(o.get("effort", "")),
                    success_likelihood=int(o.get("success_likelihood", 0) or 0),
                    risk_level=str(o.get("risk_level", "medium")),
                    pros=[str(x) for x in (o.get("pros") or [])],
                    cons=[str(x) for x in (o.get("cons") or [])],
                    evidence_required=[str(x) for x in (o.get("evidence_required") or [])],
                    best_for=str(o.get("best_for", "")),
                    interoperability_note=str(o.get("interoperability_note", "")),
                    next_steps=[str(x) for x in (o.get("next_steps") or [])],
                    applicable_documents=[str(x) for x in (o.get("applicable_documents") or [])],
                )
                options.append(opt)

            # Enforce exactly one recommended option
            if not any(o.recommended for o in options) and options:
                options[0].recommended = True
            else:
                seen = False
                for o in options:
                    if o.recommended and not seen:
                        seen = True
                    elif o.recommended and seen:
                        o.recommended = False

            comparison_note = str(data.get("comparison_note", ""))
            if not options:
                return self._options_fallback(description)
            return options, comparison_note
        except Exception as e:
            logger.warning(f"[options] generation failed: {e}")
            return self._options_fallback(description)

    def _options_fallback(self, description: str) -> tuple[list[LegalOptionDTO], str]:
        opt = LegalOptionDTO(
            id="opt-001",
            name="Legal Notice",
            forum="Advocate + Registered Post / Email",
            tagline="Fastest, cheapest first step to recover deposit",
            recommended=True,
            cost_range="Rs.500-2,000",
            time_range="7-15 days",
            effort="Low",
            success_likelihood=70,
            risk_level="low",
            pros=["Cheap and fast", "Often recovers deposit without court", "Preserves relationship"],
            cons=["No binding order if ignored", "May need follow-up suit"],
            evidence_required=["UPI/rent payment proofs", "Lock-out evidence", "Landlord contact details"],
            best_for="time",
            interoperability_note="Notice is a prerequisite for a civil suit and can run parallel to mediation.",
            next_steps=[
                "Draft notice with facts + 15-day compliance deadline",
                "Send via registered post / email",
                "Keep proof of delivery",
            ],
            applicable_documents=["Legal Notice Template", "Model Tenancy Act Section 11"],
        )
        return [opt], "Consult a qualified advocate to choose the best forum for your facts."

    async def _run_llm_analysis(self, description: str, use_client=None) -> AnalyzeResponseDTO:
        reasoning_trace = []
        today = datetime.now(timezone.utc).strftime("%d %B %Y")
        client = use_client or self.client
        logger.info(f"Starting analysis: {len(description)} chars, model={FAST_MODEL}")

        # ═══════════════════════════════════════════════════════════════════
        # STAGE 1 (parallel): classify+vagueness (meta_call) + query rewrite
        # ═══════════════════════════════════════════════════════════════════
        meta_result, rewritten_query = await asyncio.gather(
            self.meta_call(description, client),
            self._rewrite_query(description, client),
        )
        classification = meta_result.classification
        is_vague = meta_result.is_vague
        vague_questions = meta_result.clarifying_questions
        logger.info(f"Classification: type={classification.get('case_type')}, role={classification.get('user_role')}, vague={is_vague}")
        reasoning_trace.append(f"[classify] {classification.get('case_type')} / {classification.get('user_role')}")

        if is_vague:
            return AnalyzeResponseDTO(
                case_type="other", severity="low", legal_domain="Other",
                relevant_sections=[], summary="Insufficient data to proceed. Currently our database only has documents regarding: Model Tenancy Act, 2021, Transfer of Property Act, 1882, Registration Act, 1908. Please provide more details about your case.", next_steps=[],
                reasoning_trace="\n".join(reasoning_trace),
                clarifying_questions=[],
                ai_message="Not enough data to proceed. Please provide more details: what happened, who is involved, when did it happen, and any amounts or documents you have.",
                case_readiness_score=0, is_sufficient=False,
                law_docs_available=AVAILABLE_LAW_DOCS, law_docs_coverage="",
            )

        # ═══════════════════════════════════════════════════════════════════
        # STAGE 2: RAG search with the rewritten query (rewrite ran in parallel)
        # ═══════════════════════════════════════════════════════════════════
        try:
            law_sections = await self.rag.search(query=rewritten_query, top_k=5)
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")
            reasoning_trace.append(f"[rag] error: {e}")
            law_sections = []

        logger.info(f"RAG search: query='{rewritten_query[:50]}...' -> {len(law_sections)} results")
        reasoning_trace.append(f"[rag] query='{rewritten_query}' -> {len(law_sections)} results")

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 3: Generate all parts in PARALLEL (small individual calls)
        # ═══════════════════════════════════════════════════════════════════
        section_refs = self._build_section_refs(law_sections)
        case_type = classification.get("case_type", "other")
        user_role = classification.get("user_role", "other")
        severity = classification.get("severity", "medium")
        legal_domain = classification.get("legal_domain", "")

        # Options generation (runs in parallel with the 4 generation calls below)
        options_task = self._generate_options(description, case_type, section_refs)

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
            f'{{"summary": "2-3 sentence case summary in plain language", '
            f'"ai_message": "warm 2-3 sentence message to the user in plain language", '
            f'"evidence_missing": ["evidence item 1", "evidence item 2", ...], '
            f'"evidence_suggestions": ["suggestion 1", ...], '
            f'"evidence_available": ["likely evidence 1", ...], '
            f'"case_readiness_score": 0-100, '
            f'"risk_level": "low|medium|high", '
            f'"recommended_actions": ["action 1", ...]}}\n'
            f"BRUTALLY HONEST readiness scoring: "
            f"0-10 very vague with almost no detail, "
            f"15-30 short description but missing key facts (names, dates, amounts), "
            f"30-50 detailed but NO evidence attached, "
            f"50-70 detailed with SOME evidence but gaps remain, "
            f"70-85 strong case with good evidence, "
            f"85-100 fully documented with strong evidence and clear legal basis.\n"
            f"IMPORTANT: Do NOT give high scores to vague or incomplete descriptions. "
            f"If the user has not provided names, dates, amounts, or evidence, score below 30.\n"
            f"CRITICAL: You MUST return evidence_missing as an array with at least 3-5 specific evidence items "
            f"that would strengthen this case (e.g., lease agreement, payment receipts, photos, chat messages, etc.). "
            f"Never return an empty evidence_missing array.\n"
            f"Use simple, clear language anyone can understand."
        )

        # --- Call B: Legal Notice ---
        notice_prompt = (
            f"Generate a LEGAL NOTICE document.\n\n"
            f"Case facts: {description}\n"
            f"User role: {user_role}\n"
            f"Applicable laws: {section_refs}\n\n"
            f"FORMAT — follow this EXACTLY, no extra text:\n"
            f"---\n"
            f"LEGAL NOTICE\n\n"
            f"TO:\n[OPPOSING PARTY NAME]\n[OPPOSING PARTY ADDRESS]\n\n"
            f"FROM:\n[YOUR NAME]\n[YOUR ADDRESS]\n\n"
            f"Date: {today}\n\n"
            f"SUBJECT: [brief subject]\n\n"
            f"Dear Sir/Madam,\n\n"
            f"[2-3 paragraphs: state the facts, cite the legal grounds with specific sections, state the demand]\n\n"
            f"DEMAND:\n[clear demand with deadline]\n\n"
            f"Yours faithfully,\n[YOUR NAME]\n[YOUR PHONE]\n[YOUR EMAIL]\n---\n\n"
            f"IMPORTANT: Use [SQUARE BRACKETS] for ALL names, addresses, phone numbers, emails, and amounts. "
            f"DO NOT invent or hallucinate any personal details. The user will fill these in later.\n"
            f"Use simple, clear language anyone can understand.\n"
            f"Return ONLY the document text between the --- markers. No analysis, no JSON, no explanation."
        )

        # --- Call C: Other Documents (demand letter + complaint) ---
        docs_prompt = (
            f"Generate TWO legal documents as JSON.\n\n"
            f"Case facts: {description}\n"
            f"User role: {user_role}\n"
            f"Applicable laws: {section_refs}\n\n"
            f"DOCUMENT 1 - Demand Letter: Formal demand from {user_role} to opposing party. 2-3 paragraphs.\n"
            f"DOCUMENT 2 - Complaint: Formal complaint/petition for filing. Structured with facts, legal grounds, prayer.\n\n"
            f"IMPORTANT: Use [SQUARE BRACKETS] for ALL names, addresses, phone numbers, emails, and amounts. "
            f"DO NOT invent or hallucinate any personal details.\n"
            f"Use simple, clear language anyone can understand.\n"
            f"Both must be clean legal documents. No analysis text, no reasoning.\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{"other_documents": [{{"doc_type": "demand_letter", "title": "Demand Letter", "content": "full document text here"}}, {{"doc_type": "complaint", "title": "Complaint", "content": "full document text here"}}]}}'
        )

        # --- Call D: Action Plan ---
        plan_prompt = (
            f"Generate a step-by-step action plan for this legal case.\n\n"
            f"Case: {description}\n"
            f"User role: {user_role}\n\n"
            f"CRITICAL RULES:\n"
            f"1. Each step MUST be ONE single action only.\n"
            f"2. Do NOT combine multiple actions into one step.\n"
            f"3. Do NOT say 'and' within a step — if you use 'and', split into two steps.\n"
            f"4. Each step should be 1-2 sentences maximum.\n"
            f"5. Generate at least 5-6 steps.\n\n"
            f"BAD examples (DO NOT do this):\n"
            f'- "Collect evidence AND file complaint AND seek legal advice"\n'
            f'- "Preserve all documents, take photos, and keep a log"\n\n'
            f"GOOD examples (DO this):\n"
            f'- "Gather your lease agreement and any payment receipts"\n'
            f'- "Take photos of the property condition"\n'
            f'- "File a police complaint for illegal eviction"\n'
            f'- "Consult a lawyer about filing a compensation case"\n\n'
            f"Return ONLY valid JSON:\n"
            f'{{"next_steps": ['
            f'{{"number": 1, "text": "step description", "action_type": "info_gathering", "action_config": {{}}}}, '
            f'{{"number": 2, "text": "step description", "action_type": "generate_document", "action_config": {{"doc_type": "demand_letter", "title": "Demand Letter"}}}}'
            f'], '
            f'"action_buttons": [{{"label": "Download Documents", "message": "Download all generated documents", "style": "primary"}}]'
            f'}}'
        )

        # Fire all 4 in parallel
        notice_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": notice_prompt},
        ], 3000, client=client)

        evidence_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": evidence_prompt},
        ], 2000, client=client)

        docs_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": docs_prompt},
        ], 4000, client=client)

        plan_task = self._call_llm(FAST_MODEL, [
            {"role": "system", "content": self.legal.system_prompt()},
            {"role": "user", "content": plan_prompt},
        ], 2000, client=client)

        notice_text, evidence_text, docs_text, plan_text, options_result = await asyncio.gather(
            notice_task, evidence_task, docs_task, plan_task, options_task
        )
        legal_options, option_comparison_note = options_result

        # ═══════════════════════════════════════════════════════════════════
        # PHASE 4: Parse all results
        # ═══════════════════════════════════════════════════════════════════
        # Clean legal notice — strip any analysis/reasoning before the actual document
        legal_notice = self._clean_legal_notice(notice_text)
        legal_notice = legal_notice.replace("\\n", "\n")
        # Parse evidence/summary
        try:
            evidence_data = _extract_json(evidence_text)
        except ValueError:
            evidence_data = {}
        
        logger.info(f"Evidence raw text (first 500 chars): {evidence_text[:500]}")
        logger.info(f"Evidence data keys: {list(evidence_data.keys())}")
        logger.info(f"Evidence summary: '{evidence_data.get('summary', 'MISSING')}'")
        logger.info(f"Evidence score: {evidence_data.get('case_readiness_score', 'MISSING')}")
        logger.info(f"Evidence missing count: {len(evidence_data.get('evidence_missing', []))}")

        # Parse legal notice (cleaned)
        # legal_notice already set above by _clean_legal_notice

        # Parse other documents
        try:
            docs_data = _extract_json(docs_text)
        except ValueError:
            docs_data = {}

        other_documents = []
        for doc in docs_data.get("other_documents", []):
            content = doc.get("content", "")
            content = content.replace("\\n", "\n")
            other_documents.append(DocumentDTO(
                id=_generate_doc_id(), case_id="",
                doc_type=doc.get("doc_type", "document"),
                title=doc.get("title", "Legal Document"),
                content=content, status="draft",
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
            evidence_available=[str(x) for x in evidence_data.get("evidence_available", [])],
            evidence_missing=[str(x) for x in evidence_data.get("evidence_missing", [])],
            evidence_suggestions=[str(x) for x in evidence_data.get("evidence_suggestions", [])],
            risk_level=str(evidence_data.get("risk_level", "medium")),
            recommended_actions=[str(x) for x in evidence_data.get("recommended_actions", [])],
            is_sufficient=True,
            law_docs_available=AVAILABLE_LAW_DOCS,
            law_docs_coverage=self._get_coverage(case_type),
            legal_options=legal_options,
            option_comparison_note=option_comparison_note,
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

    def _clean_legal_notice(self, text: str) -> str:
        """Strip analysis/reasoning from LLM output, keep only the legal document."""
        text = text.strip()

        # Try to extract between --- markers if present
        if "---" in text:
            parts = text.split("---")
            # Take the content between first pair of --- markers
            if len(parts) >= 3:
                text = parts[1].strip()
            elif len(parts) == 2:
                text = parts[-1].strip()

        # Find the start of the actual document (look for LEGAL NOTICE header)
        lines = text.split("\n")
        start_idx = 0
        for i, line in enumerate(lines):
            lower = line.strip().lower()
            if any(kw in lower for kw in ["legal notice", "to:", "to:\n"]):
                start_idx = i
                break

        # Remove trailing analysis/reasoning
        end_idx = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            lower = lines[i].strip().lower()
            if any(kw in lower for kw in ["yours faithfully", "yours sincerely", "[name]", "[phone]", "[email]"]):
                end_idx = i + 1
                # Include any remaining signature lines
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        end_idx = j + 1
                break

        result = "\n".join(lines[start_idx:end_idx]).strip()

        # If result is too short or looks like analysis, return original
        if len(result) < 50:
            return text

        return result

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
            extra_body={"reasoning": {"enabled": True}},
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
            extra_body={"reasoning": {"enabled": True}},
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
