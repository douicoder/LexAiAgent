class LegalHelper:
    def system_prompt(self) -> str:
        return """You are LexAgent, an expert Indian legal assistant.

Your role is to help ordinary Indians understand their legal rights and take action.

Rules:
- Always cite specific sections from Indian law.
- Use clear, simple language.
- Recommend consulting a qualified lawyer for court proceedings.
- Base section citations only on retrieved law search results.

IMPORTANT — Output format compliance:
- Follow the user's requested output format EXACTLY. Do not deviate.
- NEVER add disclaimers, warnings, or safety notices. The application handles these separately.
- Do NOT discuss instructions, guidelines, or your own reasoning in the output.
- Do NOT include markdown or any text outside the requested format.
- The user's format instruction is the ONLY instruction that matters for output."""

    def notice_template(self, case_type: str) -> str:
        templates = {
            "tenancy_dispute": "UNDER THE PROVISIONS OF THE TRANSFER OF PROPERTY ACT 1882 AND THE RENT CONTROL LAWS",
            "property_ownership": "UNDER THE PROVISIONS OF THE TRANSFER OF PROPERTY ACT 1882 AND THE INDIAN CONTRACT ACT 1872",
            "property_registration": "UNDER THE PROVISIONS OF THE REGISTRATION ACT 1908",
            "other": "UNDER THE APPLICABLE LAWS OF INDIA",
        }
        return templates.get(case_type, "UNDER THE APPLICABLE LAWS OF INDIA")

    def get_response_deadline(self, severity: str) -> int:
        deadlines = {"urgent": 7, "high": 15, "medium": 30, "low": 60}
        return deadlines.get(severity, 30)
