"""Cached tray reporting for the owning host; no native inspection or restart effects."""

import copy
import json
import threading
import time
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from mcp.types import TextContent
from universal_tools import __version__ as framework_running
from universal_tools.framework import ApplicationBackend
from universal_tools.management import ComponentVersion, ManagedStatus, RestartResult

from . import __version__ as host_running
from .maintenance import journal_status

PLUGIN_ID = "freecad-modeling@freecad-development"
RESTART_REASON = (
    "Tray restart is unavailable: no surviving supervisor fences every chat and verifies "
    "unsaved FreeCAD documents, Undo history and unresolved effects. Use explicit idle-host maintenance."
)
COMPONENTS = {
    "app": "codex-freecad",
    "host": "freecad-mcp-host",
    "framework": "universal-codex-tools",
    "mcp": "mcp",
}


def installed_version(distribution):
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unknown"


def local_json(path):
    if not path.exists():
        return {}
    raw = path.read_bytes()
    if len(raw) > 8192:
        raise ValueError("Management metadata exceeds its limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Invalid management metadata")
    return value


def newer(available, installed):
    # Local artifacts use numeric package versions. Unknown ordering is not an update claim.
    if not available:
        return False
    try:
        return tuple(map(int, available.split("."))) > tuple(map(int, installed.split(".")))
    except ValueError:
        return False


class StatusCache:
    def __init__(self, state, publication, *, stale_after=10, clock=time.monotonic):
        self.state, self.output = Path(state), Path(publication).parent
        self.clock, self.stale_after = clock, stale_after
        self.lock = threading.RLock()
        self.active = 0
        self.ready = self.stopped = False
        self.error = None
        self.stamp = clock()
        self.journals = None
        self.versions = {}
        self.resources = {"state": "unassessed", "durable_ledger": "awaiting-shared-api"}
        self.running = {name: installed_version(package) for name, package in COMPONENTS.items()}
        self.running.update(framework=framework_running, host=host_running)

    def collect(self):
        """Producer-only file reads. The HTTP status callback never calls this method."""
        from codex_freecad.process_lifetime import ProcessSlots, process_tree_snapshot
        from codex_freecad.resource_ownership import supervisor_status

        resources = process_tree_snapshot()
        resources.update(supervisor_status())
        resources["sampled_frontends"] = ProcessSlots.occupied(self.state / "frontends")
        resources["frontend_limit"] = 8
        with self.lock:
            self.resources = resources
        available = local_json(self.output / "available-versions.json").get("versions", {})
        plugin = local_json(self.output / "installed-plugin.json")
        versions = {}
        for name, package in COMPONENTS.items():
            installed = installed_version(package)
            running = self.running[name]
            versions[name] = ComponentVersion(
                installed=installed,
                running=None if running == "unknown" else running,
                available=available.get(name),
                update_pending=newer(available.get(name), installed),
            )
        plugin_installed = (
            plugin.get("version", "unknown") if plugin.get("plugin_id") == PLUGIN_ID else "unknown"
        )
        versions["plugin"] = ComponentVersion(
            installed=plugin_installed,
            running=None,
            available=available.get("plugin"),
            update_pending=newer(available.get("plugin"), plugin_installed),
        )
        return versions, journal_status(self.state)

    def refresh(self, versions, journals, *, catalog_available=True):
        with self.lock:
            self.versions, self.journals = versions, journals
            self.ready, self.stamp = True, self.clock()
            self.error = (
                None if catalog_available else "A CAD backend is unavailable; inspect host doctor."
            )

    def failed(self):
        with self.lock:
            self.error = "Management metadata is unavailable; native state was not inspected."

    def close(self):
        with self.lock:
            self.stopped = True

    def resource_snapshot(self):
        with self.lock:
            return copy.deepcopy(self.resources)

    @contextmanager
    def operation(self):
        with self.lock:
            self.active += 1
        try:
            yield
        finally:
            with self.lock:
                self.active -= 1

    def snapshot(self):
        with self.lock:
            state, message = "running", "CAD host available; native documents were not inspected."
            if self.stopped:
                state, message = "stopped", "CAD host stopped."
            elif self.error or self.clock() - self.stamp > self.stale_after:
                state, message = (
                    "degraded",
                    self.error or "Management status is stale; native state was not inspected.",
                )
            elif not self.ready:
                state, message = "starting", "CAD host is starting."
            elif self.active:
                state, message = "busy", "CAD requests are in progress."
            elif self.journals and not self.journals["idle"]:
                state = (
                    "degraded"
                    if self.journals["unresolved_writes"]
                    or any(row["state"] == "lost" for row in self.journals["contexts"])
                    else "busy"
                )
                message = "Retained CAD contexts or unresolved effects require app-owned review."
            message += (
                f" Frontends {self.resources.get('sampled_frontends', 'unknown')}/8; "
                "attached GUIs are external. Durable resource recovery pending."
            )
            return ManagedStatus(
                state=state,
                message=message,
                active_operations=self.active,
                versions=self.versions,
                restart_allowed=False,
                restart_reason=RESTART_REASON,
            ).model_copy(deep=True)

    @staticmethod
    def refuse_restart(_):
        return RestartResult(outcome="blocked", message=RESTART_REASON)


class ReportingBackend(ApplicationBackend):
    """Count CAD-facing calls while preserving the framework's routing and ownership."""

    async def invoke(self, name, arguments, *, relay=None):
        if name == "broker_status":
            result = await super().invoke(name, arguments, relay=relay)
            if result.is_error or result.structured_content is None:
                return result
            value = {
                **result.structured_content,
                "resource_ownership": self.host.tray_status.resource_snapshot(),
            }
            return result.model_copy(
                update={
                    "structured_content": value,
                    "content": [TextContent(type="text", text=json.dumps(value))],
                }
            )
        if name in {
            "call_read_tool",
            "call_write_tool",
            "acquire_service",
            "release_service",
            "refresh_capabilities",
            "refresh_services",
        }:
            with self.host.tray_status.operation():
                return await super().invoke(name, arguments, relay=relay)
        return await super().invoke(name, arguments, relay=relay)
