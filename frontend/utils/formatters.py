from datetime import datetime, timedelta, timezone

from dateutil import parser as date_parser


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def format_date(value: str | None) -> str:
    dt = parse_datetime(value)
    if not dt:
        return ""
    return dt.strftime("%b %d, %Y")


def format_time(value: str | None) -> str:
    dt = parse_datetime(value)
    if not dt:
        return ""
    return dt.strftime("%I:%M %p")


def group_cases_by_date(cases: list[dict]) -> dict[str, list[dict]]:
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    groups: dict[str, list[dict]] = {
        "Today": [],
        "Yesterday": [],
        "This Week": [],
        "Older": [],
    }

    for case in cases:
        dt = parse_datetime(case.get("created_at"))
        if not dt:
            groups["Older"].append(case)
            continue
        if dt >= today_start:
            groups["Today"].append(case)
        elif dt >= yesterday_start:
            groups["Yesterday"].append(case)
        elif dt >= week_start:
            groups["This Week"].append(case)
        else:
            groups["Older"].append(case)

    return {k: v for k, v in groups.items() if v}


def case_title(case: dict) -> str:
    description = case.get("description") or case.get("summary") or ""
    if description:
        return description[:60] + ("..." if len(description) > 60 else "")
    case_type = case.get("case_type") or "Legal Matter"
    return case_type.replace("_", " ").title()
