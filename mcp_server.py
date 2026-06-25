"""
RetinaStyle AI  --  MCP server
==============================
Exposes the project's code-safety tools over the Model Context Protocol (MCP)
so the ADK agents can call them as standard MCP tools instead of hard-coding
the logic inside an agent prompt.

Tools exposed:
  - validate_ui_code(code)    : scan generated HTML/JS for dangerous patterns
  - audit_accessibility(code) : basic accessibility checks on the HTML

Run as an MCP server (stdio, what ADK launches):
    python mcp_server.py

Self-test the tool logic without MCP:
    python mcp_server.py --selftest
"""

import re
import sys

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("retinastyle-tools")

# Same denylist the app uses -- kept here so the server is self-contained.
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


def _validate(code: str) -> dict:
    findings = []
    cleaned = code
    for pattern in BLOCKED_PATTERNS:
        if re.findall(pattern, cleaned, flags=re.IGNORECASE):
            findings.append(pattern)
            cleaned = re.sub(pattern, "/*blocked*/", cleaned, flags=re.IGNORECASE)
    return {
        "safe": len(findings) == 0,
        "blocked_count": len(findings),
        "patterns": findings,
        "cleaned_code": cleaned,
    }


def _audit(code: str) -> dict:
    issues = []
    low = code.lower()
    if "<html" in low and "lang=" not in low:
        issues.append("html element is missing a lang attribute")
    if "<img" in low and "alt=" not in low:
        issues.append("at least one img is missing an alt attribute")
    if ("<input" in low or "<select" in low or "<textarea" in low) and "<label" not in low:
        issues.append("form fields present but no <label> elements found")
    if re.search(r"<button[^>]*>\s*</button>", low):
        issues.append("a button has no accessible text")
    return {
        "accessible": len(issues) == 0,
        "issue_count": len(issues),
        "issues": issues,
    }


@mcp.tool()
def validate_ui_code(code: str) -> dict:
    """Scan generated HTML/JS for dangerous patterns (eval, fetch, cookies,
    iframe-escape attempts, remote scripts) and return the findings plus a
    cleaned version with each match neutralised."""
    return _validate(code)


@mcp.tool()
def audit_accessibility(code: str) -> dict:
    """Run basic accessibility checks on an HTML document (missing lang, missing
    alt text, form fields without labels, empty buttons) and return any issues."""
    return _audit(code)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sample = (
            '<html><body><script>eval("x"); fetch("/y")</script>'
            '<img src="a.png"><input></body></html>'
        )
        print("validate_ui_code ->", _validate(sample))
        print("audit_accessibility ->", _audit(sample))
        print("SELFTEST OK")
    else:
        mcp.run()