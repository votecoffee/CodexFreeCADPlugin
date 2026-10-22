"""Exercise app-owned startup and reconnect without allowing native CAD dispatch."""

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from universal_tools.cli import probe
from universal_tools.models import load_settings


def run(command, *, success=True):
    result = subprocess.run(command, capture_output=True, timeout=50)
    assert (result.returncode == 0) == success, result.stderr.decode(errors="replace")
    return result


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def connect(command):
    async with Client(
        StdioServerParameters(
            command=command[0], args=command[1:], env={"PYTHONPATH": os.environ["PYTHONPATH"]}
        )
    ) as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 14


def exercise(args):
    os.environ["PYTHONPATH"] = str(args.host_source)
    sys.path.insert(0, str(args.backend_source.parent))
    from codex_freecad.framework_setup import publish

    source = args.root / "source/codex_freecad"
    shutil.copytree(args.backend_source, source, ignore=shutil.ignore_patterns("__pycache__"))
    marker = args.root / "native-dispatch-forbidden.txt"
    with (source / "client.py").open("a") as stream:
        stream.write(
            "\ndef _forbidden(*args, **kwargs):\n"
            f"    Path({str(marker)!r}).write_text('unexpected native dispatch')\n"
            "    raise AssertionError('Native dispatch forbidden')\n"
            "HeadlessClient._start = LiveClient.call = _forbidden\n"
        )
    result = publish(
        args.root / "models",
        args.root / "installation",
        sys.executable,
        backend_python=args.backend_python,
        source_package=source,
        installed=True,
    )
    state = Path(result["state"])
    base = [
        sys.executable,
        "-m",
        "freecad_mcp_host",
        "--state",
        str(state),
        "--publication",
        result["publication"],
        "--management-registry",
        str(args.root / "management-registry"),
    ]
    run([*base, "init", "--port", str(free_port())])
    settings = load_settings(state)
    try:
        # Two independent frontends must converge on one authenticated app server.
        processes = [
            subprocess.Popen([*base, "start"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            for _ in range(2)
        ]
        for process in processes:
            _, error = process.communicate(timeout=50)
            assert process.returncode == 0, error.decode(errors="replace")
        first = probe(settings)
        assert first
        run([*base, "doctor"])
        run([*base, "check-idle"])
        publication = Path(result["publication"])
        original = publication.read_bytes()
        pending = json.loads(original)
        pending["backends"][0]["revision"] = "f" * 64
        publication.write_text(json.dumps(pending))
        rejected = run([*base, "doctor"], success=False)
        assert b"Live backend publication differs" in rejected.stderr
        publication.write_bytes(original)
        run([*base, "start"])
        assert probe(settings) == first
        asyncio.run(connect([*base, "connect"]))
        assert probe(settings) == first
        original_marker = (state / "freecad-host.json").read_bytes()
        run([*base, "stop"])
        assert probe(settings) is None
        # The plugin command starts only the same app after reboot/explicit stop.
        asyncio.run(connect([*base, "connect"]))
        assert probe(settings) != first
        assert (state / "freecad-host.json").read_bytes() == original_marker
        (state / "freecad-host.json").write_text("{}")
        rejected = run([*base, "start"], success=False)
        assert b"another application/publication" in rejected.stderr
        (state / "freecad-host.json").write_bytes(original_marker)
    finally:
        run([*base, "stop"])
    # An occupied non-HTTP port must not cause a fallback or process termination.
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", settings.port))
        occupied.listen()
        rejected = run([*base, "start"], success=False)
        assert b"port is occupied" in rejected.stderr
    assert not marker.exists()
    (args.root / "lifecycle.json").write_text(
        json.dumps(
            {
                "concurrent_start": True,
                "reconnect": True,
                "app_identity_guard": True,
                "occupied_port_preserved": True,
                "native_dispatches": 0,
            },
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--host-source", type=Path, required=True)
    parser.add_argument("--backend-source", type=Path, required=True)
    parser.add_argument("--backend-python", required=True)
    exercise(parser.parse_args())


if __name__ == "__main__":
    main()
