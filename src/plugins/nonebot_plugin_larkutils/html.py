

def escape_html(html: str) -> str:
    return html.replace("<", "&lt;").replace(">", "&gt;")