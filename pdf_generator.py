from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
import os
import base64
import re
import tempfile
import shutil
import copy
import logging
import gc

logger = logging.getLogger(__name__)

# 🔥 FONT FIX (CRITICAL FOR RENDER)
os.environ.setdefault("FONTCONFIG_PATH", "/etc/fonts")
os.environ.setdefault("FONTCONFIG_FILE", "")
os.environ.setdefault("FONTCONFIG_PATH", "")

# 🔥 DOCKER SAFE PATH
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")


def process_images(obj, tmp_dir, counter):
    if isinstance(obj, str) and obj.startswith('data:image'):
        try:
            match = re.match(r'data:([^;]+);base64,(.+)', obj, re.DOTALL)
            if match:
                mime = match.group(1)
                ext = mime.split('/')[-1].replace('jpeg', 'jpg').replace('svg+xml', 'svg')
                counter[0] += 1
                fpath = os.path.join(tmp_dir, f"img_{counter[0]}.{ext}")

                with open(fpath, 'wb') as f:
                    f.write(base64.b64decode(match.group(2)))

                return 'file:///' + fpath.replace('\\', '/')
        except Exception as e:
            logger.warning(f"Image processing failed: {e}")
            return obj

    if isinstance(obj, list):
        return [process_images(i, tmp_dir, counter) for i in obj]

    if isinstance(obj, dict):
        return {k: process_images(v, tmp_dir, counter) for k, v in obj.items()}

    return obj


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


def inject_orientation(html: str, orientation: str) -> str:
    if orientation == 'landscape':
        override = """
<style>
  @page { size: 297mm 210mm !important; margin: 0 !important; }
</style>"""
    else:
        override = """
<style>
  @page { size: 210mm 297mm !important; margin: 0 !important; }
</style>"""
    return html.replace('</head>', override + '\n</head>', 1)


def generate_pdf(portfolio_data: dict, template_id: int, orientation: str = 'portrait') -> bytes:
    if not (1 <= template_id <= 5):
        raise ValueError(f"Invalid template_id: {template_id}. Must be 1-5.")

    if not os.path.exists(TEMPLATE_DIR):
        raise FileNotFoundError(f"Template directory not found: {TEMPLATE_DIR}")

    template_file = f"template_{template_id}.html"
    template_path = os.path.join(TEMPLATE_DIR, template_file)

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template not found: {template_path}")

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template(template_file)

    merged_data = merge_images_into_ai_projects(portfolio_data)

    context = copy.deepcopy(merged_data)
    ai = merged_data.get("ai_content", {})

    # 🔥 SAFE FIELD EXTRACTION
    for key in ["summary", "tagline", "enhanced_bio", "skills_highlight"]:
        context[key] = ai.get(key, context.get(key, ""))

    tmp_dir = None
    try:
        tmp_dir = tempfile.mkdtemp(prefix="pfimgs_")
        counter = [0]

        context = process_images(context, tmp_dir, counter)

        # 🔥 SAFE CONTEXT (NO JINJA CRASH)
        safe_context = {
            "full_name": context.get("full_name", ""),
            "professional_title": context.get("professional_title", ""),
            "bio": context.get("bio", ""),
            "technical_skills": context.get("technical_skills", []),
            "projects": context.get("projects", []),
            "summary": context.get("summary", ""),
            "tagline": context.get("tagline", ""),
            "enhanced_bio": context.get("enhanced_bio", ""),
            "skills_highlight": context.get("skills_highlight", []),
            **context
        }

        html_content = template.render(**safe_context)
        html_content = inject_orientation(html_content, orientation)

        # 🔥 STABILITY FIX
        gc.collect()

        pdf_bytes = HTML(
            string=html_content,
            base_url='file:///' + TEMPLATE_DIR.replace('\\', '/') + '/'
        ).write_pdf()

        return pdf_bytes

    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)

        # 🔥 FAILSAFE PDF (NO CRASH)
        fallback_html = f"""
        <h1>PDF Generation Error</h1>
        <p>Something went wrong while generating your portfolio.</p>
        <pre>{str(e)}</pre>
        """

        return HTML(string=fallback_html).write_pdf()

    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
