"""Native tests must never publish resource records into the user's manager registry."""

import sys

import pytest


@pytest.fixture(autouse=True)
def isolated_native_resource_owner(request, tmp_path):
    if request.node.get_closest_marker("native") is None:
        yield
        return
    if sys.platform != "win32":
        pytest.skip("Managed native process acceptance currently targets Windows")
    pytest.importorskip("universal_tools.resources")
    from codex_freecad.resource_ownership import resource_session

    with resource_session(tmp_path / "management-registry"):
        yield
