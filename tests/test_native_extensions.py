import asyncio
import json
import math
import os
import sys

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from test_extensions import write_extension
from test_mcp import data

from codex_freecad.client import HeadlessClient, find_freecad_cmd
from codex_freecad.engine import CadError

pytestmark = pytest.mark.native


@pytest.fixture
def cad(tmp_path):
    try:
        command = find_freecad_cmd()
    except CadError:
        pytest.skip("Native FreeCADCmd is not installed")
    with HeadlessClient(tmp_path / "models", command) as client:
        client.call("new_document", name="Model")
        yield client


def tube(**arguments):
    return {
        "op": "extension",
        "capability": "parts.create_tube",
        "arguments": {
            "name": "Tube",
            "outer_radius": 10,
            "inner_radius": 6,
            "height": 20,
            **arguments,
        },
    }


def test_builtin_extension_native_geometry_query_undo_and_save_reopen(cad, tmp_path):
    described = cad.call("describe_capability", capability="parts.create_tube")
    operation = {**tube(), "catalog_revision": described["catalog_revision"]}
    cad.call("apply_operations", document="Model", operations=[operation])
    before = cad.call("inspect_document", document="Model")["revision"]
    query = cad.call(
        "run_query",
        document="Model",
        capability="parts.mass_properties",
        arguments={"object": "Tube", "density_kg_m3": 7800},
    )["result"]
    assert query["volume_mm3"] == pytest.approx(math.pi * 64 * 20)
    assert query["mass_kg"] == pytest.approx(math.pi * 64 * 20 * 7800e-9)
    assert query["center_of_mass_mm"] == pytest.approx([0, 0, 10])
    assert cad.call("inspect_document", document="Model")["revision"] == before
    cad.call("reload_extensions")  # Unchanged source is a no-op and keeps native Undo.
    cad.call("save_document", document="Model", path="Tube.FCStd")
    with HeadlessClient(tmp_path / "models", find_freecad_cmd()) as other:
        name = other.call("open_document", path="Tube.FCStd")["name"]
        shape = other.call("inspect_object", document=name, object_name="Tube")["shape"]
        assert shape["valid"] and shape["solids"] == 1
        assert shape["volume_mm3"] == pytest.approx(query["volume_mm3"])
    cad.call("undo_document", document="Model")
    assert cad.call("inspect_document", document="Model")["objects"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"height": -1},
        {"inner_radius": 11},
        {"height": True},
        {"name": "../escape"},
        {"script": "not a field"},
    ],
)
def test_extension_validation_rolls_back_entire_mixed_batch(cad, changes):
    with pytest.raises(CadError):
        cad.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Earlier", "length": 2, "width": 3, "height": 4},
                tube(**changes),
            ],
        )
    assert cad.call("inspect_document", document="Model")["objects"] == []
    cad.call("apply_operations", document="Model", operations=[tube()])
    assert cad.call("inspect_object", document="Model", object_name="Tube")["shape"]["valid"]


def test_query_mutation_is_rolled_back_and_read_write_kinds_stay_separate(tmp_path):
    root = tmp_path / "installed"
    write_extension(
        root, source="def answer(engine, doc, args):\n    doc.Box.Length = 99\n    return {}\n"
    )
    with HeadlessClient(tmp_path / "models", find_freecad_cmd(), extension_dirs=[root]) as cad:
        cad.call("new_document", name="Model")
        cad.call(
            "apply_operations",
            document="Model",
            operations=[
                {"op": "create_box", "name": "Box", "length": 10, "width": 10, "height": 10}
            ],
        )
        before = cad.call("inspect_document", document="Model")["revision"]
        with pytest.raises(CadError, match="Query handler changed"):
            cad.call("run_query", document="Model", capability="demo.answer", arguments={})
        assert cad.call("inspect_document", document="Model")["revision"] == before
        with pytest.raises(CadError, match="entry point"):
            cad.call("run_query", document="Model", capability="parts.create_tube", arguments={})
        cad.call("undo_document", document="Model")
        assert cad.call("inspect_document", document="Model")["objects"] == []


