"""Actual directory-policy checks on disposable test folders only."""

import os

import pytest

private_directory = pytest.importorskip("universal_tools.management").private_directory
private_directories = pytest.importorskip("codex_freecad.private_directories")


def test_existing_private_directory_is_validated_without_acl_rewrites(tmp_path, monkeypatch):
    path = tmp_path / "private"
    private_directory(path)
    payload = path / "original.txt"
    payload.write_bytes(b"Preserved test evidence")

    def forbidden(path):
        pytest.fail("Already-private metadata directory was rewritten")

    monkeypatch.setattr(private_directories, "private_directory", forbidden)
    private_directories.ensure_private(path)
    private_directories.ensure_private(path)
    assert payload.read_bytes() == b"Preserved test evidence"


def test_replaced_directory_is_not_silently_repinned(tmp_path):
    path, retained = tmp_path / "private", tmp_path / "retained"
    private_directories.ensure_private(path)
    assert path.resolve().is_relative_to(tmp_path.resolve())
    path.rename(retained)
    private_directory(path)
    with pytest.raises(PermissionError, match="identity or permissions"):
        private_directories.ensure_private(path)
    assert retained.is_dir()


def test_permission_drift_is_refused_without_automatic_repair(tmp_path):
    path = tmp_path / "private"
    private_directories.ensure_private(path)
    if os.name == "nt":
        import ntsecuritycon
        import win32security

        descriptor = win32security.GetNamedSecurityInfo(
            str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
        )
        acl = descriptor.GetSecurityDescriptorDacl()
        acl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION_DS,
            0,
            ntsecuritycon.FILE_GENERIC_READ,
            win32security.CreateWellKnownSid(win32security.WinWorldSid),
        )
        win32security.SetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
        with pytest.raises(PermissionError, match="identity or permissions"):
            private_directories.ensure_private(path)
        assert (
            win32security.GetNamedSecurityInfo(
                str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
            )
            .GetSecurityDescriptorDacl()
            .GetAceCount()
            == 3
        )
    else:
        path.chmod(0o755)
        with pytest.raises(PermissionError, match="identity or permissions"):
            private_directories.ensure_private(path)
        assert path.stat().st_mode & 0o777 == 0o755
    private_directory(path)  # Restore only this test-created folder's original policy.
