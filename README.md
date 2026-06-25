# RetinaStyle AI

**Sketch → multi-agent pipeline → live UI.** Draw a rough wireframe on a canvas; a team of four Gemini-powered agents — coordinated by Google's ADK and backed by an MCP tool server — reads your intent, designs a real interface, writes the code, and security-audits it. The result renders live in a sandboxed frame, in seconds.

Built for the Kaggle × Google **AI Agents Intensive — Vibe Coding Capstone** (Freestyle track).

---

## The problem

Turning a UI idea into working front-end code is slow: sketch, hand off, code, review, repeat. RetinaStyle collapses that loop. A hand-drawn wireframe becomes a polished, functional interface instantly — so anyone can prototype a screen without writing markup.

## Why agents?

A single prompt can turn an image into code, but it conflates several different jobs. RetinaStyle splits them across specialists, which improves quality and — just as importantly — makes the system **inspectable**: you can see each agent's contribution in the UI.

- **Vision Agent** — looks at the sketch and *infers intent* (a box up top is a header, lines are input fields, a small box is a button), producing a structured UI spec.
- **CodeGen Agent** — turns that spec into a complete, polished Tailwind page, honouring the chosen style preset.
- **Refiner Agent** — cleans up the generated HTML and removes forbidden JavaScript without stripping the design.
- **Security Auditor Agent** — calls the **MCP server's** tools (`validate_ui_code`, `audit_accessibility`) to scan the code and report findings, then emits the cleaned result.

## Architecture

```
 Browser (index.html)
   canvas sketch + style --> PNG (base64)
        |  POST /generate
        v
 FastAPI backend (app.py)
        |
        v  Google ADK SequentialAgent (agents.py)
   [ Vision ] -> [ CodeGen ] -> [ Refiner ] -> [ Security Auditor ]
    ui_spec       ui_code       refined_code        |
                                                    |  MCP (stdio)
                                                    v
                                       MCP server (mcp_server.py)
                                       - validate_ui_code
                                       - audit_accessibility
        |
        v  Python security validator (hard gate)
   clean HTML --> sandboxed <iframe> --> live preview
```

## Course concepts demonstrated

| Concept                  | Where                                                                 |
|--------------------------|-----------------------------------------------------------------------|
| Multi-agent system (ADK) | `agents.py` — 4-agent `SequentialAgent` pipeline                      |
| MCP Server               | `mcp_server.py` — FastMCP server; the Security Auditor agent calls it |
| Security features        | MCP audit + `app.py` validator (hard gate) + sandboxed iframe         |

The security layer is **defense-in-depth**:

1. The **Refiner agent** removes forbidden JavaScript while preserving the design.
2. The **Security Auditor agent** calls the MCP server to validate the code and audit accessibility — agent-to-tool interoperability over the Model Context Protocol.
3. A **Python validator** (`app.py`) then independently scans and neutralizes a denylist of dangerous patterns (`eval`, `fetch`, `document.cookie`, `localStorage`, iframe-escape, remote scripts), so safety never depends on model output alone.
4. The preview runs inside a `sandbox="allow-scripts"` **iframe** with no access to the parent page, cookies, or network.

## Setup

Requires Python 3.10+ (developed on 3.14).

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

copy .env.example .env           # then paste your Gemini key into .env
#   key from https://aistudio.google.com/app/apikey

uvicorn app:app --port 8000
```

Open http://localhost:8000, draw a wireframe, pick a style, press **Generate UI**.

> **Note:** run without `--reload`. The Security Auditor agent launches the MCP
> server as a stdio subprocess; the reloader can restart it mid-request.

## Configuration

`.env` keys:

- `GEMINI_API_KEY` — your key (never commit `.env`).
- `GEMINI_MODEL` — defaults to `gemini-2.5-flash`. `gemini-2.5-flash-lite` gives
  more free-tier headroom if you hit rate limits.

## Project structure

```
app.py            FastAPI server, security validator (hard gate), serves the frontend
agents.py         the 4-agent Google ADK pipeline (Vision, CodeGen, Refiner, Security Auditor)
mcp_server.py     MCP server exposing validate_ui_code + audit_accessibility tools
index.html        canvas UI, WebGL background, live pipeline view, sandboxed preview
requirements.txt  pinned dependencies
.env.example      template for your API key (copy to .env)
```

## Security note

Never commit `.env` or hard-code keys. The MCP audit, the validator, and the
sandbox reduce risk, but model output is always treated as untrusted.