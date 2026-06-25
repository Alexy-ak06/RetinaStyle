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


def audit_accessibility(code: str) -> list[str]:
    issues = []
    low = code.lower()
    if "<html" in low and "lang=" not in low:
        issues.append("html element is missing a lang attribute")
    if "<img" in low and "alt=" not in low:
        issues.append("an img is missing an alt attribute")
    if ("<input" in low or "<select" in low or "<textarea" in low) and "<label" not in low:
        issues.append("form fields present but no label elements found")
    if re.search(r"<button[^>]*>\s*</button>", low):
        issues.append("a button has no accessible text")
    return issues


class SketchRequest(BaseModel):
    image: str
    style: str = "modern, clean, light"


@app.post("/generate")
async def generate(req: SketchRequest):
    raw = req.image.split(",", 1)[-1]
    try:
        image_bytes = base64.b64decode(raw)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Bad image data"})

    try:
        result = await run_agent_pipeline(image_bytes, style=req.style)
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Agent error: {e}"})

    clean_code, findings = sanitize_ui_code(result.get("code", ""))
    a11y = audit_accessibility(clean_code)

    return {
        "code": clean_code,
        "spec": result.get("spec", ""),
        "security_findings": findings,
        "accessibility_issues": a11y,
        "stages": ["Vision", "CodeGen", "Refiner", "Security (MCP)"],
    }


@app.get("/", response_class=HTMLResponse)
def home():
    with open("index.html", "r", encoding="utf-8") as f:
        return f.read()


app.mount("/static", StaticFiles(directory="."), name="static")