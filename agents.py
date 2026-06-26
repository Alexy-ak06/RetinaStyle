"""
RetinaStyle AI  --  multi-agent pipeline (Google ADK + MCP)
===========================================================
Vision -> CodeGen -> Refiner -> SecurityAuditor  (an ADK SequentialAgent)

  1. Vision Agent          : infers the intended UI from the sketch (ui_spec).
  2. CodeGen Agent         : {ui_spec} + chosen {style} -> polished page (ui_code).
  3. Refiner Agent         : cleans the HTML (refined_code).
  4. SecurityAuditor Agent : calls the MCP server's validate_ui_code and
                             audit_accessibility tools (final_code).

run_agent_pipeline returns a dict: {"spec", "code"} so the UI can show the
intermediate reasoning, not just the final result. It retries automatically on
transient (rate-limit / server-busy) errors.

Standalone test:  python agents.py
"""

import os
import re
import sys
import uuid
import random
import asyncio

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.genai import types

load_dotenv()

if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
APP_NAME = "retinastyle"

_MCP_SERVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcp_server.py")

_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[_MCP_SERVER],
        ),
        timeout=60,
    ),
)

vision_agent = LlmAgent(
    name="VisionAgent",
    model=MODEL,
    instruction=(
        "You are a senior product designer reading a hand-drawn UI wireframe.\n"
        "Infer the INTENT, not just the shapes. A box near the top is usually a "
        "header, hero, logo or card; horizontal lines are usually input fields or "
        "rows of text; a small box is usually a button.\n"
        "Decide the most likely purpose of the screen (login, sign-up, search, "
        "dashboard, profile, settings, checkout, etc.) and describe a COMPLETE, "
        "realistic interface for it. List every component top-to-bottom with "
        "concrete labels and placeholder text, and note layout and spacing.\n"
        "Output the spec only -- no preamble."
    ),
    output_key="ui_spec",
)

codegen_agent = LlmAgent(
    name="CodeGenAgent",
    model=MODEL,
    instruction=(
        "You are a senior front-end engineer. Build a SINGLE, complete, "
        "polished, production-quality HTML document for this UI spec:\n\n"
        "{ui_spec}\n\n"
        "Visual style to apply (honour this strongly): {style}\n\n"
        "Make it look like a REAL modern product screen, not a skeleton:\n"
        "- Include Tailwind via <script src=\"https://cdn.tailwindcss.com\"></script> in <head>.\n"
        "- The <body> must fill the viewport (min-h-screen), use a tasteful "
        "background that matches the style, and centre the main content.\n"
        "- Use realistic placeholder text, field labels, and a clearly styled "
        "primary button. Add simple icons with unicode/emoji if helpful.\n"
        "- Good spacing, rounded corners, soft shadows, readable typography.\n"
        "- Any interactivity uses plain inline JavaScript only.\n"
        "- Do NOT use eval, new Function, fetch, XMLHttpRequest, localStorage, "
        "sessionStorage, document.cookie, or window.parent/top.\n"
        "- Output ONLY raw HTML. No explanations, no Markdown fences."
    ),
    output_key="ui_code",
)

refiner_agent = LlmAgent(
    name="RefinerAgent",
    model=MODEL,
    instruction=(
        "You are a senior reviewer. Here is generated HTML:\n\n{ui_code}\n\n"
        "Return a corrected version that keeps the full visual design and the "
        "Tailwind CDN script, fixes any obviously broken markup, and removes any "
        "eval, new Function, fetch, XMLHttpRequest, localStorage, sessionStorage, "
        "document.cookie, or window.parent/top usage. Keep it a single valid HTML "
        "document.\n"
        "Output ONLY the raw HTML. No explanations, no Markdown fences."
    ),
    output_key="refined_code",
)

security_agent = LlmAgent(
    name="SecurityAuditorAgent",
    model=MODEL,
    instruction=(
        "You are a security auditor. You have two MCP tools: validate_ui_code "
        "and audit_accessibility.\n\n"
        "Step 1: call validate_ui_code with this HTML as the 'code' argument:\n\n"
        "{refined_code}\n\n"
        "Step 2: call audit_accessibility with the same HTML.\n"
        "Step 3: take the 'cleaned_code' field returned by validate_ui_code and "
        "output it EXACTLY as raw HTML -- nothing else. No commentary, no Markdown "
        "fences."
    ),
    tools=[_mcp_toolset],
    output_key="final_code",
)

pipeline = SequentialAgent(
    name="RetinaStylePipeline",
    sub_agents=[vision_agent, codegen_agent, refiner_agent, security_agent],
)

_session_service = InMemorySessionService()
_runner = Runner(agent=pipeline, app_name=APP_NAME, session_service=_session_service)


# Substrings that mark a transient, retryable error (rate limits / busy servers).
_TRANSIENT_MARKERS = (
    "429", "resource_exhausted", "rate limit", "quota",
    "503", "unavailable", "high demand",
    "500", "internal", "deadline", "timeout", "502",
)


def _is_transient(err: Exception) -> bool:
    """True if the error looks like a temporary rate-limit / availability blip."""
    s = str(err).lower()
    return any(m in s for m in _TRANSIENT_MARKERS)


def _suggested_delay(err: Exception, fallback: float) -> float:
    """Honor the server's retry hint if present (e.g. 'retry in 37.5s'), capped."""
    s = str(err)
    m = (re.search(r"retry in ([\d.]+)\s*s", s, re.IGNORECASE)
         or re.search(r"retrydelay['\"]?\s*[:=]?\s*['\"]?(\d+)\s*s", s, re.IGNORECASE))
    if m:
        try:
            return min(float(m.group(1)) + 1.0, 65.0)
        except ValueError:
            pass
    return fallback


async def run_agent_pipeline(
    image_bytes: bytes,
    style: str = "modern, clean, light",
    max_attempts: int = 5,
) -> dict:
    """Run the pipeline with retry/backoff on transient (429/503/5xx) errors.

    Permanent errors (bad input, auth, etc.) are raised immediately.
    """
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await _run_pipeline_once(image_bytes, style)
        except Exception as e:  # noqa: BLE001 - we re-raise non-transient below
            last_err = e
            if attempt == max_attempts or not _is_transient(e):
                raise
            # exponential backoff (capped), plus jitter to avoid lockstep retries
            backoff = min(2.0 * (2 ** (attempt - 1)), 30.0)
            delay = _suggested_delay(e, fallback=backoff)
            delay += random.uniform(0, 0.6 * delay)
            print(
                f"[retry] transient error on attempt {attempt}/{max_attempts}; "
                f"waiting {delay:.1f}s then retrying. ({str(e)[:120]})"
            )
            await asyncio.sleep(delay)
    assert last_err is not None
    raise last_err


async def _run_pipeline_once(image_bytes: bytes, style: str = "modern, clean, light") -> dict:
    """One pass of the pipeline. Returns {"spec": <ui_spec>, "code": <final html>}."""
    user_id = "user"
    session_id = uuid.uuid4().hex

    await _session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
        state={"style": style},
    )

    message = types.Content(
        role="user",
        parts=[
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            types.Part(text="Here is the wireframe sketch. Turn it into a UI."),
        ],
    )

    async for _ in _runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        pass

    session = await _session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    state = session.state
    return {
        "spec": state.get("ui_spec", ""),
        "code": state.get("final_code") or state.get("refined_code", ""),
    }


if __name__ == "__main__":
    async def _test():
        import base64
        print("Running 4-agent pipeline (with MCP + retry) on a test...\n")
        # 1x1 transparent PNG just to exercise the wiring
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        result = await run_agent_pipeline(png, style="modern dark, glassmorphism")
        print("--- SPEC (first 200 chars) ---")
        print(result["spec"][:200])
        print("\n--- CODE length:", len(result["code"]), "chars ---")
        print("OK" if "<" in result["code"] else "EMPTY")

    asyncio.run(_test())