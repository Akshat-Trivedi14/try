from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
import os
import copy
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")


def generate_pdf(portfolio_data: dict, template_id: int, orientation: str = 'portrait') -> bytes:
    try:
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template(f"template_{template_id}.html")

        context = copy.deepcopy(portfolio_data)
        ai = context.get("ai_content", {})

        # safe fields
        context["summary"] = ai.get("summary", "")
        context["tagline"] = ai.get("tagline", "")
        context["projects"] = ai.get("projects", context.get("projects", []))

        html_content = template.render(**context)

        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page()

            page.set_content(html_content, wait_until="networkidle")

            pdf_bytes = page.pdf(
                format="A4",
                landscape=(orientation == "landscape"),
                print_background=True
            )

            browser.close()

        return pdf_bytes

    except Exception as e:
        logger.error(f"Playwright PDF failed: {e}", exc_info=True)

        # fallback (never crash)
        return b"PDF generation failed"
