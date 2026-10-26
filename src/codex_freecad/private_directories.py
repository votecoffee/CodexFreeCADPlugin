"""Validate pinned private metadata directories without repeatedly rewriting child ACLs."""

import os
import stat
import threading
import uuid
from pathlib import Path

from universal_tools.management import private_directory

_pins = {}
_mutex = threading.RLock()
_user_sid = None


def _read(path):
    before = path.lstat()
    if (
        not stat.S_ISDIR(before.st_mode)
        or path.is_symlink()
        or getattr(before, "st_file_attributes", 0) & 0x400
    ):
        raise ValueError("Private metadata directory must be an ordinary directory")
    identity = (before.st_dev, before.st_ino)
    if os.name != "nt":
        policy = (before.st_uid, stat.S_IMODE(before.st_mode))
        valid = policy == (os.geteuid(), 0o700)
    else:
        import ntsecuritycon
        import win32api
        import win32con
        import win32security

        global _user_sid
        if _user_sid is None:
            token = win32security.OpenProcessToken(
                win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
            )
            try:
                _user_sid = win32security.ConvertSidToStringSid(
                    win32security.GetTokenInformation(token, win32security.TokenUser)[0]
                )
            finally:
                token.Close()
        descriptor = win32security.GetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION | win32security.OWNER_SECURITY_INFORMATION,
        )
        owner = win32security.ConvertSidToStringSid(descriptor.GetSecurityDescriptorOwner())
        acl = descriptor.GetSecurityDescriptorDacl()
        protected = bool(descriptor.GetSecurityDescriptorControl()[0] & 0x1000)
        entries = []
        if acl is not None:
            for index in range(acl.GetAceCount()):
                ace = acl.GetAce(index)
                if len(ace) != 3:
                    entries.append(("unsupported-ace", index))
                    continue
                (kind, flags), mask, sid = ace
                entries.append((kind, flags, mask, win32security.ConvertSidToStringSid(sid)))
        flags = win32con.OBJECT_INHERIT_ACE | win32con.CONTAINER_INHERIT_ACE
        expected = {
            (0, flags, ntsecuritycon.FILE_ALL_ACCESS, _user_sid),
            (0, flags, ntsecuritycon.FILE_ALL_ACCESS, "S-1-5-18"),
        }
        policy = (owner, protected, frozenset(entries))
        valid = owner == _user_sid and protected and len(entries) == 2 and set(entries) == expected
    after = path.lstat()
    if (after.st_dev, after.st_ino) != identity or getattr(after, "st_file_attributes", 0) & 0x400:
        raise ValueError("Private metadata directory changed during inspection")
    return (identity, policy), valid


def ensure_private(path):
    """Create new private directories; existing ownership/ACLs are never repaired."""
    path = Path(path).absolute()
    with _mutex:
        if path in _pins:
            current, valid = _read(path)
            if not valid or current != _pins[path]:
                raise PermissionError("Private metadata directory identity or permissions changed")
            return
        try:
            path.lstat()
        except FileNotFoundError:
            path.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                # Publish a secured EMPTY directory atomically. Other processes
                # never observe the intermediate inherited ACL as a valid target.
                stage = path.parent / (".freecad-private-" + uuid.uuid4().hex)
                stage.mkdir(exist_ok=False)
                private_directory(stage)  # Only the directory this call just created.
                _, valid = _read(stage)
                if not valid:
                    raise PermissionError(
                        "New metadata directory ownership/ACL is unavailable"
                    ) from None
                assert stage.parent.resolve() == path.parent.resolve()
                try:
                    stage.rename(path)  # Windows refuses an existing target; never replace it.
                except FileExistsError:
                    stage.rmdir()  # Only our still-empty, secured staging directory.
            else:
                try:
                    path.mkdir(mode=0o700)
                except FileExistsError:
                    pass  # Validate the winner; never replace or chmod it.
        current, valid = _read(path)
        if not valid:
            raise PermissionError(
                "Foreign metadata directory owner or ACL; existing state unchanged"
            )
        _pins[path] = current
