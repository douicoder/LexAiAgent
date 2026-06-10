import json

from openai import AsyncOpenAI

from app.config import settings
from app.dto.agent_dto import (
    ActionButton,
    AnalyzeRequestDTO,
    AnalyzeResponseDTO,
    ChatRequestDTO,
    ChatResponseDTO,
    ClarifyingQuestion,
    NextStep,
)
from app.helpers.legal_helper import LegalHelper
from app.helpers.text_helper import TextHelper
from app.interfaces.i_agent_service import IAgentService
from app.interfaces.i_rag_service import IRagService

LLM_MODEL = settings.LLM_MODEL
FAST_MODEL = "gpt-4o"


def _extract_json(text: str) -> dict:
    text = text.strip()

    for end in range(len(text) - 1, -1, -1):
        if text[end] != "}":
            continue

        depth = 0
        in_string = False
        escape = False
        start = -1

        for j in range(end, -1, -1):
            char = text[j]

            if escape:
                escape = False
                continue

            if char == "\\":
                escape = True
                continue

            if char == '"' and not escape:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "}":
                depth += 1
            elif char == "{":
                depth -= 1
                if depth == 0:
                    start = j
                    break

        if start >= 0 and depth == 0:
            return json.loads(text[start : end + 1])

    raise ValueError("No valid JSON object found in text")


