import html
import re
from pathlib import Path

OG_BLOCK = re.compile(r"<!-- OMA:OG:START -->.*?<!-- OMA:OG:END -->", re.DOTALL)
TITLE_TAG = re.compile(r"<title>.*?</title>", re.DOTALL)


def _attribute(value: str) -> str:
    return html.escape(value, quote=True)


def render_social_metadata(
    template: str,
    *,
    title: str,
    description: str,
    canonical_url: str,
    image_url: str,
) -> str:
    """Inject escaped page metadata into the shared SPA shell."""
    safe_title = _attribute(title)
    safe_description = _attribute(description)
    safe_url = _attribute(canonical_url)
    safe_image = _attribute(image_url)
    tags = "\n".join(
        (
            "<!-- OMA:OG:START -->",
            f'<meta property="og:title" content="{safe_title}" />',
            f'<meta property="og:description" content="{safe_description}" />',
            '<meta property="og:type" content="website" />',
            f'<meta property="og:url" content="{safe_url}" />',
            f'<meta property="og:image" content="{safe_image}" />',
            '<meta property="og:site_name" content="OMA Studio" />',
            '<meta name="twitter:card" content="summary" />',
            f'<meta name="twitter:title" content="{safe_title}" />',
            f'<meta name="twitter:description" content="{safe_description}" />',
            f'<meta name="twitter:image" content="{safe_image}" />',
            "<!-- OMA:OG:END -->",
        )
    )
    rendered = TITLE_TAG.sub(f"<title>{safe_title}</title>", template, count=1)
    return OG_BLOCK.sub(tags, rendered, count=1)


def load_template(static_dir: Path) -> str:
    return (static_dir / "index.html").read_text(encoding="utf-8")
