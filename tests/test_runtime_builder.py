"""Reviewed wheel extraction refuses changed or escaping bytes before publication."""

import base64
import csv
import hashlib
import io
import zipfile

import pytest

from codex_freecad.runtime_builder import extract_wheel, wheel_files


def wheel(tmp_path, *, member="fixture/code.py", wrong_record=False):
    path = tmp_path / "fixture.whl"
    data = b"# Harmless fixture, never imported\n"
    record = "fixture-1.dist-info/RECORD"
    rows = [
        [
            member,
            "sha256="
            + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode(),
            str(len(data)),
        ],
        [record, "", ""],
    ]
    if wrong_record:
        rows[0][2] = "999"
    text = io.StringIO(newline="")
    csv.writer(text).writerows(rows)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, data)
        archive.writestr(record, text.getvalue())
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_record_and_existing_runtime_bytes_are_preserved(tmp_path):
    path, expected = wheel(tmp_path)
    output = tmp_path / "runtime"
    extract_wheel(path, expected, output)
    assert (output / "fixture/code.py").read_bytes() == b"# Harmless fixture, never imported\n"
    (output / "fixture/code.py").write_bytes(b"existing different bytes")
    with pytest.raises(ValueError, match="Conflicting"):
        extract_wheel(path, expected, output)
    assert (output / "fixture/code.py").read_bytes() == b"existing different bytes"


@pytest.mark.parametrize(
    "member", ["../escape.py", "/absolute.py", "C:/drive.py", "folder\\backslash.py"]
)
def test_escaping_member_is_refused_before_extraction(tmp_path, member):
    path, expected = wheel(tmp_path, member=member)
    output = tmp_path / "runtime"
    with pytest.raises(ValueError, match="Unsafe|RECORD"):
        extract_wheel(path, expected, output)
    assert not output.exists()


def test_unreviewed_archive_and_bad_record_are_rejected(tmp_path):
    path, expected = wheel(tmp_path, wrong_record=True)
    with pytest.raises(ValueError, match="RECORD bytes"):
        wheel_files(path, expected)
    with pytest.raises(ValueError, match="reviewed SHA"):
        wheel_files(path, "0" * 64)
