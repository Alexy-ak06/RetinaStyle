import re
import base64

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from agents import run_agent_pipeline

load_dotenv()

app = FastAPI(title="RetinaStyle AI")

BLOCKED_PATTERNS = [
    r"\beval\s*\(",
    r"\bnew\s+Function\s*\(",
    r"document\.cookie",
    r"localStorage",
    r"sessionStorage",
    r"\bfetch\s*\(",
    r"XMLHttpRequest",
    r"[^.\w]import\s*\(",
    r"<script[^>]+src=(?![\"']https://cdn\.tailwindcss\.com)",
    r"window\.parent",
    r"window\.top",
]


def sanitize_ui_code(code: str) -> tuple[str, list[str]]:
    findings: list[str] = []
    code = re.sub(r"^```[a-zA-Z]*\n?", "", code.strip())
    code = re.sub(r"\n?```$", "", code.strip())
    for pattern in BLOCKED_PATTERNS:
        if re.findall(pattern, code, flags=re.IGNORECASE):
            findings.append(pattern)
            code = re.sub(pattern, "/*blocked*/", code, flags=re.IGNORECASE)
    return code, findings


class SketchRequest(BaseModel):
    image: str


@app.post("/generate")
async def generate(req: SketchRequest):
    raw = req.image.split(",", 1)[-1]
    try:
        image_bytes = base64.b64decode(raw)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Bad image data"})

    try:
        generated = await run_agent_pipeline(image_bytes)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Agent error: {e}"})

    clean_code, findings = sanitize_ui_code(generated)
    return {"code": clean_code, "security_findings": findings}


@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


app.mount("/static", StaticFiles(directory="."), name="static")