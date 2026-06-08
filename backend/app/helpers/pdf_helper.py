import datetime


class PdfHelper:
    def format_date_legal(self, dt=None) -> str:
        if dt is None:
            dt = datetime.date.today()
        return dt.strftime("%d %B %Y")
