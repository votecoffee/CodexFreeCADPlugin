import asyncio
import json
import sys

from mcp import Client

from codex_freecad.extension_runtime import Registry
from codex_freecad.host_catalog import installation_catalog
from codex_freecad.host_config import WRITE_TOOLS
from codex_freecad.server import create_server


def test_installation_catalog_never_imports_extension_code_or_native_backend(tmp_path):
    root = tmp_path / "extensions"
    extension = root / "example"
    extension.mkdir(parents=True)
    (extension / "__init__.py").write_text(
        'raise RuntimeError("Must never execute during metadata")'
    )
    (extension / "manifest.json").write_text(
        json.dumps(
            {
                "id": "example",
                "version": "1.0.0",
                "api_version": 1,
                "description": "example",
                "ui": False,
                "capabilities": {
                    "inspect": {
                        "kind": "query",
                        "description": "Inspect example",
                        "handler": "inspect",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    }
                },
            }
        )
    )
    before = set(sys.modules)
    result = installation_catalog([root])
    assert "FreeCAD" not in set(sys.modules) - before
    assert not any(name.startswith("_codex_cad_extension_") for name in set(sys.modules) - before)
    assert next(c for c in result["capabilities"] if c["id"] == "example.inspect")["discovery"] == {
        "tool": "describe_capability",
        "arguments": {"capability": "example.inspect"},
    }
    (extension / "__init__.py").write_text('raise RuntimeError("Changed installed code")')
    assert installation_catalog([root])["catalog_revision"] != result["catalog_revision"]


def test_installation_and_native_catalog_revisions_match_for_same_sources():
    registry = Registry()
    try:
        catalog = installation_catalog()
        assert catalog["catalog_revision"] == registry.catalog()["catalog_revision"]
        assert {c["id"] for c in catalog["capabilities"]} == {
            c["name"] for c in registry.catalog()["capabilities"]
        }
    finally:
        registry.active.close()


def test_app_host_adds_readonly_metadata_and_keeps_direct_schemas():
    class NoNativeCalls:
        def call(self, *args, **kwargs):
            raise AssertionError("Discovery contacted a native backend")

        def close(self):
            pass

    async def run():
        async with Client(create_server(NoNativeCalls())) as direct:
            baseline = (await direct.list_tools()).tools
            assert len(baseline) == 25
        async with Client(create_server(NoNativeCalls(), framework_backend=True)) as host:
            tools = (await host.list_tools()).tools
            assert len(tools) == 26
            assert [t.model_dump() for t in tools if t.name not in {"list_host_capabilities"}] == [
                t.model_dump() for t in baseline
            ]
            provider = next(t for t in tools if t.name == "list_host_capabilities")
            assert provider.annotations.read_only_hint is True
            catalog = await host.call_tool("list_host_capabilities", {})
            assert not catalog.is_error
            contents = catalog.structured_content or json.loads(catalog.content[0].text)
            assert contents["schema_version"] == 1
            assert {t.name for t in tools if t.annotations.read_only_hint is not True} == set(
                WRITE_TOOLS
            )

    asyncio.run(run())
