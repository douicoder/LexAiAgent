import re


def nl2br(text: str | None) -> str:
    if not text:
        return ""
    escaped = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return escaped.replace("\n", "<br>")


def highlight_changes(old_text: str, new_text: str) -> str:
    if not old_text or old_text == new_text:
        return nl2br(new_text)

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    result = []

    for i, line in enumerate(new_lines):
        if i < len(old_lines) and line != old_lines[i]:
            escaped = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            result.append(f'<span class="notice-highlight">{escaped}</span>')
        else:
            escaped = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            result.append(escaped)

    return "<br>".join(result)


def score_percent(score: float) -> int:
    return min(100, max(0, int(score * 100)))


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_-]+", "-", text)
