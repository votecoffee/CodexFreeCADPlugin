"""Prepare an explicit hash-bound native candidate without installation or execution."""

import argparse
import hashlib
import json
from pathlib import Path

from .framework_setup import atomic_json
from .offline_setup import generate as generate_offline


def generate(
    workspace,
    output,
    runtime,
    *,
    native_target,
    mode="headless",
    python=None,
    state=None,
    registry=None,
):
    if mode not in {"headless", "live"}:
        raise ValueError("Select headless modeling or an explicit existing live bridge")
    target = Path(native_target).resolve(strict=True)
    if (mode == "headless" and target.name.lower() != "freecadcmd.exe") or (
        mode == "live" and target.suffix.lower() != ".json"
    ):
        raise ValueError("Bind FreeCADCmd.exe or an explicit live bridge JSON descriptor")
    with target.open("rb") as stream:
        target_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    runtime = Path(runtime).resolve(strict=True)
    for name in ("native.py", "native_session.py", "guidance/native.md"):
        if not (runtime / "codex_freecad" / name).is_file():
            raise ValueError("Native runtime closure is incomplete")
    result = generate_offline(
        workspace, output, runtime, python=python, state=state, registry=registry
    )
    output = Path(output).resolve()
    state = Path(state or output / "state").absolute()
    launcher = output / "offline-launch.py"
    text = launcher.read_text(encoding="utf-8")
    guard = "with root_lifetime(" + repr(str(state)) + "):"
    if text.count(guard) != 1 or text.count("from codex_freecad.offline import main") != 1:
        raise ValueError("Generated bootstrap differs from the reviewed native entry template")
    text = text.replace(
        "with root_lifetime(" + repr(str(state)) + "):",
        "with root_lifetime(" + repr(str(state)) + ", process_limit=4):",
    )
    text = text.replace(
        "from codex_freecad.offline import main", "from codex_freecad.native import main"
    )
    native_launcher = output / "native-launch.py"
    native_launcher.write_text(text, encoding="utf-8", newline="\n")
    launcher.unlink()  # Only this fresh generated file; installed candidates never touched.
    plugin = output / "plugin"
    config = json.loads((plugin / ".mcp.json").read_bytes())
    server = config["mcpServers"]["freecad"]
    server["args"][3] = str(native_launcher)
    server["args"] += [
        "--mode",
        mode,
        "--native-target",
        str(target),
        "--expected-target-sha256",
        target_hash,
    ]
    atomic_json(plugin / ".mcp.json", config)
    manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_bytes())
    manifest["description"] = (
        "Standalone FreeCAD native profile with inspected targets and durable receipts"
    )
    manifest["interface"]["displayName"] = "FreeCADMCPServer (native)"
    manifest["interface"]["shortDescription"] = "Native modeling with reviewed targets"
    atomic_json(plugin / ".codex-plugin/plugin.json", manifest)
    offline_skill = plugin / "skills/freecad-offline/SKILL.md"
    offline_skill.unlink()
    skill = plugin / "skills/freecad-modeling/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes((runtime / "codex_freecad/standalone_skill.md").read_bytes())
    result.update(
        profile="direct-standalone-native",
        mode=mode,
        native_execution=True,
        native_target=str(target),
        native_target_sha256=target_hash,
        launcher_sha256=hashlib.sha256(native_launcher.read_bytes()).hexdigest(),
        installed=False,
        started=False,
    )
    atomic_json(output / "candidate.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("workspace", "output", "runtime", "native-target"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--mode", choices=["headless", "live"], default="headless")
    args = parser.parse_args()
    print(
        json.dumps(
            generate(
                args.workspace,
                args.output,
                args.runtime,
                native_target=args.native_target,
                mode=args.mode,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
