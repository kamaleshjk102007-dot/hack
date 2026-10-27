from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .contracts import Connector, ToolResult, ToolSpec


class BlenderConnector(Connector):
    id, name, category = "blender", "Blender", "Design"
    description = "3D scene creation through Blender Python and its command line interface."

    def _executable(self):
        configured = os.getenv("NEXUS_BLENDER_PATH", "").strip()
        candidates = [configured, shutil.which("blender")]
        program_files = Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Blender Foundation"
        if program_files.exists():
            candidates.extend(str(p) for p in program_files.glob("Blender */blender.exe"))
        return next((str(p) for p in candidates if p and Path(p).is_file()), None)

    def probe(self, local_agent_connected):
        found = bool(self._executable())
        connected = bool(local_agent_connected and found)
        return {"status": "connected" if connected else "not_configured",
                "statusLabel": "Connected" if connected else ("Requires local agent" if found else "Connector not configured"),
                "available": found, "requiresLocalAgent": True}

    def tools(self):
        return [
            ToolSpec("open", "Launch Blender", {}),
            ToolSpec("create_project", "Create a Blender project", {"path": "string"}),
            ToolSpec("create_human_face", "Create, light, render and save a procedural human face", {"prompt": "string"}),
            ToolSpec("execute_python", "Execute Blender Python", {"script": "string"}, "elevated"),
            ToolSpec("create_object", "Create scene objects", {"type": "string", "name": "string"}),
            ToolSpec("modify_object", "Modify an existing object", {"name": "string", "changes": "object"}),
            ToolSpec("add_material", "Create and apply materials", {"object": "string", "material": "object"}),
            ToolSpec("add_camera", "Add and configure a camera", {"settings": "object"}),
            ToolSpec("add_lighting", "Add scene lighting", {"settings": "object"}),
            ToolSpec("render", "Render the active scene", {"output": "string"}),
            ToolSpec("inspect_scene", "Inspect objects and scene state", {}),
            ToolSpec("save_project", "Save the .blend project", {"path": "string"}),
        ]

    def execute(self, tool, parameters):
        exe = self._executable()
        if not exe:
            return ToolResult(False, "Blender connector is not configured. Set NEXUS_BLENDER_PATH.")
        if tool == "open":
            subprocess.Popen([exe])
            return ToolResult(True, "Blender launched.")
        if tool == "create_human_face":
            script = Path(__file__).resolve().parent / "blender_scripts" / "human_face.py"
            output_dir = Path.home() / "Documents" / "NEXUS" / datetime.now().strftime("human_face_%Y%m%d_%H%M%S")
            output_dir.mkdir(parents=True, exist_ok=True)
            try:
                completed = subprocess.run(
                    [exe, "--background", "--python", str(script), "--", "--output-dir", str(output_dir)],
                    capture_output=True, text=True, timeout=240,
                )
            except subprocess.TimeoutExpired:
                return ToolResult(False, "Blender timed out after four minutes.")
            if completed.returncode != 0:
                error = (completed.stderr or completed.stdout or "Unknown Blender error")[-1200:]
                return ToolResult(False, f"Blender execution failed: {error}")
            blend = output_dir / "nexus_human_face.blend"
            render = output_dir / "nexus_human_face.png"
            if not blend.exists() or not render.exists():
                return ToolResult(False, "Blender finished but the verified output files were not created.")
            subprocess.Popen([exe, str(blend)])
            return ToolResult(True, "Created and verified a procedural 3D human face in Blender.",
                              {"output": str(blend), "render": str(render)})
        return ToolResult(False, f"Blender tool '{tool}' requires the local Blender bridge, which is not configured.")


