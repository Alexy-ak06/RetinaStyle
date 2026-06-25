# RetinaStyle AI

**Sketch → multi-agent pipeline → live UI.** Draw a rough wireframe on a canvas; a team of three Gemini-powered agents reads it, designs a real interface, writes the code, and security-checks it — then it renders live in a sandboxed frame, in seconds.

Built for the Kaggle x Google **AI Agents Intensive — Vibe Coding Capstone** (Freestyle track).



## The problem

Turning a UI idea into working front-end code is slow: sketch, hand off, code, review, repeat. RetinaStyle collapses that loop. A hand-drawn wireframe becomes a polished, functional interface instantly — so anyone can prototype a screen without writing markup.

## Why agents?

A single prompt can turn an image into code, but it conflates three different jobs. RetinaStyle splits them across specialists, which both improves quality and makes the system inspectable:

- **Vision Agent** — looks at the sketch and *infers intent* (a box up top is a header, lines are input fields, a small box is a button), producing a structured UI spec.
- **CodeGen Agent** — turns that spec into a complete, polished Tailwind page with realistic content.
- **Refiner Agent** — reviews the generated HTML against security rules without stripping the design.

## Architecture

```
 Browser (index.html)
   canvas sketch --> PNG (base64)
        |  POST /generate
        v
 FastAPI backend (app.py)
        |
        v  Google ADK SequentialAgent (agents.py)
   [ Vision Agent ] -> [ CodeGen Agent ] -> [ Refiner Agent ]
     (ui_spec)            (ui_code)            (final_code)
        |
        v  Python security validator (hard gate)
   clean HTML --> sandboxed <iframe> --> live preview
```

## Course concepts demonstrated

| Concept                       | Where                                              |
|-------------------------------|----------------------------------------------------|
| Multi-agent system (ADK)      | agents.py — 3-agent SequentialAgent pipeline       |
| Security features             | app.py validator + sandbox iframe + Refiner agent  |
| MCP Server                    | in progress                                        |

The security layer is defense-in-depth: the Refiner agent removes forbidden
JavaScript, a Python validator then scans and neutralizes a denylist of
dangerous patterns (eval, fetch, document.cookie, iframe-escape, remote
scripts), and the preview runs inside a sandbox="allow-scripts" iframe with
no access to the parent page, cookies, or network.

## Setup

Requires Python 3.10+ (developed on 3.14).

```bash
python -m venv venv
venv\Scripts\activate            # Windows  (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

copy .env.example .env           # then paste your Gemini key into .env
#   key from https://aistudio.google.com/app/apikey

uvicorn app:app --reload --port 8000
```

Open http://localhost:8000, draw a wireframe, press **Generate UI**.

## Configuration

`.env` keys:

- `GEMINI_API_KEY` — your key (never commit `.env`).
- `GEMINI_MODEL` — defaults to `gemini-2.5-flash`.

## Project structure

```
app.py            FastAPI server, security validator, serves the frontend
agents.py         the 3-agent Google ADK pipeline
index.html        canvas UI + sandboxed live preview
requirements.txt  pinned dependencies
.env.example      template for your API key (copy to .env)
```

## Security note

Never commit `.env` or hard-code keys. The validator and sandbox reduce risk
but model output is always treated as untrusted.