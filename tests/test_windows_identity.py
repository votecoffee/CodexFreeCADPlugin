"""OS image-file identities; no app launch, attachment, or process termination."""

import ctypes
import os
import shutil
from ctypes import wintypes as w

import pytest

pytest.importorskip("universal_tools.windows_resources")

from codex_freecad.windows_identity import AppProcessDriver


@pytest.mark.skipif(os.name != "nt", reason="Windows process handle")
def test_logical_physical_file_alias_is_alive_but_copied_image_and_reused_generation_are_not(
    tmp_path,
):
    driver = AppProcessDriver()
    current = driver.capture(os.getpid())
    alias = tmp_path / "logical-image.exe"
    try:
        os.link(current["executable"], alias)
    except OSError as exc:
        pytest.skip(f"Hardlink fixture unavailable: {exc}")
    identity = {**current, "executable": str(alias)}
    assert driver.state(identity) == "alive"
    copied = tmp_path / "copied-image.exe"
    shutil.copyfile(current["executable"], copied)
    assert driver.state({**current, "executable": str(copied)}) == "unknown"
    assert driver.state({**identity, "created": str(int(current["created"]) + 1)}) == "different"
    # Alias-aware observations do not broaden the framework's termination rights.
    with pytest.raises(ProcessLookupError):
        driver.open(identity)


@pytest.mark.skipif(os.name != "nt", reason="Windows native image namespace")
def test_native_physical_image_namespace_matches_the_same_live_generation():
    driver = AppProcessDriver()
    current = driver.capture(os.getpid())
    with driver._open(current["pid"]) as held:
        size = w.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        assert driver.kernel.QueryFullProcessImageNameW(held.handle, 1, image, ctypes.byref(size))
        physical = "\\\\?\\GLOBALROOT" + image.value
        assert os.path.samefile(current["executable"], physical)
        assert driver.state({**current, "executable": physical}) == "alive"