def test_existing_stdio_mcp_session_discovers_new_features_without_tool_schema_or_worker_restart(
    tmp_path,
):
    root = tmp_path / "installed"
    folder = write_extension(
        root,
        source="from .helper import VALUE\ndef answer(engine, doc, args):\n    return {'value': VALUE}\n",
    )
    helper = folder / "helper.py"
    helper.write_text("VALUE = 11\n")

    async def run():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "codex_freecad.server",
                "--mode",
                "headless",
                "--workspace",
                str(tmp_path / "models"),
                "--extensions",
                str(root),
            ],
        )
        async with Client(parameters, read_timeout_seconds=60) as client:
            tools_before = (await client.list_tools()).model_dump(mode="json")
            backend_pid = data(await client.call_tool("freecad_status", {}))["backend_pid"]
            await client.call_tool("new_document", {"name": "Model"})
            await client.call_tool(
                "apply_operations",
                {
                    "document": "Model",
                    "operations": [
                        {"op": "create_box", "name": "Keep", "length": 2, "width": 2, "height": 2}
                    ],
                },
            )
            before = data(await client.call_tool("inspect_document", {"document": "Model"}))
            described = data(
                await client.call_tool("describe_capability", {"capability": "demo.answer"})
            )

            async def query():
                return data(
                    await client.call_tool(
                        "run_query",
                        {"document": "Model", "capability": "demo.answer", "arguments": {}},
                    )
                )["result"]["value"]

            assert await query() == 11
            stamp = helper.stat()
            helper.write_text("VALUE = 22\n")
            os.utime(helper, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            manifest = json.loads((folder / "manifest.json").read_text())
            manifest["version"] = "1.1.0"
            manifest["capabilities"]["new_feature"] = {
                "kind": "edit",
                "description": "Added after MCP connected",
                "handler": "make_box",
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "side"],
                    "properties": {
                        "name": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]*$"},
                        "side": {"type": "number", "exclusiveMinimum": 0},
                    },
                },
            }
            (folder / "manifest.json").write_text(json.dumps(manifest))
            (folder / "__init__.py").write_text(
                (folder / "__init__.py").read_text()
                + "\ndef make_box(engine, doc, args):\n    return engine.operation(doc, {'op':'create_box', 'name':args['name'], 'length':args['side'], 'width':args['side'], 'height':args['side']})\n"
            )
            reloaded = data(await client.call_tool("reload_extensions", {}))
            assert reloaded["reloaded"] and reloaded["changed_extensions"] == ["demo"]
            assert await query() == 22
            assert data(await client.call_tool("freecad_status", {}))["backend_pid"] == backend_pid
            assert (
                data(await client.call_tool("inspect_document", {"document": "Model"}))["revision"]
                == before["revision"]
            )
            assert (await client.list_tools()).model_dump(mode="json") == tools_before
            stale = await client.call_tool(
                "run_query",
                {
                    "document": "Model",
                    "capability": "demo.answer",
                    "arguments": {},
                    "catalog_revision": described["catalog_revision"],
                },
            )
            assert stale.is_error
            new = data(
                await client.call_tool("describe_capability", {"capability": "demo.new_feature"})
            )
            created = data(
                await client.call_tool(
                    "apply_operations",
                    {
                        "document": "Model",
                        "operations": [
                            {
                                "op": "extension",
                                "capability": "demo.new_feature",
                                "arguments": {"name": "NewBox", "side": 3},
                                "catalog_revision": new["catalog_revision"],
                            }
                        ],
                    },
                )
            )
            assert created["document"]["objects"][-1]["shape"]["volume_mm3"] == pytest.approx(27)
            data(
                await client.call_tool(
                    "save_document", {"document": "Model", "path": "Reloaded.FCStd"}
                )
            )
            # An external extension's ordinary native output survives without that extension installed.
            with HeadlessClient(tmp_path / "models", find_freecad_cmd()) as other:
                name = other.call("open_document", path="Reloaded.FCStd")["name"]
                assert other.call("inspect_object", document=name, object_name="NewBox")["shape"][
                    "volume_mm3"
                ] == pytest.approx(27)
            await client.call_tool("undo_document", {"document": "Model"})
            assert (
                data(await client.call_tool("inspect_document", {"document": "Model"}))["revision"]
                == before["revision"]
            )
            (folder / "__init__.py").write_text("def broken(:\n")
            assert (await client.call_tool("reload_extensions", {})).is_error
            assert await query() == 22
            # Original model and its previous Undo entry survive successful and failed reloads.
            await client.call_tool("undo_document", {"document": "Model"})
            assert (
                data(await client.call_tool("inspect_document", {"document": "Model"}))["objects"]
                == []
            )

    asyncio.run(run())


def test_generation_owned_python_proxies_cannot_leak_into_saved_features(tmp_path):
    root = tmp_path / "installed"
    folder = write_extension(
        root,
        source="class Transient:\n    pass\ndef answer(engine, doc, args):\n    obj=doc.addObject('App::FeaturePython','TransientFeature')\n    obj.Proxy=Transient()\n    return {}\n",
    )
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["capabilities"]["answer"]["kind"] = "edit"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with HeadlessClient(tmp_path / "models", find_freecad_cmd(), extension_dirs=[root]) as cad:
        cad.call("new_document", name="Model")
        with pytest.raises(CadError, match="persistent native objects"):
            cad.call(
                "apply_operations",
                document="Model",
                operations=[{"op": "extension", "capability": "demo.answer", "arguments": {}}],
            )
        assert cad.call("inspect_document", document="Model")["objects"] == []
