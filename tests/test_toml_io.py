"""Disposable byte-level config fixtures; never read or write the user's Codex home."""

import io
import os
import tomllib

import pytest

from codex_freecad.setup import generate
from codex_freecad.toml_io import BOM, encode_toml

FIXTURE = (
    '''# Unicode and literal newlines are intentional.
name = "Café Ω"
instructions = """Preserve this value.
[marketplaces.example]
source = 'a header inside a multiline string'
"""
literal = '''
    + "'''"
    + """First line
第二行
"""
    + "'''"
    + """
[marketplaces.freecad-development]
source = 'C:\\CAD models\\old'
[plugins."another-plugin@example"]
enabled = true
"""
)


@pytest.mark.parametrize("input_newline", ["\n", "\r\n"])
@pytest.mark.parametrize("output_newline", ["\n", "\r\n"])
def test_utf8_publication_has_exact_bytes_and_preserves_settings(
    tmp_path, input_newline, output_newline
):
    original = FIXTURE.replace("\n", input_newline).encode("utf-8")
    before = tomllib.loads(original.decode("utf-8"))
    updated = original.decode("utf-8").replace("C:\\CAD models\\old", "D:\\Models Ω\\new")
    output = encode_toml(updated, newline=output_newline)
    path = tmp_path / "Config Ω with spaces.toml"
    path.write_bytes(output)
    assert path.read_bytes() == updated.replace("\r\n", "\n").replace("\n", output_newline).encode(
        "utf-8"
    )
    assert b"\r\r\n" not in output and b"\r" not in output.replace(b"\r\n", b"")
    assert not output.startswith(b"\xef\xbb\xbf")
    after = tomllib.loads(output.decode("utf-8"))
    assert after["marketplaces"]["freecad-development"]["source"] == "D:\\Models Ω\\new"
    after["marketplaces"] = before["marketplaces"]
    assert after == before  # Unrelated plugins, Unicode and multiline values preserved.


@pytest.mark.parametrize("broken", ["name = 'x'\r", "name = 'x'\r\r\n", "name = 'x'\rx = 1"])
def test_malformed_carriage_return_is_refused_before_writing(broken):
    with pytest.raises(ValueError, match="carriage return"):
        encode_toml(broken)


def test_text_mode_double_translation_reproduction_and_byte_write_fix(tmp_path):
    text = "[example]\r\nname = 'Ω'\r\n"
    stream = io.BytesIO()
    writer = io.TextIOWrapper(stream, encoding="utf-8", newline="\r\n")
    writer.write(text)
    writer.flush()
    broken = stream.getvalue()
    assert broken == b"[example]\r\r\nname = '\xce\xa9'\r\r\n"
    with pytest.raises(tomllib.TOMLDecodeError):
        tomllib.loads(broken.decode("utf-8"))
    fixed = encode_toml(text, newline="\r\n")
    path = tmp_path / "publication.toml"
    path.write_bytes(fixed)
    assert path.read_bytes() == text.encode("utf-8")
    assert tomllib.loads(path.read_text(encoding="utf-8")) == {"example": {"name": "Ω"}}


@pytest.mark.parametrize("bom", [b"", BOM])
@pytest.mark.parametrize("input_newline", ["\n", "\r\n"])
@pytest.mark.parametrize("final_newline", [False, True])
def test_publication_preserves_bom_final_newline_and_multiline_values(
    tmp_path, bom, input_newline, final_newline
):
    original = bom + (FIXTURE.rstrip("\n") + ("\n" if final_newline else "")).replace(
        "\n", input_newline
    ).encode("utf-8")
    updated = original.decode("utf-8-sig").replace("C:\\CAD models\\old", "D:\\New Ω")
    raw = encode_toml(updated, newline="\r\n", source_bytes=original)
    target = tmp_path / "publication Ω.toml"
    target.write_bytes(raw)
    assert raw.startswith(BOM) is bool(bom)
    assert raw.count(BOM) == bool(bom)
    assert raw.endswith(b"\r\n") is final_newline
    assert b"\r\r\n" not in raw and b"\r" not in raw.replace(b"\r\n", b"")
    before = tomllib.loads(original.decode("utf-8-sig"))
    after = tomllib.loads(target.read_bytes().decode("utf-8-sig"))
    assert after["marketplaces"]["freecad-development"]["source"] == "D:\\New Ω"
    after["marketplaces"] = before["marketplaces"]
    assert after == before


def test_invalid_original_is_refused_before_publication():
    with pytest.raises(ValueError, match="carriage return"):
        encode_toml("name = 'valid'\n", source_bytes=BOM + b"name = 'original'\r\r\n")


def test_setup_generated_reference_has_valid_platform_line_endings(tmp_path):
    output = tmp_path / "generated Ω"
    generate(tmp_path / "CAD Ω models", output)
    raw = (output / "codex-mcp.toml").read_bytes()
    assert b"\r\r\n" not in raw and b"\r" not in raw.replace(b"\r\n", b"")
    if os.name == "nt":
        assert raw.count(b"\r\n") == raw.count(b"\n")
    assert set(tomllib.loads(raw.decode("utf-8"))["mcp_servers"]) == {
        "freecad-live",
        "freecad-headless",
    }
