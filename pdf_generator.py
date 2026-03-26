from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
import os
import copy
import logging
import asyncio

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# ---------------- GLOBALS ----------------
playwright = None
browser = None

# Limit concurrency (VERY IMPORTANT)
semaphore = asyncio.Semaphore(2)


# ---------------- INIT BROWSER ----------------
def init_browser():
    global playwright, browser

    if browser is None:
        logger.info("🚀 Launching shared Chromium instance...")

        playwright = sync_playwright().start()

        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox",
                "--single-process",
                "--no-zygote",
                "--disable-extensions",
                "--disable-background-networking"
            ]
        )


# ---------------- PDF GENERATION (SYNC CORE) ----------------
def generate_pdf_sync(html_content: str, orientation: str) -> bytes:
    global browser

    # 🔁 Retry mechanism (CRITICAL FIX)
    for attempt in range(2):
        try:
            init_browser()

            page = browser.new_page(
                viewport={"width": 1024, "height": 1440}
            )

            try:
                page.set_content(html_content, wait_until="load")
                page.emulate_media(media="print")

                pdf_bytes = page.pdf(
                    print_background=True,
                    prefer_css_page_size=True,
                    landscape=(orientation == "landscape"),
                    margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"}
                )

                if not pdf_bytes or len(pdf_bytes) < 1000:
                    raise Exception("Invalid PDF generated")

                return pdf_bytes

            finally:
                page.close()  # 🔥 prevents memory leak

        except Exception as e:
            logger.warning(f"⚠️ Browser issue, retrying... Attempt {attempt + 1}")

            # 🔥 Force reset browser (SELF-HEAL)
            try:
                if browser:
                    browser.close()
            except:
                pass

            browser = None

            if attempt == 1:
                logger.error("❌ Browser failed after retry", exc_info=True)
                raise e


# ---------------- ASYNC WRAPPER ----------------
async def generate_pdf(portfolio_data: dict, template_id: int, orientation: str = "portrait") -> bytes:
    async with semaphore:  # 🔥 prevents overload crashes
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

            return pdf_bytes

        except Exception as e:
            logger.error(f"PDF generation failed: {e}", exc_info=True)
            raise


# ---------------- CLEANUP ----------------
def shutdown_browser():
    global browser, playwright

    logger.info("🛑 Closing browser...")

    try:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")
