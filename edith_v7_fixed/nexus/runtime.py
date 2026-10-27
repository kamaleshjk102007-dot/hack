from __future__ import annotations

import hashlib
import json
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .connectors import default_connectors
from .planner import create_plan


class NexusRuntime:
    def __init__(self):
        self.lock = threading.RLock()
        self.connectors = {c.id: c for c in default_connectors()}
        # NEXUS runs inside the local E.D.I.T.H. process; that process is the
        # local agent. Individual connectors still probe their dependencies.
        self.local_agent_connected = True
        self.tasks = {}
        self.approval_tokens = {}  # token -> {task_id, content_hash, expires_at, used}
        self.history = []
        self.memories = [
            {"id": "pref-dark", "type": "User preference", "value": "Use dark UI.", "enabled": True},
            {"id": "project-resq", "type": "Project context", "value": "ResQ360 is an emergency response project.", "enabled": True},
        ]

    @staticmethod
    def compute_task_content_hash(task: dict) -> str:
        """Deterministic SHA-256 hash of security-relevant task parameters."""
        data = {
            "id": str(task.get("id", "")),
            "application": str(task.get("application", "")),
            "request": str(task.get("request", "")).strip(),
            "demo": bool(task.get("demo", False)),
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def snapshot(self):
        with self.lock:
            successes = sum(1 for item in self.history if item.get("status") == "completed")
            today = datetime.now().date().isoformat()
            return {"name": "NEXUS", "tagline": "One AI. Every Application.", "ai": "online",
                    "model": "Adaptive cloud chain", "demoMode": False,
                    "localAgent": {"connected": self.local_agent_connected, "computer": "This Device"},
                    "connectedApps": sum(1 for c in self.connector_manifests() if c["status"] == "connected"),
                    "tasksToday": sum(1 for t in self.history if t.get("createdAt", "").startswith(today)),
                    "successfulTasks": successes, "history": self.history[-8:][::-1]}

    def connector_manifests(self):
        return [c.manifest(self.local_agent_connected) for c in self.connectors.values()]

    def connect_local_agent(self):
        self.local_agent_connected = True
        return {"connected": True, "computer": "This Device",
                "capabilities": ["Application control", "Keyboard control", "Mouse control",
                                 "Screen observation", "File access", "Terminal execution"]}

    def create_task(self, request, demo=False, attachments=None):
        plan = create_plan(request)
        task_id = uuid.uuid4().hex[:12]
        task = {"id": task_id, "name": request[:80], "request": request,
                "status": "planning", "phase": "PLAN", "application": plan["application"],
                "steps": plan["steps"], "requiresApproval": plan["requiresApproval"],
                "approved": False, "demo": bool(demo), "simulated": bool(demo),
                "attachments": attachments or [], "createdAt": datetime.now(timezone.utc).isoformat(),
                "startedAt": time.time(), "elapsed": 0, "result": None, "error": None,
                "approval_consumed": False}
        with self.lock:
            if task["requiresApproval"]:
                content_hash = self.compute_task_content_hash(task)
                token = secrets.token_hex(16)
                self.approval_tokens[token] = {
                    "task_id": task_id,
                    "content_hash": content_hash,
                    "expires_at": time.time() + 300,  # 5 minute TTL
                    "used": False,
                }
                task["pending_approval_token"] = token
            self.tasks[task_id] = task
        threading.Thread(target=self._run, args=(task_id,), daemon=True, name=f"NEXUS-{task_id}").start()
        return task

    def approve(self, task_id, token=None):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task:
                return None, "Task not found."
            if not task.get("requiresApproval"):
                # Task doesn't require approval; nothing to validate
                task["approved"] = True
                task["approval_consumed"] = True
                if task["status"] == "approval_required":
                    task["status"] = "running"
                return task, None

            if not token or not isinstance(token, str):
                return None, "Approval token is required for tasks requiring authorization."

            token_record = self.approval_tokens.get(token)
            if not token_record:
                return None, "Invalid or unknown approval token."

            if token_record["task_id"] != task_id:
                return None, "Approval token was issued for a different task."

            if token_record.get("used"):
                return None, "Approval token has already been consumed (replay rejected)."

            if time.time() > token_record.get("expires_at", 0):
                return None, "Approval token has expired."

            current_hash = self.compute_task_content_hash(task)
            if token_record.get("content_hash") != current_hash:
                return None, "Task parameters have been modified since approval token issuance."

            if task.get("approval_consumed") or task.get("approved"):
                return None, "Task has already been approved."

            # Atomically mark token used and task approved
            token_record["used"] = True
            token_record["used_at"] = time.time()
            task["approved"] = True
            task["approval_consumed"] = True
            task.pop("pending_approval_token", None)
            if task["status"] == "approval_required":
                task["status"] = "running"
            return task, None

    def cancel(self, task_id):
        with self.lock:
            task = self.tasks.get(task_id)
            if not task: return None
            task["status"], task["phase"] = "cancelled", "CANCELLED"
            task["error"] = "Cancelled by user. No pending action was executed."
            task["elapsed"] = int(time.time() - task["startedAt"])
            # Invalidate any pending approval token for this task
            token = task.pop("pending_approval_token", None)
            if token and token in self.approval_tokens:
                self.approval_tokens[token]["used"] = True
                self.approval_tokens[token]["cancelled"] = True
            return task

    def _finish(self, task, status, summary):
        task["status"] = status
        task["phase"] = "SUCCESS" if status == "completed" else "FAILED"
        task["elapsed"] = int(time.time() - task["startedAt"])
        task["result"] = {"summary": summary, "applications": [task["application"]],
                          "actions": sum(1 for step in task["steps"] if step["status"] == "completed"),
                          "output": task.get("output"), "render": task.get("render")}
        self.history.append({"id": task["id"], "name": task["name"], "createdAt": task["createdAt"],
                             "duration": task["elapsed"], "applications": [task["application"]],
                             "status": status, "result": summary, "simulated": task["simulated"]})

    def _execute_live_request(self, connector_id, connector, request_text):
        text = request_text.strip()
        lower = text.lower()
        if connector_id == "browser":
            destination = re.search(r"(?:open|visit|go to)\s+(https?://\S+|[\w.-]+\.[a-z]{2,}|youtube|google|gmail|github|chatgpt|claude)", text, re.I)
            if destination:
                from plugins.universal_control import open_website
                message = open_website(destination.group(1))
                from .contracts import ToolResult
                return ToolResult(message.startswith("SUCCESS:"), message)
            query = re.sub(r"^(?:search(?: the web| google)?(?: for)?|find|look up)\s+", "", text, flags=re.I).strip()
            return connector.execute("search", {"query": query or text, "site": "google"})
        if connector_id == "computer":
            app = re.search(r"^(?:open|launch|start)\s+(.+)$", text, re.I)
            if app:
                return connector.execute("open_app", {"target": app.group(1).strip()})
            typed = re.search(r"^(?:type|enter text)\s+(.+)$", text, re.I | re.S)
            if typed:
                return connector.execute("type_text", {"text": typed.group(1)})
            if re.search(r"(?:take|capture).*(?:screen|screenshot)", lower):
                return connector.execute("screenshot", {})
            from .contracts import ToolResult
            return ToolResult(False, "The requested desktop action is not yet in the safe action registry.")
        from .contracts import ToolResult
        return ToolResult(True, "Connector ready.")

    def _run(self, task_id):
        task = self.tasks[task_id]
        for index, step in enumerate(task["steps"]):
            with self.lock:
                if task["status"] in {"cancelled", "failed"}:
                    return
                if task["requiresApproval"]:
                    if index >= 3 and not task.get("approved"):
                        task["status"], task["phase"] = "approval_required", "APPROVAL"
            while task["status"] == "approval_required":
                time.sleep(.05)
            if task["status"] in {"cancelled", "failed"}:
                return
            if task["requiresApproval"] and index >= 3 and not task.get("approval_consumed"):
                with self.lock:
                    step["status"] = "failed"
                    self._finish(task, "failed", "Execution rejected: task requires valid authorization.")
                return
            if not task["demo"] and index == 3:
                connector_id = {"Blender": "blender", "Chrome": "browser", "Windows Computer": "computer", "VS Code": "vscode",
                                "File System": "filesystem"}.get(task["application"])
                connector = self.connectors.get(connector_id) if connector_id else None
                manifest = connector.manifest(self.local_agent_connected) if connector else None
                if not connector or not manifest or manifest["status"] != "connected":
                    with self.lock:
                        step["status"] = "failed"
                        reason = (manifest or {}).get("statusLabel", "No connector registered")
                        self._finish(task, "failed", f"Live execution stopped: {task['application']} — {reason}.")
                    return
                if connector_id == "blender":
                    result = connector.execute("open", {})
                    if not result.ok:
                        with self.lock:
                            step["status"] = "failed"
                            self._finish(task, "failed", f"Live execution failed: {result.message}")
                        return
                elif connector_id in {"browser", "computer"}:
                    result = self._execute_live_request(connector_id, connector, task["request"])
                    if not result.ok:
                        with self.lock:
                            step["status"] = "failed"
                            self._finish(task, "failed", f"Live execution failed: {result.message}")
                        return
                    task["live_message"] = result.message
                    task["output"] = result.data.get("output") if result.data else None
            if not task["demo"] and index == 4 and task["application"] == "Blender" and len(task["steps"]) > 7:
                result = self.connectors["blender"].execute("create_human_face", {"prompt": task["request"]})
                if not result.ok:
                    with self.lock:
                        step["status"] = "failed"
                        self._finish(task, "failed", f"Blender launched, but execution stopped: {result.message}")
                    return
                task["output"] = result.data.get("output")
                task["render"] = result.data.get("render")
            with self.lock:
                if task["status"] in {"cancelled", "failed"}:
                    return
                task["status"] = "running"
                task["phase"] = "OBSERVE" if index == 0 else ("VERIFY" if "Verify" in step["title"] else "ACT")
                step["status"] = "running"
                task["elapsed"] = int(time.time() - task["startedAt"])
            time.sleep(.32 if task["demo"] else .12)
            with self.lock:
                if task["status"] in {"cancelled", "failed"}:
                    return
                step["status"] = "completed"
        with self.lock:
            if task["status"] in {"cancelled", "failed"}:
                return
            qualifier = "Demo execution completed. No external application was controlled." if task["demo"] else task.get("live_message", "Execution completed through configured connectors.")
            self._finish(task, "completed", qualifier)


runtime = NexusRuntime()
