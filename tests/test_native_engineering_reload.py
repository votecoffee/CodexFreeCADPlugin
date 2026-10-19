import asyncio
import json
import shutil
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from test_mcp import data

import codex_freecad
from codex_freecad.client import HeadlessClient, find_freecad_cmd

pytestmark = pytest.mark.native


def test_engineering_extensions_load_and_recover_in_one_existing_mcp_connection(tmp_path):
    root = tmp_path / "extensions"
    root.mkdir()
    workspace = tmp_path / "models"

    async def run():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "codex_freecad.server",
                "--mode",
                "headless",
                "--workspace",
                str(workspace),
                "--extensions",
                str(root),
            ],
        )
        async with Client(parameters, read_timeout_seconds=90) as client:

            async def call(method, **arguments):
                return data(await client.call_tool(method, arguments))

            async def edit(*operations):
                return await call("apply_operations", document="Model", operations=list(operations))

            def extension(capability, **arguments):
                return {
                    "op": "extension",
                    "capability": "installed_" + capability,
                    "arguments": arguments,
                }

            async def query(capability, **arguments):
                return (
                    await call(
                        "run_query",
                        document="Model",
                        capability="installed_" + capability,
                        arguments=arguments,
                    )
                )["result"]

            tools = (await client.list_tools()).model_dump(mode="json")
            pid = (await call("freecad_status"))["backend_pid"]
            await call("new_document", name="Model")
            await edit(
                {"op": "create_box", "name": "Block", "length": 40, "width": 30, "height": 10}
            )
            before = (await call("inspect_document", document="Model"))["revision"]
            source = Path(codex_freecad.__file__).parent / "extensions"
            for name in ("bom", "studies", "drawings", "requirements"):
                target = root / ("installed_" + name)
                shutil.copytree(source / name, target, ignore=shutil.ignore_patterns("__pycache__"))
                manifest_path = target / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["id"] = "installed_" + name
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            loaded = await call("reload_extensions")
            assert loaded["changed_extensions"] == [
                "installed_bom",
                "installed_drawings",
                "installed_requirements",
                "installed_studies",
            ]
            assert (await client.list_tools()).model_dump(mode="json") == tools
            assert (await call("freecad_status"))["backend_pid"] == pid
            assert (await call("inspect_document", document="Model"))["revision"] == before
            assert (await query("bom.inspect", objects=["Block"]))["quantity"] == 1
            study = await query(
                "studies.parameter_sweep",
                object="Block",
                property="Length",
                values=[20, 40],
                objects=["Block"],
            )
            assert [frame["total_volume_mm3"] for frame in study["frames"]] == pytest.approx(
                [6000, 12000]
            )
            preview_arguments = {
                "changes": [
                    {"object": "Block", "property": "Length", "value": 60},
                    {"object": "Block", "property": "Width", "value": 20},
                ],
                "objects": ["Block"],
            }
            preview = await query("studies.preview_changes", **preview_arguments)
            assert preview["objects"][0]["added_volume_mm3"] == pytest.approx(4000)
            assert preview["objects"][0]["removed_volume_mm3"] == pytest.approx(4000)
            assert (await call("inspect_document", document="Model"))["revision"] == before
            helper = root / "installed_studies/preview.py"
            helper_source = helper.read_text(encoding="utf-8")
            helper.write_text(helper_source + "\n# helper generation update\n", encoding="utf-8")
            assert (await call("reload_extensions"))["changed_extensions"] == ["installed_studies"]
            assert await query("studies.preview_changes", **preview_arguments) == preview
            catalog = (await call("list_capabilities"))["catalog_revision"]
            helper.write_text("def invalid(:\n", encoding="utf-8")
            assert (await client.call_tool("reload_extensions", {})).is_error
            assert (await call("list_capabilities"))["catalog_revision"] == catalog
            assert await query("studies.preview_changes", **preview_arguments) == preview
            helper.write_text(helper_source, encoding="utf-8")
            await call("reload_extensions")
            await edit(
                extension("bom.create_sheet", name="BOM", objects=["Block"]),
                extension("drawings.create_sheet", name="Drawing", objects=["Block"]),
                extension(
                    "studies.create_variants",
                    name="Variants",
                    object="Block",
                    property="Length",
                    values=[20],
                    objects=["Block"],
                ),
                extension(
                    "requirements.create_set",
                    name="Limits",
                    rules=[
                        {"id": "Volume", "metric": "volume", "object": "Block", "maximum": 15000},
                        {
                            "id": "Length",
                            "metric": "property",
                            "object": "Block",
                            "property": "Length",
                            "maximum": 45,
                        },
                    ],
                ),
            )
            limits = await query("requirements.evaluate", set="Limits")
            assert limits["all_passed"]
            guarded = await query(
                "studies.preview_changes", **preview_arguments, requirement_sets=["Limits"]
            )
            assert not guarded["requirements"]["all_passed_after"]
            baseline = (await call("inspect_document", document="Model"))["revision"]
            assert (await client.call_tool("apply_operations", guarded["apply_arguments"])).is_error
            assert (await call("inspect_document", document="Model"))["revision"] == baseline
            passing_guarded = await query(
                "studies.preview_changes",
                objects=["Block"],
                requirement_sets=["Limits"],
                changes=[{"object": "Block", "property": "Length", "value": 42}],
            )
            assert passing_guarded["requirements"]["all_passed_after"]
            rule_helper = root / "installed_requirements/rules.py"
            rule_source = rule_helper.read_text(encoding="utf-8")
            rule_helper.write_text(rule_source + "\n# rule helper update\n", encoding="utf-8")
            assert (await call("reload_extensions"))["changed_extensions"] == [
                "installed_requirements"
            ]
            assert await query("requirements.evaluate", set="Limits") == limits
            stale = await client.call_tool("apply_operations", passing_guarded["apply_arguments"])
            assert stale.is_error
            assert (await call("inspect_document", document="Model"))["revision"] == baseline
            catalog = (await call("list_capabilities"))["catalog_revision"]
            rule_helper.write_text("def invalid(:\n", encoding="utf-8")
            assert (await client.call_tool("reload_extensions", {})).is_error
            assert (await call("list_capabilities"))["catalog_revision"] == catalog
            assert await query("requirements.evaluate", set="Limits") == limits
            rule_helper.write_text(rule_source, encoding="utf-8")
            await call("reload_extensions")
            rendered = await query("drawings.render_svg", page="Drawing")
            assert rendered["views"][0]["width_mm"] == pytest.approx(40)
            await call("save_document", document="Model", path="Engineering.FCStd")
            # The external extension packages are absent in this fresh native worker.
            with HeadlessClient(workspace, find_freecad_cmd()) as other:
                name = other.call("open_document", path="Engineering.FCStd")["name"]
                assert other.call(
                    "run_query",
                    document=name,
                    capability="requirements.evaluate",
                    arguments={"set": "Limits"},
                )["result"]["all_passed"]
                assert other.call("inspect_object", document=name, object_name="Variants_001_01")[
                    "shape"
                ]["volume_mm3"] == pytest.approx(6000)
                other.call(
                    "apply_operations",
                    document=name,
                    operations=[
                        {
                            "op": "extension",
                            "capability": "drawings.refresh_sheet",
                            "arguments": {"page": "Drawing"},
                        }
                    ],
                )
            revision = (await call("inspect_document", document="Model"))["revision"]
            module = root / "installed_drawings/__init__.py"
            working = module.read_text(encoding="utf-8")
            module.write_text(working + "\n# candidate generation update\n", encoding="utf-8")
            assert (await call("reload_extensions"))["changed_extensions"] == ["installed_drawings"]
            assert (await query("drawings.render_svg", page="Drawing"))["svg"] == rendered["svg"]
            assert (await call("inspect_document", document="Model"))["revision"] == revision
            catalog = (await call("list_capabilities"))["catalog_revision"]
            module.write_text("def invalid(:\n", encoding="utf-8")
            assert (await client.call_tool("reload_extensions", {})).is_error
            assert (await call("list_capabilities"))["catalog_revision"] == catalog
            assert (await query("drawings.render_svg", page="Drawing"))["svg"] == rendered["svg"]
            await call("undo_document", document="Model")
            assert (await call("inspect_document", document="Model"))["revision"] == before
            await call("undo_document", document="Model")
            assert (await call("inspect_document", document="Model"))["objects"] == []
            assert (await call("freecad_status"))["backend_pid"] == pid
            assert (await client.list_tools()).model_dump(mode="json") == tools

    asyncio.run(run())
