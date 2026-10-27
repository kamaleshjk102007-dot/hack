from __future__ import annotations

import re


DANGEROUS = re.compile(r"\b(delete|remove|install|purchase|buy|send|publish|post|format|shutdown|system settings)\b", re.I)


def create_plan(request: str) -> dict:
    text = request.strip()
    lower = text.lower()
    app = "NEXUS"
    if re.match(r"^(?:open|launch|start)\s+blender\b", lower) and not any(x in lower for x in ("create", "make", "render")):
        app = "Blender"
        action_steps = ["Launch Blender"]
    elif "blender" in lower or any(x in lower for x in ("3d ", "render", ".blend")):
        app = "Blender"
        action_steps = ["Launch Blender", "Create a new scene", "Create base geometry",
                        "Build requested structure", "Apply materials", "Add lighting",
                        "Set camera", "Render preview", "Inspect scene", "Save project"]
    elif any(x in lower for x in ("website", "browser", "chrome", "search the web", "search google", "latest",
                                              "youtube", "gmail", "github.com", "chatgpt", "claude.ai")):
        app = "Chrome"
        if re.match(r"^(?:open|visit|go to|search|find|look up)\b", lower):
            action_steps = ["Connect browser", "Open requested destination", "Observe browser response"]
        else:
            action_steps = ["Connect browser", "Open relevant search", "Observe browser response"]
    elif any(x in lower for x in ("code", "react", "python", "vs code", "dashboard")):
        app = "VS Code"
        action_steps = ["Open workspace", "Inspect project", "Create implementation plan",
                        "Edit files", "Run checks", "Review diagnostics"]
    elif any(x in lower for x in ("presentation", "powerpoint", "slides")):
        app = "PowerPoint"
        action_steps = ["Read source content", "Create slide outline", "Build slides",
                        "Apply visual system", "Render and inspect deck"]
    elif re.search(r"\b(open|launch|start|close)\s+(notepad|calculator|paint|word|excel|outlook|edge|firefox)\b", lower) or any(x in lower for x in ("take screenshot", "capture screen", "type text")):
        app = "Windows Computer"
        action_steps = ["Connect local computer", "Execute allowlisted desktop action", "Observe application state"]
    elif any(x in lower for x in ("file", "folder", "zip", "download")):
        app = "File System"
        action_steps = ["Inspect supplied files", "Classify content", "Apply requested organization", "Verify file structure"]
    else:
        action_steps = ["Understand request", "Select available tools", "Perform requested work", "Review result"]
    steps = ["Observe request", f"Identify application: {app}", "Create execution plan"] + action_steps + ["Verify output", "Report result"]
    return {"application": app, "requiresApproval": bool(DANGEROUS.search(text)),
            "steps": [{"id": i + 1, "title": value, "status": "waiting"} for i, value in enumerate(steps)]}
