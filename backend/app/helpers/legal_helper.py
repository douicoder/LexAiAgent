class LegalHelper:
    def system_prompt(self) -> str:
        return """You are LexAgent, an AI legal assistant specializing in Indian property and tenancy law.

Your current knowledge base covers:
- Model Tenancy Act 2021 (rent disputes, eviction, security deposits)
- Transfer of Property Act 1882 (property sales, mortgages, leases)
- Registration Act 1908 (property registration, deeds)

Rules:
- ONLY cite sections returned by the search_law tool. Never make up section numbers.
- Use plain simple English. Users are not lawyers.
- Be empathetic. Users are stressed.
- In legal notices always give a 15-30 day response deadline.
- If the case is outside your knowledge base (criminal, consumer, RTI),
  say so clearly and tell the user to consult a lawyer.

When generating the final JSON output always use these exact keys:
summary, next_steps, legal_notice_draft"""

    def notice_template(self, case_type: str) -> str:
        templates = {
            "tenancy_dispute": "UNDER THE PROVISIONS OF THE MODEL TENANCY ACT 2021",
            "property_ownership": "UNDER THE PROVISIONS OF THE TRANSFER OF PROPERTY ACT 1882",
            "property_registration": "UNDER THE PROVISIONS OF THE REGISTRATION ACT 1908",
            "other": "UNDER THE APPLICABLE LAWS OF INDIA",
        }
        return templates.get(case_type, "UNDER THE APPLICABLE LAWS OF INDIA")

    def get_response_deadline(self, severity: str) -> int:
        deadlines = {"urgent": 7, "high": 15, "medium": 30, "low": 60}
        return deadlines.get(severity, 30)
