import datetime
import io

from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)
from supabase import create_client

from app.config import settings
from app.dto.agent_dto import GeneratePdfDTO, PdfResponseDTO, PersonDetailsDTO
from app.interfaces.i_pdf_service import IPdfService


class PdfService(IPdfService):
    def __init__(self):
        self.supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        self.supabase_admin = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

    # ── Public: interface method ───────────────────────────────────────────
    async def generate_pdf(self, request: GeneratePdfDTO) -> PdfResponseDTO:
        pdf_bytes = await self.generate_legal_notice(
            notice_content=request.notice_content,
            user_details=request.user_details.model_dump(),
            recipient_details=request.recipient_details.model_dump(),
            sections=[],
            case_type="civil",
        )
        case_id = request.case_id
        url = await self.upload_to_storage(pdf_bytes, f"{case_id}.pdf")
        return PdfResponseDTO(
            pdf_url=url,
            pdf_id=case_id,
            generated_at=str(datetime.datetime.utcnow()),
        )

    # ── Public: new methods ────────────────────────────────────────────────
    async def generate_legal_notice(
        self,
        notice_content: str,
        user_details: dict,
        recipient_details: dict,
        sections: list | None = None,
        case_type: str = "civil",
    ) -> bytes:
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            topMargin=0.8 * inch,
            bottomMargin=0.8 * inch,
            leftMargin=0.9 * inch,
            rightMargin=0.9 * inch,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "Title",
            parent=styles["Title"],
            fontSize=18,
            leading=22,
            alignment=TA_CENTER,
            spaceAfter=6,
        )
        heading_style = ParagraphStyle(
            "Heading",
            parent=styles["Heading2"],
            fontSize=13,
            leading=16,
            spaceBefore=12,
            spaceAfter=6,
        )
        normal = ParagraphStyle(
            "NormalCustom",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=4,
        )
        justified = ParagraphStyle(
            "Justified",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=6,
        )
        small_grey = ParagraphStyle(
            "SmallGrey",
            parent=styles["Normal"],
            fontSize=8,
            leading=10,
            textColor="#666666",
            alignment=TA_CENTER,
        )
        address_style = ParagraphStyle(
            "Address",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            leftIndent=20,
            spaceAfter=2,
        )
        signature_style = ParagraphStyle(
            "Signature",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            spaceBefore=20,
        )

        elements = []

        # Title
        elements.append(Paragraph("LEGAL NOTICE", title_style))
        elements.append(HRFlowable(width="100%", thickness=2, color="black"))
        elements.append(Spacer(1, 10))

        # Date (right) and Case Type (left)
        today = datetime.date.today().strftime("%B %d, %Y")
        date_right = ParagraphStyle(
            "DateRight", parent=normal, alignment=TA_RIGHT
        )
        elements.append(Paragraph(f"Date: {today}", date_right))
        elements.append(Paragraph(f"Case Type: <b>{case_type.replace('_', ' ').title()}</b>", normal))
        elements.append(Spacer(1, 14))

        # TO block
        elements.append(Paragraph("<b>TO:</b>", normal))
        r_name = recipient_details.get("name", "Recipient")
        r_addr = recipient_details.get("address", "")
        elements.append(Paragraph(r_name, address_style))
        if r_addr:
            elements.append(Paragraph(r_addr, address_style))
        elements.append(Spacer(1, 12))

        # FROM block
        elements.append(Paragraph("<b>FROM:</b>", normal))
        u_name = user_details.get("name", "Sender")
        u_addr = user_details.get("address", "")
        u_phone = user_details.get("phone")
        elements.append(Paragraph(u_name, address_style))
        if u_addr:
            elements.append(Paragraph(u_addr, address_style))
        if u_phone:
            elements.append(Paragraph(f"Phone: {u_phone}", address_style))
        elements.append(Spacer(1, 14))

        # Horizontal rule
        elements.append(HRFlowable(width="100%", thickness=1, color="black"))
        elements.append(Spacer(1, 14))

        # Body
        elements.append(Paragraph(notice_content.replace("\n", "<br/>"), justified))
        elements.append(Spacer(1, 12))

        # Legal Provisions
        if sections:
            elements.append(Paragraph("<b>Legal Provisions:</b>", heading_style))
            for s in sections:
                act = s.get("act", "")
                section = s.get("section_number") or s.get("section", "")
                title = s.get("section_title") or s.get("title", "")
                line = f"• {act} — Section {section}: {title}"
                elements.append(Paragraph(line, normal))
            elements.append(Spacer(1, 12))

        # Horizontal rule
        elements.append(HRFlowable(width="100%", thickness=1, color="black"))
        elements.append(Spacer(1, 8))

        # Deadline
        elements.append(
            Paragraph(
                "<i>Respond within 15 days of receipt of this notice.</i>",
                normal,
            )
        )
        elements.append(Spacer(1, 20))

        # Signature
        elements.append(Paragraph("Yours faithfully,", signature_style))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph(f"<b>{u_name}</b>", signature_style))
        elements.append(Spacer(1, 30))

        # Footer
        elements.append(HRFlowable(width="100%", thickness=0.5, color="#CCCCCC"))
        elements.append(
            Paragraph(
                "Generated by LexAgent — AI legal aid for India",
                small_grey,
            )
        )

        doc.build(elements)
        return buf.getvalue()

    async def upload_to_storage(self, pdf_bytes: bytes, filename: str) -> str:
        path = f"notices/{filename}"
        self.supabase_admin.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            path,
            pdf_bytes,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )
        url = self.supabase_admin.storage.from_(
            settings.SUPABASE_STORAGE_BUCKET
        ).get_public_url(path)
        return url
