"""Validate pinned private metadata directories without repeatedly rewriting child ACLs."""

import os
import stat
import threading
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
        policy = stat.S_IMODE(before.st_mode)
        valid = policy == 0o700
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
            str(path), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION
        )
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
        policy = (protected, frozenset(entries))
        valid = protected and len(entries) == 2 and set(entries) == expected
    after = path.lstat()
    if (after.st_dev, after.st_ino) != identity or getattr(after, "st_file_attributes", 0) & 0x400:
        raise ValueError("Private metadata directory changed during inspection")
    return (identity, policy), valid


def ensure_private(path):
    """Apply original framework policy at first preparation only; later drift refuses."""
    path = Path(path).absolute()
    with _mutex:
        if path in _pins:
            current, valid = _read(path)
            if not valid or current != _pins[path]:
                raise PermissionError("Private metadata directory identity or permissions changed")
            return
        if not path.exists():
            private_directory(path)
        current, valid = _read(path)
        if not valid:
            private_directory(path)  # Original framework preparation, not an operation replay.
            current, valid = _read(path)
        if not valid:
            raise PermissionError("Cannot verify private metadata directory policy")
        _pins[path] = current
