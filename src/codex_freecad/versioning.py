"""Fixed release identities. No clock is read at application startup."""

import argparse
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import __version__


def canonical_version(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("Expected three numeric version components")
    return ".".join(str(int(part)) for part in value.split("."))


def version_key(value):
    return tuple(map(int, canonical_version(value).split(".")))


def same_version(left, right):
    return version_key(left) == version_key(right)


def timestamp_forms(display):
    if not re.fullmatch(r"[0-9]{2}\.[0-9]{4}\.[0-9]{6}", display):
        raise ValueError("Expected YY.MMDD.HHmmss with full padding")
    year, month_day, clock = display.split(".")
    local = datetime(
        2000 + int(year),
        int(month_day[:2]),
        int(month_day[2:]),
        int(clock[:2]),
        int(clock[2:4]),
        int(clock[4:]),
    )
    return {
        "display_version": display,
        "package_version": canonical_version(display),
        "assembly_file_version": ".".join(
            map(str, (int(year), int(month_day), int(clock[:4]), local.second))
        ),
    }


def release_from_utc(value):
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0) or instant.microsecond:
        raise ValueError("Supply one explicit UTC instant at whole-second precision")
    local = instant.astimezone(ZoneInfo("America/New_York"))
    if not 2000 <= local.year <= 2099:
        raise ValueError("Two-digit release years are defined only for 2000 through 2099")
    forms = timestamp_forms(local.strftime("%y.%m%d.%H%M%S"))
    return {
        "schema_version": 1,
        "application_id": "freecad-mcp-server",
        **forms,
        "timezone": "America/New_York",
        "stamped_at": local.isoformat(),
        "stamped_utc": instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def apply_mcp_identity(server):
    # MCP 2.3's public version property reads this pinned low-level server field.
    # The framework's own package/protocol version stays independent.
    server._lowlevel_server.version = __version__
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", required=True)
    args = parser.parse_args()
    print(canonical_version(args.canonical))


if __name__ == "__main__":
    main()
