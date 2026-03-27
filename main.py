import os
import json
import logging
import traceback
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

from groq import Groq
from pdf_generator import generate_pdf, shutdown_browser


# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ---------------- APP ----------------
app = FastAPI(title="Portfolio Generator API", version="1.0.0")


# ---------------- CORS ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- GROQ ----------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    logger.warning("⚠️ GROQ_API_KEY not set")

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


# ---------------- MODELS ----------------
class WorkExperience(BaseModel):
    job_title: str
    company: str
    location: Optional[str] = ""
    start_date: str
    end_date: str
    description: str


class Project(BaseModel):
    name: str
    description: str
    tech_stack: List[str]
    live_url: Optional[str] = ""
    github_url: Optional[str] = ""
    images: Optional[List[str]] = []
    problem_statement: Optional[str] = ""
    dataset: Optional[str] = ""
    features: Optional[str] = ""
    model_approach: Optional[str] = ""
    accuracy: Optional[str] = ""
    results: Optional[str] = ""
    additional_notes: Optional[str] = ""


class Education(BaseModel):
    degree: str
    institution: str
    start_year: str
    end_year: str
    grade: Optional[str] = ""


class Achievement(BaseModel):
    title: str
    organization: str
    date: str
    credential_url: Optional[str] = ""
    image: Optional[str] = ""
    description: Optional[str] = ""


class PortfolioRequest(BaseModel):
    full_name: str
    professional_title: str
    email: str
    bio: str

    technical_skills: List[str]
    projects: List[Project]

    photo: Optional[str] = ""
    location: Optional[str] = ""
    github: Optional[str] = ""
    linkedin: Optional[str] = ""
    website: Optional[str] = ""
    twitter: Optional[str] = ""
    soft_skills: Optional[List[str]] = []
    spoken_languages: Optional[List[str]] = []
    work_experience: Optional[List[WorkExperience]] = []
    education: Optional[List[Education]] = []
    achievements: Optional[List[Achievement]] = []
    availability: Optional[str] = ""
    open_to_work: Optional[bool] = False

    class Config:
        extra = "allow"


class PDFRequest(BaseModel):
    portfolio_data: dict
    template_id: int
    orientation: Optional[str] = "portrait"


# ---------------- HELPERS ----------------
def trim_text(text: str, max_len: int = 200):
    if not text:
        return ""
    return text if len(text) <= max_len else text[:max_len] + "..."


def safe_json_parse(raw: str):
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        return json.loads(raw[start:end])
    except:
        return {}


# ---------------- ROUTES ----------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/generate")
async def generate_portfolio(data: PortfolioRequest):
    try:
        logger.info(f"Generating portfolio for: {data.full_name}")

        if not client:
            raise HTTPException(status_code=500, detail="Groq API not configured")

        limited_projects = [
            {
                "name": p.name,
                "description": trim_text(p.description, 200),
                "tech_stack": p.tech_stack[:5]
            }
            for p in data.projects[:3]
        ]

        limited_skills = data.technical_skills[:10]
        limited_bio = trim_text(data.bio, 300)

        prompt = f"""
Return ONLY valid JSON:

{{
  "summary": "3-4 sentence summary",
  "tagline": "short tagline",
  "projects": [
    {{"name":"", "enhanced_description":""}}
  ]
}}

Name: {data.full_name}
Title: {data.professional_title}
Bio: {limited_bio}
Skills: {', '.join(limited_skills)}
Projects: {json.dumps(limited_projects)}
"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800
        )

        raw = response.choices[0].message.content
        ai_content = safe_json_parse(raw)

        result = data.dict()
        result["ai_content"] = ai_content

        return {"success": True, "portfolio": result}

    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- PDF ENDPOINT ----------------
@app.post("/api/download-pdf")
async def download_pdf(req: PDFRequest):
    try:
        pdf_bytes = await generate_pdf(
            req.portfolio_data,
            req.template_id,
            req.orientation
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename=portfolio.pdf"
            },
        )

    except Exception as e:
        logger.error("PDF GENERATION FAILED")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- CLEAN SHUTDOWN ----------------
@app.on_event("shutdown")
async def shutdown_event():
    await shutdown_browser()


# ---------------- FRONTEND ----------------
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/")
    async def serve_root():
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.exists(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
else:
    @app.get("/")
    async def root():
        return JSONResponse({"message": "API running"})


# ---------------- START ----------------
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
