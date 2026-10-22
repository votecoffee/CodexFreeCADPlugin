"""App-owned ASGI lifecycle with a reporting-only tray endpoint."""

import asyncio
import secrets
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from universal_tools.daemon import ProtectedApp
from universal_tools.framework import ApplicationHost
from universal_tools.management import ManagedService
from universal_tools.models import load_settings

from codex_freecad.resource_ownership import resource_session

from . import APPLICATION_ID
from .guidance import GuidanceCatalog
from .management import PLUGIN_ID, ReportingBackend, StatusCache


def serve(state, publication, *, registry=None):
    if registry is not None:
        from pathlib import Path

        from universal_tools.framework import load_application

        for backend in load_application(publication).backends:
            args = backend.service.transport.args
            if (
                "--resource-registry" not in args
                or Path(args[args.index("--resource-registry") + 1]).resolve()
                != Path(registry).resolve()
            ):
                raise ValueError(
                    "An isolated host requires the same explicit resource registry on every backend"
                )
    settings = load_settings(state)
    host = ApplicationHost(
        state, publication, max_request_body_bytes=settings.max_request_body_bytes
    )
    host.tray_status = cache = StatusCache(state, publication)
    host.backend = ReportingBackend(host)
    guidance = GuidanceCatalog(publication)
    server = host.create_server(port=settings.port, skills=guidance.catalog)
    base = server.streamable_http_app(**server.http_options)

    async def refresh():
        try:
            # Public cached catalog only; no engineering context is acquired for status.
            result = await host.client().invoke("broker_status", {})
            services = (result.structured_content or {}).get("services", [])
            available = (
                not result.is_error
                and {row["service_id"] for row in services}
                == {backend.service.id for backend in host.definition.backends}
                and all(row["status"] == "available" for row in services)
            )
            versions, journals = await asyncio.to_thread(cache.collect)
            cache.refresh(versions, journals, catalog_available=available)
        except Exception:
            cache.failed()  # No paths, project details or credentials in the management endpoint.

    async def watch():
        while True:
            await asyncio.sleep(2)
            try:
                await guidance.refresh(host)
            except (ValueError, OSError):
                cache.failed()
            await refresh()

    @asynccontextmanager
    async def lifespan(_):
        watcher = None
        with ManagedService(
            APPLICATION_ID,
            "FreeCADMCPServer",
            cache.snapshot,
            restart=cache.refuse_restart,
            plugin_id=PLUGIN_ID,
            registry=registry,
        ):
            try:
                async with host:
                    await refresh()
                    watcher = asyncio.create_task(watch())
                    async with server.session_manager.run():
                        yield
            finally:
                if watcher is not None:
                    watcher.cancel()
                    await asyncio.gather(watcher, return_exceptions=True)
                cache.close()

    app = Starlette(routes=base.routes, lifespan=lifespan)
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="warning",
        access_log=False,
        timeout_graceful_shutdown=15,
    )
    process = uvicorn.Server(config)
    config.app = ProtectedApp(app, settings, process, secrets.token_hex(16))
    with resource_session(registry):
        process.run()
