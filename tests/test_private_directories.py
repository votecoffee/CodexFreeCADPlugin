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

    monkeypatch.setattr(private_directories, "_create_private", forbidden)
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


def test_existing_foreign_dacl_is_not_repaired_on_first_use(tmp_path, monkeypatch):
    path = tmp_path / "untrusted"
    path.mkdir()
    if os.name != "nt":
        path.chmod(0o755)
    before = path.lstat()

    def forbidden(path):
        pytest.fail("Existing foreign ACL was reset")

    monkeypatch.setattr(private_directories, "_create_private", forbidden)
    with pytest.raises(PermissionError, match="Foreign metadata directory"):
        private_directories.ensure_private(path)
    assert path.lstat().st_ino == before.st_ino


def test_foreign_owner_is_refused_without_takeover(tmp_path, monkeypatch):
    path = tmp_path / "foreign-owner-view"
    private_directory(path)
    if os.name == "nt":
        import win32security

        getter = win32security.GetNamedSecurityInfo

        class ForeignOwner:
            def __init__(self, descriptor):
                self.descriptor = descriptor

            def GetSecurityDescriptorOwner(self):
                return win32security.CreateWellKnownSid(win32security.WinWorldSid)

            def GetSecurityDescriptorDacl(self):
                return self.descriptor.GetSecurityDescriptorDacl()

            def GetSecurityDescriptorControl(self):
                return self.descriptor.GetSecurityDescriptorControl()

        monkeypatch.setattr(
            win32security, "GetNamedSecurityInfo", lambda *args: ForeignOwner(getter(*args))
        )
    else:
        monkeypatch.setattr(os, "geteuid", lambda: path.stat().st_uid + 1)

    def forbidden(path):
        pytest.fail("Foreign owner was repaired or taken over")

    monkeypatch.setattr(private_directories, "_create_private", forbidden)
    with pytest.raises(PermissionError, match="Foreign metadata directory"):
        private_directories.ensure_private(path)


def test_initial_reparse_observation_refuses_before_any_policy_write(tmp_path, monkeypatch):
    path = tmp_path / "reparse-view"
    private_directory(path)
    original = type(path).is_symlink
    monkeypatch.setattr(type(path), "is_symlink", lambda p: p == path or original(p))
    monkeypatch.setattr(
        private_directories, "_create_private", lambda p: pytest.fail("Reparse path repaired")
    )
    with pytest.raises(ValueError, match="ordinary directory"):
        private_directories.ensure_private(path)


def test_create_to_first_pin_replacement_keeps_foreign_dacl_and_payload(tmp_path, monkeypatch):
    target, retained, foreign = (tmp_path / name for name in ("target", "retained", "foreign"))
    foreign.mkdir()
    payload = foreign / "evidence.txt"
    payload.write_bytes(b"Foreign fixture evidence must remain unchanged")
    if os.name != "nt":
        foreign.chmod(0o755)
        before_policy = foreign.stat().st_mode
    else:
        import win32security

        def policy(path):
            descriptor = win32security.GetNamedSecurityInfo(
                str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
            )
            return win32security.ConvertSecurityDescriptorToStringSecurityDescriptor(
                descriptor, win32security.SDDL_REVISION_1, win32security.DACL_SECURITY_INFORMATION
            )

        before_policy = policy(foreign)
    before_identity = (foreign.stat().st_dev, foreign.stat().st_ino)
    create = private_directories._create_private

    def swapped(path):
        create(path)  # Private ACL exists from the kernel creation call.
        assert path.resolve().is_relative_to(tmp_path.resolve())
        assert retained.absolute().parent == path.absolute().parent
        path.rename(retained)  # Only this test's newly created empty directory.
        foreign.rename(path)  # Inject a different preexisting object before the first pin.

    monkeypatch.setattr(private_directories, "_create_private", swapped)
    if os.name == "nt":
        monkeypatch.setattr(
            win32security,
            "SetNamedSecurityInfo",
            lambda *args: pytest.fail("Replacement ACL reset"),
        )
    with pytest.raises(PermissionError, match="Foreign metadata directory"):
        private_directories.ensure_private(target)
    assert (target.stat().st_dev, target.stat().st_ino) == before_identity
    assert (
        target / "evidence.txt"
    ).read_bytes() == b"Foreign fixture evidence must remain unchanged"
    assert (policy(target) if os.name == "nt" else target.stat().st_mode) == before_policy
    assert retained.is_dir()
