class LegalHelper:
    def system_prompt(self) -> str:
        return """You are LexAgent, an expert Indian legal assistant.

Your role is to help ordinary Indians understand their legal rights and take action.

Rules:
- Always cite specific sections from Indian law.
- Use clear, simple language.
- Recommend consulting a qualified lawyer for court proceedings.
- Base section citations only on retrieved law search results."""

    def notice_template(self, case_type: str) -> str:
        templates = {
            "civil": "UNDER THE PROVISIONS OF THE BHARATIYA NYAYA SANHITA 2023",
            "consumer": "UNDER THE CONSUMER PROTECTION ACT 2019",
            "rti": "UNDER THE RIGHT TO INFORMATION ACT 2005",
            "labour": "UNDER THE LABOUR LAWS OF INDIA",
        }
        return templates.get(case_type, "UNDER THE APPLICABLE LAWS OF INDIA")

    def get_response_deadline(self, severity: str) -> int:
        deadlines = {"urgent": 7, "high": 15, "medium": 30, "low": 60}
        return deadlines.get(severity, 30)
