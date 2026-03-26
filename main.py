from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import os
import json
import logging
import traceback
import sys

from groq import Groq
from pdf_generator import generate_pdf

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
    logger.warning("⚠️ GROQ_API_KEY not set (set in Render dashboard)")

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

    # OPTIONAL (keeps frontend safe)
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
        extra = "allow"  # VERY IMPORTANT


class PDFRequest(BaseModel):
    portfolio_data: dict
    template_id: int
    orientation: Optional[str] = "portrait"


# ---------------- HELPERS ----------------
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

        prompt = f"""
Return ONLY valid JSON:

{{
  "summary": "3-4 sentence summary",
  "tagline": "short tagline",
  "projects": [
    {{"name":"", "enhanced_description":""}}
  ],
  "work_experience": [
    {{"job_title":"", "company":"", "enhanced_description":""}}
  ]
}}

Name: {data.full_name}
Title: {data.professional_title}
Bio: {data.bio}
Skills: {', '.join(data.technical_skills)}
Projects: {json.dumps([p.dict() for p in data.projects])}
"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )

        raw = response.choices[0].message.content
        ai_content = safe_json_parse(raw)

        result = data.dict()
        result["ai_content"] = ai_content

        return {"success": True, "portfolio": result}

    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/download-pdf")
async def download_pdf(req: PDFRequest):
    try:
        pdf_bytes = generate_pdf(
            req.portfolio_data,
            req.template_id,
            req.orientation
        )

        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=portfolio.pdf"},
        )

    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- FRONTEND (OPTIONAL) ----------------
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