class BrowserConnector(Connector):
    id, name, category = "browser", "Chrome", "Browser"
    description = "Browser navigation and page interaction through a local browser bridge."

    def probe(self, local_agent_connected):
        return {"status": "connected" if local_agent_connected else "ready_to_connect",
                "statusLabel": "Ready" if local_agent_connected else "Ready to connect",
                "available": True, "requiresLocalAgent": True}

    def tools(self):
        return [ToolSpec(n, d, {}) for n, d in [
            ("open_website", "Open an HTTP or HTTPS website"), ("navigate", "Navigate to a URL"),
            ("search", "Search the web"), ("click", "Click a page element"),
            ("type", "Type into a page field"), ("upload", "Upload a selected file"),
            ("download", "Download a file"), ("read_page", "Read visible page content"),
            ("extract", "Extract structured information"), ("screenshot", "Capture the page")]]

    def execute(self, tool, parameters):
        if tool in {"open_website", "navigate"}:
            url = str(parameters.get("url", ""))
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return ToolResult(False, "Only valid HTTP/HTTPS URLs are allowed.")
            return ToolResult(bool(webbrowser.open(url, new=2)), f"Opened {url}")
        if tool == "search":
            query = str(parameters.get("query", "")).strip()
            if not query:
                return ToolResult(False, "A browser search query is required.")
            from plugins.universal_control import search_website
            opened = search_website(str(parameters.get("site", "google")), query)
            return ToolResult(opened.startswith("SUCCESS:"), opened)
        return ToolResult(False, f"'{tool}' requires the local browser bridge.")


class ComputerConnector(Connector):
    id, name, category = "computer", "Windows Computer", "Desktop"
    description = "Real allowlisted Windows application, keyboard, browser and screenshot control."

    def probe(self, local_agent_connected):
        return {"status": "connected" if local_agent_connected else "ready_to_connect",
                "statusLabel": "Connected" if local_agent_connected else "Requires local agent",
                "available": True, "requiresLocalAgent": True}

    def tools(self):
        return [ToolSpec(name, desc, {}) for name, desc in [
            ("open_app", "Open a configured Windows application"),
            ("close_app", "Close a configured application with confirmation"),
            ("type_text", "Type text into the focused control"),
            ("press_key", "Press an allowlisted key"),
            ("hotkey", "Use an allowlisted keyboard shortcut"),
            ("screenshot", "Capture the current screen")]]

    def execute(self, tool, parameters):
        from plugins.universal_control import control
        result = control(tool, target=str(parameters.get("target", "")),
                         text=str(parameters.get("text", "")), keys=parameters.get("keys"))
        ok = result.startswith("SUCCESS:") or result.startswith("✅")
        return ToolResult(ok, result)


class ManifestConnector(Connector):
    def __init__(self, connector_id, name, category, description, capabilities):
        self.id, self.name, self.category = connector_id, name, category
        self.description, self._capabilities = description, capabilities

    def probe(self, local_agent_connected):
        return {"status": "not_configured", "statusLabel": "Connector not configured",
                "available": False, "requiresLocalAgent": True}

    def tools(self):
        return [ToolSpec(name, f"{name.replace('_', ' ').title()} using {self.name}", {}) for name in self._capabilities]

    def execute(self, tool, parameters):
        return ToolResult(False, f"{self.name} connector is not configured.")


def default_connectors():
    return [
        BlenderConnector(), BrowserConnector(), ComputerConnector(),
        ManifestConnector("vscode", "VS Code", "Development", "Code editing and workspace automation.", ["open_workspace", "edit_file", "run_task", "inspect_diagnostics"]),
        ManifestConnector("figma", "Figma", "Design", "Design-file inspection and editing.", ["read_design", "create_frame", "edit_component", "export_asset"]),
        ManifestConnector("photoshop", "Photoshop", "Design", "Image editing through a future local bridge.", ["open_document", "edit_layer", "export_image"]),
        ManifestConnector("github", "GitHub", "Development", "Repository, issue and pull-request workflows.", ["read_repository", "create_issue", "open_pull_request"]),
        ManifestConnector("terminal", "Terminal", "Development", "Permission-aware command execution.", ["run_command", "read_output"]),
        ManifestConnector("filesystem", "File System", "Files", "Scoped local file operations.", ["read_file", "write_file", "move_file", "list_folder"]),
    ]
