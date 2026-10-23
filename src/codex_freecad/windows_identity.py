"""App-owned identity observations without changing the reviewed framework pin."""

import os

from universal_tools.windows_resources import ProcessDriver


def same_image(left, right):
    """An OS file identity proves aliases; equal bytes or basenames never suffice."""
    try:
        return os.path.samefile(left, right)
    except (OSError, ValueError):
        return False


class AppProcessDriver(ProcessDriver):
    def state(self, identity):
        observed = super().state(identity)
        if observed != "unknown" or identity.get("host_id") != self.host_id:
            return observed
        # MSIX logical/physical paths may describe one image. Pin the process
        # handle, host and creation time again, then require actual file identity.
        # The framework's strict termination/open policy remains unchanged.
        try:
            with self._open(identity["pid"]) as handle:
                if not handle.alive():
                    return "absent"
                current = handle.identity
                if current["created"] != identity["created"]:
                    return "different"
                if same_image(current["executable"], identity["executable"]):
                    return "alive" if handle.alive() else "absent"
        except ProcessLookupError:
            return "absent"
        except (OSError, ValueError, KeyError):
            pass
        return "unknown"
