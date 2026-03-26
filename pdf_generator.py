from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright
import os
import copy
import logging

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")


def inject_orientation(html: str, orientation: str) -> str:
    if orientation == "landscape":
        override = """
<style>
  @page { size: 297mm 210mm !important; margin: 0 !important; }
  @page cover-p { size: 297mm 210mm !important; margin: 0 !important; }
  @page inner-p { size: 297mm 210mm !important; margin: 0 !important; }
</style>"""
    else:
        override = """
<style>
  @page { size: 210mm 297mm !important; margin: 0 !important; }
  @page cover-p { size: 210mm 297mm !important; margin: 0 !important; }
  @page inner-p { size: 210mm 297mm !important; margin: 0 !important; }
</style>"""
    return html.replace("</head>", override + "\n</head>", 1)


def merge_images_into_ai_projects(portfolio_data: dict) -> dict:
    data = copy.deepcopy(portfolio_data)
    ai = data.get("ai_content", {})
    orig_projects = data.get("projects", [])
    ai_projects = ai.get("projects", [])

    for i, ai_proj in enumerate(ai_projects):
        if i < len(orig_projects):
            orig = orig_projects[i]
            ai_proj["images"] = orig.get("images", [])
            ai_proj["problem_statement"] = orig.get("problem_statement", "")
            ai_proj["dataset"] = orig.get("dataset", "")
            ai_proj["features"] = orig.get("features", "")
            ai_proj["model_approach"] = orig.get("model_approach", "")
            ai_proj["accuracy"] = orig.get("accuracy", "")
            ai_proj["results"] = orig.get("results", "")
            ai_proj["additional_notes"] = orig.get("additional_notes", "")
            ai_proj["live_url"] = orig.get("live_url", "")
            ai_proj["github_url"] = orig.get("github_url", "")

    return data


def generate_pdf(portfolio_data: dict, template_id: int, orientation: str = "portrait") -> bytes:
    if not (1 <= template_id <= 5):
        raise ValueError(f"Invalid template_id: {template_id}. Must be 1-5.")

    template_dir = TEMPLATE_DIR
    if not os.path.exists(template_dir):
        raise FileNotFoundError(f"Template directory not found: {template_dir}")

    template_file = f"template_{template_id}.html"
    template_path = os.path.join(template_dir, template_file)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")

    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(template_file)

    merged_data = merge_images_into_ai_projects(portfolio_data)

    context = copy.deepcopy(merged_data)
    ai = merged_data.get("ai_content", {})

    context["summary"] = ai.get("summary", "")
    context["tagline"] = ai.get("tagline", "")
    context["projects"] = ai.get("projects", context.get("projects", []))

    html_content = template.render(**context)
    html_content = inject_orientation(html_content, orientation)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            page = browser.new_page(
                viewport={"width": 1440, "height": 2560},
                device_scale_factor=1
            )

            page.set_content(html_content, wait_until="load")
            page.emulate_media(media="print")

            pdf_bytes = page.pdf(
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0in", "right": "0in", "bottom": "0in", "left": "0in"}
            )

            browser.close()

        if not pdf_bytes or len(pdf_bytes) < 1000:
            raise RuntimeError("Generated PDF is empty or invalid.")

        return pdf_bytes

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise
