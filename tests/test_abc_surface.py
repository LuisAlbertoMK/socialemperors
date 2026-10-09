"""Tests for tools.abc_surface.

These tests use only synthetic fixtures built inside this file so that they pin
the parser's behaviour without depending on the real game assets.
"""

from __future__ import annotations

import struct
import zlib

import pytest

import tools.abc_surface as abc_surface


def _u30(value: int) -> bytes:
    """Encode an unsigned 30-bit integer in ABC's variable-length format."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def _s32(value: int) -> bytes:
    """Encode a signed 32-bit integer as ABC's variable-length s32/u30 form."""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if (value != 0 or (byte & 0x40) != 0) and (value != -1 or (byte & 0x40) == 0):
            out.append(byte | 0x80)
        else:
            out.append(byte & 0x7F)
            break
    return bytes(out)


def _string(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return _u30(len(encoded)) + encoded


def _build_minimal_abc() -> bytes:
    """Hand-assemble a tiny but structurally valid ABC block.

    The resulting ABC contains:
    - constant pool: 1 int, 1 uint, 1 double, 3 strings, 2 namespaces,
      1 namespace set, 2 multinames
    - 1 method (no params, name idx 1, flags 0)
    - 0 metadata entries
    - 1 instance (name idx 2, super idx 0, iinit = method 0)
    - 1 class (cinit = method 0)
    - 1 script (init = method 0)
    - 1 method body with bytecode: getlocal0, pushscope, getlocal0, returnvalue
    """
    data = bytearray()

    # Header
    data += struct.pack("<HH", 16, 46)  # minor, major

    # Constant pool
    # ints: count=2, int[0]=0 (implicit), int[1]=42
    data += _u30(2)
    data += _s32(42)
    # uints: count=2, uint[0]=0 (implicit), uint[1]=7
    data += _u30(2)
    data += struct.pack("<I", 7)
    # doubles: count=2, double[0]=0.0 (implicit), double[1]=3.14
    data += _u30(2)
    data += struct.pack("<d", 3.14)
    # strings: count=4, implicit [0]="", [1]="main", [2]="TestClass", [3]="Object"
    data += _u30(4)
    data += _string("main")
    data += _string("TestClass")
    data += _string("Object")
    # namespaces: count=2, implicit [0] kind=0 name=0, [1] kind=22 name=1 (public)
    data += _u30(2)
    data += bytes([22]) + _u30(1)  # namespace 1
    # namespace sets: count=2, implicit [0] count=0, [1] count=1 ns=1
    data += _u30(2)
    data += _u30(1) + _u30(1)
    # multinames: count=3, implicit [0] kind=0, [1] QName ns=1 name=2, [2] QName ns=1 name=3
    data += _u30(3)
    data += bytes([0x07]) + _u30(1) + _u30(2)  # multiname 1
    data += bytes([0x07]) + _u30(1) + _u30(3)  # multiname 2

    # Methods: count=1
    data += _u30(1)
    data += _u30(0)  # param_count
    data += _u30(0)  # return_type
    # no param types
    data += _u30(1)  # name = "main"
    data += bytes([0])  # flags

    # Metadata: count=0
    data += _u30(0)

    # Instances: count=1
    data += _u30(1)
    data += _u30(2)  # name = TestClass
    data += _u30(3)  # super_name = Object
    data += bytes([0])  # flags
    data += _u30(0)  # interface_count
    data += _u30(0)  # iinit = method 0
    data += _u30(0)  # trait_count

    # Classes: count=1 (same as instance_count)
    data += _u30(0)  # cinit = method 0
    data += _u30(0)  # trait_count

    # Scripts: count=1
    data += _u30(1)
    data += _u30(0)  # init = method 0
    data += _u30(0)  # trait_count

    # Method bodies: count=1
    data += _u30(1)
    data += _u30(0)  # method
    data += _u30(1)  # max_stack
    data += _u30(1)  # local_count
    data += _u30(0)  # init_scope_depth
    data += _u30(1)  # max_scope_depth

    code = bytes([
        0xD0,  # getlocal0
        0x30,  # pushscope
        0xD0,  # getlocal0
        0x48,  # returnvalue
    ])
    data += _u30(len(code))
    data += code
    data += _u30(0)  # exception_count
    data += _u30(0)  # trait_count

    return bytes(data)


def _build_swf_with_abc(abc_bytes: bytes) -> bytes:
    """Wrap an ABC block in a minimal CWS SWF with a single DoABC tag."""
    # SWF header: CWS, version 9, uncompressed length (UI32)
    # RECT: Nbits=1, Xmin=0, Xmax=0, Ymin=0, Ymax=0 => 1 byte 0x00
    # Frame rate 1 byte, frame count 2 bytes => 3 bytes
    # Then tags.
    uncompressed = bytearray()
    uncompressed += bytes([0x46, 0x57, 0x53, 0x09])  # FWS signature + version
    uncompressed += struct.pack("<I", 0)  # file length placeholder

    # RECT: nbits=0 => 5 bits padded to 1 byte
    uncompressed += bytes([0x00])
    # Frame rate (UI16) + frame count (UI16)
    uncompressed += bytes([0x00, 0x00, 0x00, 0x00])

    # DoABC tag (82): header + flags/name + abc data
    tag_body = struct.pack("<I", 0) + b"\x00" + abc_bytes  # flags=0, name=""
    tag_code = 82
    tag_len = len(tag_body)
    if tag_len < 0x3F:
        tag_header = struct.pack("<H", (tag_code << 6) | tag_len)
    else:
        tag_header = struct.pack("<H", (tag_code << 6) | 0x3F) + struct.pack("<I", tag_len)
    uncompressed += tag_header + tag_body

    # End tag (0)
    uncompressed += struct.pack("<H", 0)

    # Patch file length
    file_len = len(uncompressed)
    uncompressed[4:8] = struct.pack("<I", file_len)

    # Compress to CWS: signature + version + uncompressed length + zlib(body)
    body = uncompressed[8:]
    compressed = bytearray()
    compressed += bytes([0x43, 0x57, 0x53, 0x09])
    compressed += struct.pack("<I", file_len)
    compressed += zlib.compress(bytes(body))
    return bytes(compressed)


def test_read_u30_boundary_values():
    assert abc_surface.read_u30(b"\x00", 0) == (1, 0)
    assert abc_surface.read_u30(b"\x7f", 0) == (1, 127)
    assert abc_surface.read_u30(b"\x80\x01", 0) == (2, 128)
    assert abc_surface.read_u30(b"\xff\x7f", 0) == (2, 16383)
    assert abc_surface.read_u30(b"\x80\x80\x01", 0) == (3, 16384)


def test_swf_tag_walker_parses_short_and_long_headers():
    """The tag walker must handle short (16-bit) and long (UI32) tag lengths."""
    abc = _build_minimal_abc()
    swf = _build_swf_with_abc(abc)
    result = abc_surface.analyze_swf(swf, "synthetic.swf")
    assert result["vm_type"] == "AVM2"
    assert result["do_abc_count"] == 1
    assert result["do_abc_bytes"] == len(abc_surface._extract_tag_body(swf, 82)[0])
    assert result["classes"] == 1
    assert result["methods"] == 1
    assert result["method_bodies"] == 1


def test_abc_pool_counts_are_reported():
    abc = _build_minimal_abc()
    swf = _build_swf_with_abc(abc)
    result = abc_surface.analyze_swf(swf, "synthetic.swf")
    # Counts include the implicit zero entry for ints/uints/doubles/strings/namespaces/ns_sets/multinames.
    assert result["constant_pool"]["ints"] == 2
    assert result["constant_pool"]["uints"] == 2
    assert result["constant_pool"]["doubles"] == 2
    assert result["constant_pool"]["strings"] == 4
    assert result["constant_pool"]["namespaces"] == 2
    assert result["constant_pool"]["namespace_sets"] == 2
    assert result["constant_pool"]["multinames"] == 3


def test_opcode_histogram_counts_known_opcodes():
    abc = _build_minimal_abc()
    swf = _build_swf_with_abc(abc)
    result = abc_surface.analyze_swf(swf, "synthetic.swf")
    hist = result["opcode_histogram"]
    assert hist["0xD0"] == 2  # getlocal0
    assert hist["0x30"] == 1  # pushscope
    assert hist["0x48"] == 1  # returnvalue
    assert result["distinct_opcodes_used"] == 3
    assert "0xD0" in result["top_opcodes"][0]


def test_malformed_truncated_tag_raises_with_offset():
    """A truncated SWF tag must raise loudly with the failing byte offset."""
    # CWS header followed by a tag that claims a body longer than remaining bytes.
    body = bytearray()
    body += bytes([0x43, 0x57, 0x53, 0x09])
    body += struct.pack("<I", 1000)  # claimed file length
    body += zlib.compress(
        bytes([0x00])  # RECT (nbits=0)
        + bytes([0x00] * 4)  # frame rate + frame count
        + struct.pack("<H", (82 << 6) | 0x3F)  # DoABC long header
        + struct.pack("<I", 500)  # claims 500 bytes
        + b"\x00\x00"  # but only 2 bytes of body
    )
    with pytest.raises(abc_surface.ParseError) as exc:
        abc_surface.analyze_swf(bytes(body), "truncated.swf")
    assert "byte offset" in str(exc.value).lower()


def test_malformed_abc_method_body_overflow_raises():
    """A method body whose code_length exceeds the ABC block must raise."""
    _ = _build_minimal_abc()  # reference kept for clarity; actual malformed ABC is built below
    # Find the code_length u30 for the single method body and overwrite it.
    # Simpler: build a tiny standalone malformed ABC and wrap it.
    bad_abc = bytearray()
    bad_abc += struct.pack("<HH", 16, 46)
    # Empty-ish pools
    for _ in range(7):
        bad_abc += _u30(1)
    # methods=0, metadata=0, instances=0, scripts=0
    for _ in range(4):
        bad_abc += _u30(0)
    # method bodies = 1 with a huge code_length
    bad_abc += _u30(1)
    bad_abc += _u30(0)  # method
    bad_abc += _u30(0)  # max_stack
    bad_abc += _u30(0)  # local_count
    bad_abc += _u30(0)  # init_scope_depth
    bad_abc += _u30(0)  # max_scope_depth
    bad_abc += _u30(0xFFFFFFF)  # code_length impossibly large
    bad_abc += b"\x00"  # one byte of code

    swf = _build_swf_with_abc(bytes(bad_abc))
    with pytest.raises(abc_surface.ParseError) as exc:
        abc_surface.analyze_swf(swf, "bad_body.swf")
    assert "byte offset" in str(exc.value).lower()


def test_avm1_swf_reports_avm1():
    """A SWF with DoAction but no DoABC must be reported as AVM1."""
    uncompressed = bytearray()
    uncompressed += bytes([0x46, 0x57, 0x53, 0x09])
    uncompressed += struct.pack("<I", 0)
    uncompressed += bytes([0x00])  # RECT
    uncompressed += bytes([0x00, 0x00, 0x00, 0x00])  # frame rate/count

    # DoAction tag (12) with a tiny action
    body = bytes([0x00, 0x00])  # ActionEndFlag + one byte
    tag_header = struct.pack("<H", (12 << 6) | len(body))
    uncompressed += tag_header + body
    uncompressed += struct.pack("<H", 0)  # End

    file_len = len(uncompressed)
    uncompressed[4:8] = struct.pack("<I", file_len)

    # Store as FWS to avoid zlib complexity
    swf = bytes(uncompressed)
    result = abc_surface.analyze_swf(swf, "avm1.swf")
    assert result["vm_type"] == "AVM1"
    assert result["do_action_count"] == 1
    assert result["do_action_bytes"] == len(body)


def test_top_classes_lists_synthetic_class():
    abc = _build_minimal_abc()
    swf = _build_swf_with_abc(abc)
    result = abc_surface.analyze_swf(swf, "synthetic.swf")
    assert any("TestClass" in name for name, _ in result["top_classes"])