class AgentService(IAgentService):
    def __init__(self, rag: IRagService):
        self.client = AsyncOpenAI(
            api_key=settings.GITHUB_TOKEN,
            base_url="https://models.github.ai/inference",
        )
        self.rag = rag
        self.legal = LegalHelper()
        self.text = TextHelper()

    async def analyze_case(self, request: AnalyzeRequestDTO) -> AnalyzeResponseDTO:
        description = request.description
        if request.language == "hi":
            description = await self.text.translate_to_english(description)

        reasoning_trace = []

        # ── Round 1: Classify case ────────────────────────────────────────────
        classify_prompt = (
            f"Problem: {description}\n\n"
            f"Classify this legal problem into a JSON object:\n"
            f'{{"case_type": "tenancy_dispute|property_ownership|property_registration|other", '
            f'"severity": "low|medium|high|urgent", '
            f'"reasoning": "brief reason"}}'
            f'\nWhere case_type means: tenancy_dispute = rent/deposit/eviction issues, '
            f'property_ownership = sale/transfer/title disputes, '
            f'property_registration = deed registration issues, '
            f'other = anything outside current knowledge base'
        )

        response = await self.client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": classify_prompt},
            ],
            max_tokens=1000,
        )
        classify_text = response.choices[0].message.content.strip()
        classification = _extract_json(classify_text)
        reasoning_trace.append(f"[classify_case] -> {classification}")

        # ── Round 2: Search law ───────────────────────────────────────────────
        search_prompt = (
            f"Case: {classification.get('case_type')} ({classification.get('severity')}). "
            f"{classification.get('reasoning', '')}\n\n"
            f"What specific search query should be used to find relevant Indian law sections for this case?\n\n"
            f"Output a JSON object:\n"
            f'{{"query": "specific legal search terms"}}'
        )

        response = await self.client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": classify_prompt},
                {"role": "assistant", "content": classify_text},
                {"role": "user", "content": search_prompt},
            ],
            max_tokens=1000,
        )
        search_text = response.choices[0].message.content.strip()
        search_args = _extract_json(search_text)
        query = search_args.get("query", description)

        law_sections = await self.rag.search(query=query, top_k=5)
        reasoning_trace.append(
            f"[search_law: '{query}'] -> {len(law_sections)} results"
        )

        # ── Round 3: Generate final output ────────────────────────────────────
        final_prompt = (
            f"Original problem: {description}\n"
            f"Person: {request.user_name}\n"
            f"Opponent: {request.opponent_name} ({request.opponent_address})\n\n"
            f"Case classification: {json.dumps(classification, indent=2)}\n\n"
            f"Relevant law sections found:\n{json.dumps(law_sections, indent=2, default=str)}\n\n"
            f"Generate final legal advice as JSON.\n"
            f"Return ONLY valid JSON with these exact keys. "
            f"No markdown backticks. No extra text.\n"
            f"ai_message should be warm, empathetic, conversational — not robotic.\n"
            f"clarifying_questions should be exactly 2-3 questions that would "
            f"make the legal notice stronger or more accurate.\n"
            f"action_buttons should match the clarifying questions as quick replies.\n"
            f"next_steps action_label should be 'How? ↗' if the step needs explanation, "
            f"'Draft ↗' if it involves creating a new document, or empty string if simple.\n"
            f"\n"
            f"Put your JSON answer after a line that says exactly 'FINAL_JSON:' and nothing else.\n"
            f'{{{{'
            f'"ai_message": "conversational message explaining what was found and what info would help", '
            f'"summary": "2-3 sentence summary", '
            f'"legal_notice_draft": "full notice text", '
            f'"next_steps": ['
            f'{{"number": 1, "text": "what to do", "action_label": "How? ↗", "action_message": "How do I send this notice?"}}'
            f'], '
            f'"clarifying_questions": ['
            f'{{"question": "Do you have photos?", "key": "has_photos"}}'
            f'], '
            f'"action_buttons": ['
            f'{{"label": "Yes, I have these", "message": "I have photos", "style": "primary"}}'
            f']'
            f'}}}}'
        )

        response = await self.client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": self.legal.system_prompt()},
                {"role": "user", "content": final_prompt},
            ],
            max_tokens=16000,
        )
        final_text = response.choices[0].message.content.strip()

        marker = "FINAL_JSON:"
        idx = final_text.rfind(marker)
        if idx >= 0:
            final_data = _extract_json(final_text[idx + len(marker):])
        else:
            final_data = _extract_json(final_text)

        return AnalyzeResponseDTO(
            case_type=classification.get("case_type", "other"),
            severity=classification.get("severity", "medium"),
            relevant_sections=law_sections,
            legal_notice_draft=final_data.get("legal_notice_draft", ""),
            summary=final_data.get("summary", ""),
            next_steps=[NextStep(**ns) for ns in final_data.get("next_steps", [])],
            reasoning_trace="\n".join(reasoning_trace),
            clarifying_questions=[ClarifyingQuestion(**cq) for cq in final_data.get("clarifying_questions", [])],
            action_buttons=[ActionButton(**ab) for ab in final_data.get("action_buttons", [])],
            ai_message=final_data.get("ai_message", ""),
        )

    async def chat(self, request: ChatRequestDTO) -> ChatResponseDTO:
        system_content = self.legal.system_prompt()

        if request.current_notice_draft:
            system_content += (
                f"\n\nCurrent legal notice draft:\n{request.current_notice_draft}\n\n"
                f"If the user asks to edit the notice, return the updated full notice text in 'updated_notice'. "
                f"If they are answering clarifying questions, incorporate the new info into the notice and return it in 'updated_notice'. "
                f"Otherwise 'updated_notice' should be empty."
            )

        system_content += (
            "\n\nRespond with JSON containing these keys:\n"
            '{"reply": "your conversational reply", '
            '"updated_notice": "full updated notice text or empty string", '
            '"updated_sections": [], '
            '"clarifying_questions": [{"question": "...", "key": "..."}], '
            '"action_buttons": [{"label": "...", "message": "...", "style": "default"}]}'
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

        return ChatResponseDTO(
            reply=data.get("reply", reply_text),
            updated_notice=data.get("updated_notice", ""),
            updated_sections=data.get("updated_sections", []),
            clarifying_questions=[ClarifyingQuestion(**cq) for cq in data.get("clarifying_questions", [])],
            suggested_actions=[ActionButton(**ab) for ab in data.get("action_buttons", [])],
        )
