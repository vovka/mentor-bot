"""send_image use case: render a Mermaid diagram the brain proposed and post it as a photo."""


def run(renderer, chat, args: dict) -> str:
    diagram = (args.get("diagram") or "").strip()
    if not diagram:
        return "(no diagram source given, nothing sent)"
    try:
        png = renderer.render(diagram)
    except RuntimeError as exc:
        return f"(could not render the image: {exc})"
    chat.send_photo(png, args.get("caption") or "")
    return "(image sent)"
