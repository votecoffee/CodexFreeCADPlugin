"""One guide snapshot backs ordinary tool reads and the explicit HTTP skill catalog."""

import asyncio
import json
from contextlib import AsyncExitStack
from pathlib import Path

from universal_tools.skill_catalog import SkillCatalog
from universal_tools.skill_manifest import OPENAI_IMPORT_PROFILE

from codex_freecad.framework_setup import atomic_json
from codex_freecad.workflows import build_snapshot, digest, publication_inputs, validate


class GuidanceCatalog:
    def __init__(self, publication):
        self.root = Path(publication).parent / "guidance"
        source, extensions = publication_inputs(publication)
        service = json.loads(Path(publication).read_bytes())["backends"][0]["service"]
        config = {
            name: service[name]
            for name in ("protocol_mode", "watch_catalog", "discovery_cache_ttl_seconds")
            if name in service
        }
        base = build_snapshot(extensions, source_package=source, feature_config=config)
        self.current = base
        selection = self.root / "selection.json"
        if selection.exists():
            saved = json.loads(selection.read_bytes())
            if saved.get("source_revision") == base["revision"]:
                self.current = validate(json.loads((self.root / "active.json").read_bytes()))
        self.catalog = SkillCatalog([self.package(self.current)], profile=OPENAI_IMPORT_PROFILE)
        atomic_json(self.root / "active.json", self.current)
        atomic_json(selection, {"source_revision": base["revision"]})
        self.seen = None
        self.lock = asyncio.Lock()

    def package(self, candidate):
        target = self.root / "packages" / candidate["revision"] / "freecad-modeling"
        expected = {name: text.encode("utf-8") for name, text in candidate["files"].items()}
        if target.exists():
            actual = {
                p.relative_to(target).as_posix(): p.read_bytes()
                for p in target.rglob("*")
                if p.is_file()
            }
            if actual != expected:
                raise ValueError("Existing immutable guide package changed")
        else:
            for name, raw in expected.items():
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
        return target

    async def refresh(self, host):
        desired = self.root / "desired.json"
        if not desired.exists():
            return
        with desired.open("rb") as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            atomic_json(
                self.root / "result.json",
                {"status": "rejected", "revision": self.current["revision"]},
            )
            return
        key = digest(raw)
        if key == self.seen:
            return
        self.seen = key
        try:
            request = json.loads(raw)
            candidate = validate(request["snapshot"])
            if request["expected_revision"] != self.current["revision"]:
                raise ValueError("Stale guide publication revision")
            package = self.package(candidate)
            SkillCatalog(
                [package], profile=OPENAI_IMPORT_PROFILE
            )  # Validate before changing any live view.
            async with self.lock, AsyncExitStack() as stack:
                for backend in sorted(host.definition.backends, key=lambda row: row.service.id):
                    await stack.enter_async_context(host.gate(backend.service.id))
                old = self.current
                atomic_json(self.root / "active.json", candidate)

                async def commit():
                    try:
                        await self.catalog.publish(
                            [package], expected_revision=self.catalog.revision
                        )
                    except BaseException:
                        atomic_json(self.root / "active.json", old)
                        raise
                    self.current = candidate

                task = asyncio.create_task(commit())
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    await task
                    raise
            atomic_json(
                self.root / "result.json", {"status": "applied", "revision": candidate["revision"]}
            )
        except Exception:
            atomic_json(
                self.root / "result.json",
                {"status": "rejected", "revision": self.current["revision"]},
            )
