# RetinaStyle AI — 5-Minute Demo Video Script

**Format:** Screen recording + voiceover. No face-cam needed.
**Before recording:** Do one throwaway generation first to warm up the model. Then start.

---

## SCENE 1 — Hook (0:00–0:25)
**Show:** App loaded, aurora background drifting, nothing drawn yet.

**Say:**
> "Turning a UI idea into working code is slow — sketch it, hand it off, code it, review it, repeat. This is RetinaStyle AI. Draw a rough wireframe, and four AI agents turn it into a real working interface in seconds. Let me show you."

---

## SCENE 2 — Live demo (0:25–1:30)
**Show:** Pick Dark style. Draw a wireframe — header box, two input lines, a button. Hit Generate UI. Watch pipeline strip light up. UI renders.

**Say (while drawing):**
> "I'll pick a style and sketch something rough — a header, two fields, a button. Nothing precise. Now I hit Generate."

**Say (as pipeline runs, then UI appears):**
> "Watch the pipeline — four agents, each doing one job. And there it is: a clean, styled login screen, generated from that scribble, rendering live."

*(Pause 2 seconds. Let the result land.)*

---

## SCENE 3 — Explain the agents (1:30–2:40)
**Show:** Point at green pipeline strip. Open audit panel. Expand Vision agent spec.

**Say:**
> "This isn't one prompt doing everything. It's a Google ADK multi-agent pipeline. The Vision agent reads the sketch and infers intent — here's the spec it produced. CodeGen turned that into Tailwind HTML. Refiner cleaned it up. And the fourth agent ran a security audit through an MCP server — the Model Context Protocol — calling two tools: validate the code and audit accessibility."

**Show:** Point at Security (MCP) clean pill and Accessibility pass pill.

---

## SCENE 4 — Show the code (2:40–3:40)
**Show:** VS Code — agents.py showing the SequentialAgent with 4 sub-agents. Then mcp_server.py showing the two @mcp.tool() functions.

**Say:**
> "In agents.py — one ADK SequentialAgent chains all four agents. The Security Auditor connects to the MCP toolset. In mcp_server.py — two MCP tools via FastMCP: validate-ui-code and audit-accessibility. Security is defense in depth: agent audit, Python validator, sandboxed iframe. Safety never depends on model output alone."

---

## SCENE 5 — Second generation (3:40–4:30)
**Show:** Clear canvas. Draw a different sketch — a card with image area and buttons. Pick Glass style. Generate. When done click Code tab and scroll briefly.

**Say:**
> "Different sketch, different style — the agents adapt: layout, spacing, components, all inferred from the drawing. Flip to code view to read, copy, or download the HTML."

---

## SCENE 6 — Close (4:30–5:00)
**Show:** Full app view. End with GitHub URL on screen.

**Say:**
> "RetinaStyle AI — a sketch becomes a working interface, built by four Gemini agents coordinated by Google's ADK, backed by an MCP tool server, and secured at every layer. A complete agentic system you can watch think. Code on GitHub — thanks for watching."

**Show on screen:**
github.com/Alexy-ak06/RetinaStyle

---

## Checklist — say these out loud in the video
- [ ] "Google ADK multi-agent pipeline" — Scene 3
- [ ] "MCP server" / "Model Context Protocol" — Scene 3
- [ ] "Security" / "defense in depth" / "sandboxed iframe" — Scene 4