from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
import os
import copy
import logging
import asyncio

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")


def generate_pdf_sync(html_content: str, orientation: str) -> bytes:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--single-process",
                "--no-zygote"
            ]
        )

        page = browser.new_page(viewport={"width": 1440, "height": 2560})

        page.set_content(html_content, wait_until="load")
        page.emulate_media(media="print")

        pdf_bytes = page.pdf(
            print_background=True,
            prefer_css_page_size=True,
            landscape=(orientation == "landscape"),
            margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"}
        )

        browser.close()
        return pdf_bytes


async def generate_pdf(portfolio_data: dict, template_id: int, orientation: str = "portrait") -> bytes:
    try:
        env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
        template = env.get_template(f"template_{template_id}.html")

        context = copy.deepcopy(portfolio_data)
        ai = context.get("ai_content", {})

        context["summary"] = ai.get("summary", "")
        context["tagline"] = ai.get("tagline", "")
        context["projects"] = ai.get("projects", context.get("projects", []))

        html_content = template.render(**context)

        pdf_bytes = await asyncio.to_thread(
            generate_pdf_sync,
            html_content,
            orientation
        )

        if not pdf_bytes or len(pdf_bytes) < 1000:
            raise Exception("Generated PDF is invalid")

        return pdf_bytes

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise
