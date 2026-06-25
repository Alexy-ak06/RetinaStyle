"""
RetinaStyle AI  --  multi-agent pipeline (Google ADK)
=====================================================
Vision Agent  ->  CodeGen Agent  ->  Refiner Agent  (an ADK SequentialAgent)

  1. Vision Agent  : INFERS the intended interface from the sketch (not just
                     literal shapes) -> structured spec  (state["ui_spec"]).
  2. CodeGen Agent : turns {ui_spec} into a polished, filled-in Tailwind page
                     (state["ui_code"]).
  3. Refiner Agent : enforces security rules without stripping the design
                     (state["final_code"]).

The Python security validator in app.py runs afterwards as a hard gate.

Standalone test:  python agents.py
"""

import os
import uuid
import base64

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types

load_dotenv()

if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
APP_NAME = "retinastyle"

# ---------------------------------------------------------------------------
# AGENT 1 -- Vision: infer the INTENDED interface from the sketch
# ---------------------------------------------------------------------------
vision_agent = LlmAgent(
    name="VisionAgent",
    model=MODEL,
    instruction=(
        "You are a senior product designer reading a hand-drawn UI wireframe.\n"
        "Infer the INTENT, not just the shapes. Map rough marks to real "
        "components: a box near the top is usually a header, hero, logo or card; "
        "horizontal lines are usually input fields or rows of text; a small box "
        "is usually a button.\n"
        "Decide the most likely purpose of the screen (login, sign-up, search, "
        "dashboard, profile, settings, checkout, etc.) and describe a COMPLETE, "
        "realistic interface for it. List every component top-to-bottom with "
        "concrete labels and placeholder text (e.g. 'Email input, placeholder "
        "you@example.com'), and note layout (centered card, full width, spacing).\n"
        "Output the spec only -- no preamble."
    ),
    output_key="ui_spec",
)

# ---------------------------------------------------------------------------
# AGENT 2 -- CodeGen: spec -> polished, filled-in Tailwind page
# ---------------------------------------------------------------------------
codegen_agent = LlmAgent(
    name="CodeGenAgent",
    model=MODEL,
    instruction=(
        "You are a senior front-end engineer. Build a SINGLE, complete, "
        "polished, production-quality HTML document for this UI spec:\n\n"
        "{ui_spec}\n\n"
        "Make it look like a REAL modern product screen, not a skeleton:\n"
        "- Include Tailwind via <script src=\"https://cdn.tailwindcss.com\"></script> in <head>.\n"
        "- The <body> must fill the viewport (use min-h-screen), use a tasteful "
        "background, and center the main content.\n"
        "- Use realistic placeholder text, field labels, and a clearly styled "
        "primary button. Add simple icons with unicode/emoji if helpful.\n"
        "- Good spacing, rounded corners, soft shadows, readable typography, and "
        "a cohesive colour scheme.\n"
        "- Any interactivity uses plain inline JavaScript only.\n"
        "- Do NOT use eval, new Function, fetch, XMLHttpRequest, localStorage, "
        "sessionStorage, document.cookie, or window.parent/top.\n"
        "- Output ONLY raw HTML. No explanations, no Markdown fences."
    ),
    output_key="ui_code",
)

# ---------------------------------------------------------------------------
# AGENT 3 -- Refiner: security gate, keep the design intact
# ---------------------------------------------------------------------------
refiner_agent = LlmAgent(
    name="RefinerAgent",
    model=MODEL,
    instruction=(
        "You are a strict security reviewer. Here is generated HTML:\n\n"
        "{ui_code}\n\n"
        "Return a corrected version that keeps the full visual design and the "
        "Tailwind CDN script, but removes any eval, new Function, fetch, "
        "XMLHttpRequest, localStorage, sessionStorage, document.cookie, or "
        "window.parent/top usage. Do NOT strip layout, styling or content -- "
        "only neutralise forbidden JavaScript. Keep it a single valid HTML "
        "document.\n"
        "Output ONLY the final raw HTML. No explanations, no Markdown fences."
    ),
    output_key="final_code",
)

pipeline = SequentialAgent(
    name="RetinaStylePipeline",
    sub_agents=[vision_agent, codegen_agent, refiner_agent],
)

_session_service = InMemorySessionService()
_runner = Runner(agent=pipeline, app_name=APP_NAME, session_service=_session_service)


async def run_agent_pipeline(image_bytes: bytes) -> str:
    """Run sketch -> spec -> code -> refined code. Returns the final HTML."""
    user_id = "user"
    session_id = uuid.uuid4().hex

    await _session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
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
    return session.state.get("final_code", "")


_TEST_SKETCH_B64 = "iVBORw0KGgoAAAANSUhEUgAAASwAAADcCAIAAABF+guPAAAC5klEQVR4nO3dsW3DMBRAwSjwAgJUagMb3n8Ow94nXVKlCGDqIeLdACSbh0814rJu+wfQ+awPALMTIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIscu4pV/Px7jF4XjX233EsiYhxEQIsYHX0W+DhjgcY/SHlUkIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcQuB+zxej4O2AX+KZMQYiKE2LJue30GmJpJCDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECLFLtfHr+ai2ht9cb/fjNzUJISZCiC3rttdngKmZhBATIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcS8ygQ/vMoEMxIhxLzKBDGTEGIihJgIISZCiIkQYiKEmAghJkKIiRBiIoSYCCEmQoiJEGIihJgIISZCiIkQYiKEmAghJkKIiRBiIoSYCCEmQoiJEGIihJgIIZY9jXY+Ez72ljwkdj4mIcRECDHX0fc7/SVtwov3UCYhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEPPz3/fzb1z+xCSEmAghtqzbXp8BpmYSQkyEEBMhxEQIMRFCTIQQEyHERAgxEUJMhBATIcRECDERQkyEEBMhxEQIMRFCTIQQ+wKzUhn/cyLxNQAAAABJRU5ErkJggg=="

if __name__ == "__main__":
    import asyncio

    async def _test():
        print("Running 3-agent pipeline on a test sketch...\n")
        img = base64.b64decode(_TEST_SKETCH_B64)
        html = await run_agent_pipeline(img)
        print("--- FINAL HTML (first 600 chars) ---")
        print(html[:600])
        print("\n--- length:", len(html), "chars ---")
        print("OK" if "<" in html and "html" in html.lower() else "EMPTY/UNEXPECTED")

    asyncio.run(_test())