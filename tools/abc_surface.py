"""Measure the AVM2/AVM1 surface of real Adobe Flash SWF files.

This is a pure standard-library tool that walks the SWF tag stream, parses the
ABC (ActionScript Bytecode) container, and reports the actual instruction subset
used by a game client.  It is intentionally dependency-free so it can run on the
preserved assets with nothing but Python 3.

The AVM2 opcode operand table is mechanically transcribed from Ruffle's
avm2/read.rs and avm2/opcode.rs (MIT OR Apache-2.0), which is validated against
real SWFs.  See ``OPCODE_OPERANDS`` below.
"""

from __future__ import annotations

import argparse
import glob
import json
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any


class ParseError(Exception):
    """Raised when a SWF or ABC structure cannot be parsed."""

    def __init__(self, message: str, path: str = "", offset: int = -1) -> None:
        self.path = path
        self.offset = offset
        loc = f" at byte offset {offset}" if offset >= 0 else ""
        src = f" in {path}" if path else ""
        super().__init__(f"{message}{loc}{src}")


# ---------------------------------------------------------------------------
# Low-level ABC readers
# ---------------------------------------------------------------------------


def read_u8(data: bytes, pos: int) -> tuple[int, int]:
    if pos >= len(data):
        raise ParseError("unexpected end of data while reading u8", offset=pos)
    return 1, data[pos]


def read_u16(data: bytes, pos: int) -> tuple[int, int]:
    if pos + 2 > len(data):
        raise ParseError("unexpected end of data while reading u16", offset=pos)
    return 2, struct.unpack_from("<H", data, pos)[0]


def read_u32(data: bytes, pos: int) -> tuple[int, int]:
    if pos + 4 > len(data):
        raise ParseError("unexpected end of data while reading u32", offset=pos)
    return 4, struct.unpack_from("<I", data, pos)[0]


def read_u30(data: bytes, pos: int) -> tuple[int, int]:
    """Read an unsigned 30-bit variable-length integer (1-5 bytes)."""
    value = 0
    shift = 0
    start = pos
    for _ in range(5):
        if pos >= len(data):
            raise ParseError(
                "unexpected end of data while reading u30", offset=start
            )
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return pos - start, value
        shift += 7
    raise ParseError("u30 value exceeds 5 bytes", offset=start)


def read_s32(data: bytes, pos: int) -> tuple[int, int]:
    """Read a signed 32-bit variable-length integer (1-5 bytes)."""
    value = 0
    shift = 0
    start = pos
    for _ in range(5):
        if pos >= len(data):
            raise ParseError(
                "unexpected end of data while reading s32", offset=start
            )
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            # Sign extend if the high bit of the last 7-bit chunk is set.
            if value & (1 << (shift + 6)):
                value -= 1 << (shift + 7)
            return pos - start, value
        shift += 7
    raise ParseError("s32 value exceeds 5 bytes", offset=start)


def read_s24(data: bytes, pos: int) -> tuple[int, int]:
    """Read a signed 24-bit little-endian integer (3 bytes)."""
    if pos + 3 > len(data):
        raise ParseError("unexpected end of data while reading s24", offset=pos)
    raw = data[pos : pos + 3]
    value = raw[0] | (raw[1] << 8) | (raw[2] << 16)
    if value & 0x800000:
        value -= 0x1000000
    return 3, value


def read_double(data: bytes, pos: int) -> tuple[int, float]:
    if pos + 8 > len(data):
        raise ParseError("unexpected end of data while reading double", offset=pos)
    return 8, struct.unpack_from("<d", data, pos)[0]


def read_string(data: bytes, pos: int) -> tuple[int, str]:
    """Read an ABC string (u30 length + UTF-8 payload)."""
    ln, length = read_u30(data, pos)
    start = pos + ln
    if start + length > len(data):
        raise ParseError("string length exceeds data", offset=pos)
    try:
        text = data[start : start + length].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParseError(f"invalid UTF-8 in string: {exc}", offset=start) from exc
    return ln + length, text


# ---------------------------------------------------------------------------
# AVM2 opcode operand table (mechanically transcribed from Ruffle)
# ---------------------------------------------------------------------------

# Each entry maps an opcode byte to a tuple of operand kinds.  Kinds are:
#   'u8'         -> one raw byte
#   'u30'        -> unsigned variable-length integer
#   'i24'        -> signed 24-bit little-endian branch offset
#   'multiname'  -> u30 index into the multiname pool
#   'string'     -> u30 index into the string pool
#   'int'        -> u30 index into the int pool
#   'uint'       -> u30 index into the uint pool
#   'double'     -> u30 index into the double pool
#   'namespace'  -> u30 index into the namespace pool
#   'class'      -> u30 index into the class table (used by NewClass)
#   'method'     -> u30 index into the method table (used by NewFunction/CallStatic)
#   'lookupswitch' -> special variable-length layout (handled in code)
#
# Any byte value absent from this table is an illegal opcode in Ruffle's AVM2
# reader and will be reported as a decode failure rather than silently treated
# as a one-byte instruction.
OPCODE_OPERANDS: dict[int, tuple[str, ...]] = {
    0x01: (),  # Bkpt
    0x02: (),  # Nop
    0x03: (),  # Throw
    0x04: ("multiname",),  # GetSuper
    0x05: ("multiname",),  # SetSuper
    0x06: ("string",),  # Dxns
    0x07: (),  # DxnsLate
    0x08: ("u30",),  # Kill
    0x09: (),  # Label
    0x0C: ("i24",),  # IfNlt
    0x0D: ("i24",),  # IfNle
    0x0E: ("i24",),  # IfNgt
    0x0F: ("i24",),  # IfNge
    0x10: ("i24",),  # Jump
    0x11: ("i24",),  # IfTrue
    0x12: ("i24",),  # IfFalse
    0x13: ("i24",),  # IfEq
    0x14: ("i24",),  # IfNe
    0x15: ("i24",),  # IfLt
    0x16: ("i24",),  # IfLe
    0x17: ("i24",),  # IfGt
    0x18: ("i24",),  # IfGe
    0x19: ("i24",),  # IfStrictEq
    0x1A: ("i24",),  # IfStrictNe
    0x1B: ("lookupswitch",),  # LookupSwitch
    0x1C: (),  # PushWith
    0x1D: (),  # PopScope
    0x1E: (),  # NextName
    0x1F: (),  # HasNext
    0x20: (),  # PushNull
    0x21: (),  # PushUndefined
    0x23: (),  # NextValue
    0x24: ("u8",),  # PushByte
    0x25: ("u30",),  # PushShort
    0x26: (),  # PushTrue
    0x27: (),  # PushFalse
    0x28: (),  # PushNaN
    0x29: (),  # Pop
    0x2A: (),  # Dup
    0x2B: (),  # Swap
    0x2C: ("string",),  # PushString
    0x2D: ("int",),  # PushInt
    0x2E: ("uint",),  # PushUint
    0x2F: ("double",),  # PushDouble
    0x30: (),  # PushScope
    0x31: ("namespace",),  # PushNamespace
    0x32: ("u30", "u30"),  # HasNext2
    0x35: (),  # Li8
    0x36: (),  # Li16
    0x37: (),  # Li32
    0x38: (),  # Lf32
    0x39: (),  # Lf64
    0x3A: (),  # Si8
    0x3B: (),  # Si16
    0x3C: (),  # Si32
    0x3D: (),  # Sf32
    0x3E: (),  # Sf64
    0x40: ("method",),  # NewFunction
    0x41: ("u30",),  # Call
    0x42: ("u30",),  # Construct
    0x43: ("u30", "u30"),  # CallMethod
    0x44: ("method", "u30"),  # CallStatic
    0x45: ("multiname", "u30"),  # CallSuper
    0x46: ("multiname", "u30"),  # CallProperty
    0x47: (),  # ReturnVoid
    0x48: (),  # ReturnValue
    0x49: ("u30",),  # ConstructSuper
    0x4A: ("multiname", "u30"),  # ConstructProp
    0x4C: ("multiname", "u30"),  # CallPropLex
    0x4E: ("multiname", "u30"),  # CallSuperVoid
    0x4F: ("multiname", "u30"),  # CallPropVoid
    0x50: (),  # Sxi1
    0x51: (),  # Sxi8
    0x52: (),  # Sxi16
    0x53: ("u30",),  # ApplyType
    0x55: ("u30",),  # NewObject
    0x56: ("u30",),  # NewArray
    0x57: (),  # NewActivation
    0x58: ("class",),  # NewClass
    0x59: ("multiname",),  # GetDescendants
    0x5A: ("u30",),  # NewCatch
    0x5D: ("multiname",),  # FindPropStrict
    0x5E: ("multiname",),  # FindProperty
    0x5F: ("multiname",),  # FindDef
    0x60: ("multiname",),  # GetLex
    0x61: ("multiname",),  # SetProperty
    0x62: ("u30",),  # GetLocal
    0x63: ("u30",),  # SetLocal
    0x64: (),  # GetGlobalScope
    0x65: ("u8",),  # GetScopeObject
    0x66: ("multiname",),  # GetProperty
    0x67: ("u30",),  # GetOuterScope
    0x68: ("multiname",),  # InitProperty
    0x6A: ("multiname",),  # DeleteProperty
    0x6C: ("u30",),  # GetSlot
    0x6D: ("u30",),  # SetSlot
    0x6E: ("u30",),  # GetGlobalSlot
    0x6F: ("u30",),  # SetGlobalSlot
    0x70: (),  # ConvertS
    0x71: (),  # EscXElem
    0x72: (),  # EscXAttr
    0x73: (),  # ConvertI
    0x74: (),  # ConvertU
    0x75: (),  # ConvertD
    0x76: (),  # ConvertB
    0x77: (),  # ConvertO
    0x78: (),  # CheckFilter
    0x80: ("multiname",),  # Coerce
    0x81: (),  # CoerceB
    0x82: (),  # CoerceA
    0x83: (),  # CoerceI
    0x84: (),  # CoerceD
    0x85: (),  # CoerceS
    0x86: ("multiname",),  # AsType
    0x87: (),  # AsTypeLate
    0x88: (),  # CoerceU
    0x89: (),  # CoerceO
    0x90: (),  # Negate
    0x91: (),  # Increment
    0x92: ("u30",),  # IncLocal
    0x93: (),  # Decrement
    0x94: ("u30",),  # DecLocal
    0x95: (),  # TypeOf
    0x96: (),  # Not
    0x97: (),  # BitNot
    0xA0: (),  # Add
    0xA1: (),  # Subtract
    0xA2: (),  # Multiply
    0xA3: (),  # Divide
    0xA4: (),  # Modulo
    0xA5: (),  # LShift
    0xA6: (),  # RShift
    0xA7: (),  # URShift
    0xA8: (),  # BitAnd
    0xA9: (),  # BitOr
    0xAA: (),  # BitXor
    0xAB: (),  # Equals
    0xAC: (),  # StrictEquals
    0xAD: (),  # LessThan
    0xAE: (),  # LessEquals
    0xAF: (),  # GreaterThan
    0xB0: (),  # GreaterEquals
    0xB1: (),  # InstanceOf
    0xB2: ("multiname",),  # IsType
    0xB3: (),  # IsTypeLate
    0xB4: (),  # In
    0xC0: (),  # IncrementI
    0xC1: (),  # DecrementI
    0xC2: ("u30",),  # IncLocalI
    0xC3: ("u30",),  # DecLocalI
    0xC4: (),  # NegateI
    0xC5: (),  # AddI
    0xC6: (),  # SubtractI
    0xC7: (),  # MultiplyI
    0xD0: (),  # GetLocal0
    0xD1: (),  # GetLocal1
    0xD2: (),  # GetLocal2
    0xD3: (),  # GetLocal3
    0xD4: (),  # SetLocal0
    0xD5: (),  # SetLocal1
    0xD6: (),  # SetLocal2
    0xD7: (),  # SetLocal3
    0xEF: ("u8", "string", "u8", "u30"),  # Debug
    0xF0: ("u30",),  # DebugLine
    0xF1: ("string",),  # DebugFile
    0xF2: ("u30",),  # BkptLine
    0xF3: (),  # Timestamp
}

LEGAL_AVM2_OPCODES: frozenset[int] = frozenset(OPCODE_OPERANDS.keys())

# Branch opcodes that carry a single i24 offset.
_BRANCH_OPCODES: frozenset[int] = frozenset(
    [0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A]
)

# Opcodes whose u30/multiname operand should be counted as a multiname reference
# for the general multiname reference set.
_MULTINAME_OPCODES: frozenset[int] = frozenset(
    op
    for op, operands in OPCODE_OPERANDS.items()
    if "multiname" in operands
)

# String-pool references from instructions.
_STRING_OPCODES: frozenset[int] = frozenset(
    op
    for op, operands in OPCODE_OPERANDS.items()
    if "string" in operands
)

# Class references from instructions (NewClass).
_CLASS_OPCODES: frozenset[int] = frozenset(
    op
    for op, operands in OPCODE_OPERANDS.items()
    if "class" in operands
)

# The specific opcodes the task asks us to prefer when measuring the builtin
# API surface (plus NewClass, whose class index is resolved to the class name).
_API_SURFACE_OPCODES: frozenset[int] = frozenset(
    [
        0x60,  # GetLex
        0x66,  # GetProperty
        0x61,  # SetProperty
        0x46,  # CallProperty
        0x80,  # Coerce
        0x86,  # AsType
        0xB2,  # IsType
        0x4A,  # ConstructProp
        0x58,  # NewClass
        0x5D,  # FindPropStrict
        0x68,  # InitProperty
    ]
)


def _read_operand(
    data: bytes, pos: int, kind: str
) -> tuple[int, int]:
    """Read a single operand and return (bytes_consumed, value)."""
    if kind == "u8":
        return read_u8(data, pos)
    if kind in ("u30", "multiname", "string", "int", "uint", "double", "namespace", "class", "method"):
        return read_u30(data, pos)
    if kind == "i24":
        return read_s24(data, pos)
    raise ParseError(f"unknown operand kind {kind!r}", offset=pos)


# ---------------------------------------------------------------------------
# Bytecode walker
# ---------------------------------------------------------------------------


def parse_bytecode(
    code: bytes,
    body_index: int,
    body_offset: int,
    path: str = "",
) -> dict[str, Any]:
    """Walk an AVM2 method-body code segment and collect instruction metadata.

    Returns a dict with:
      - opcode_histogram: Counter[int]
      - instruction_count: int
      - string_refs: set[int]
      - multiname_refs: set[int]
      - class_refs: set[int]
      - instruction_starts: set[int]
      - branch_targets: set[int]
    """
    hist: Counter[int] = Counter()
    string_refs: set[int] = set()
    multiname_refs: set[int] = set()
    class_refs: set[int] = set()
    instruction_starts: set[int] = set()
    branch_targets: set[int] = set()
    pos = 0
    code_len = len(code)

    def _fail(message: str, offset: int) -> None:
        opcode_byte = code[offset] if 0 <= offset < code_len else -1
        raise ParseError(
            f"{message} (method body {body_index}, opcode 0x{opcode_byte:02X})",
            path=path,
            offset=body_offset + offset,
        )

    while pos < code_len:
        instruction_starts.add(pos)
        opcode = code[pos]
        start = pos
        hist[opcode] += 1
        pos += 1
        if opcode not in LEGAL_AVM2_OPCODES:
            _fail(
                f"illegal opcode byte 0x{opcode:02X} at method body {body_index}",
                start,
            )

        operands = OPCODE_OPERANDS[opcode]
        if operands == ("lookupswitch",):
            # LookupSwitch offsets are relative to the start of the
            # LookupSwitch instruction (the opcode byte), unlike If*/Jump
            # offsets which are relative to the following instruction.
            switch_start = start
            # default offset
            if pos + 3 > code_len:
                _fail("lookupswitch default offset overruns code", start)
            _, default_offset = read_s24(code, pos)
            branch_targets.add(switch_start + default_offset)
            pos += 3
            # number of cases (u30)
            delta, case_count = read_u30(code, pos)
            pos += delta
            # (case_count + 1) i24 offsets
            for _ in range(case_count + 1):
                if pos + 3 > code_len:
                    _fail("lookupswitch case offset overruns code", start)
                _, case_offset = read_s24(code, pos)
                branch_targets.add(switch_start + case_offset)
                pos += 3
        else:
            for kind in operands:
                if pos > code_len:
                    _fail(
                        f"operand overruns code for opcode 0x{opcode:02X}",
                        start,
                    )
                delta, value = _read_operand(code, pos, kind)
                if pos + delta > code_len:
                    _fail(
                        f"operand overruns code for opcode 0x{opcode:02X}",
                        start,
                    )
                pos += delta
                if kind == "i24" and opcode in _BRANCH_OPCODES:
                    # Branch offset is relative to the start of the next
                    # instruction, which is `pos` after the operand is read.
                    branch_targets.add(pos + value)
                if kind == "multiname":
                    multiname_refs.add(value)
                elif kind == "string":
                    string_refs.add(value)
                elif kind == "class":
                    class_refs.add(value)

        if pos > code_len:
            _fail(
                f"instruction 0x{opcode:02X} overruns method body",
                start,
            )

    if pos != code_len:
        _fail(
            f"bytecode parse did not consume exactly code_length bytes "
            f"(ended at {pos}, expected {code_len})",
            pos if pos < code_len else code_len - 1,
        )

    return {
        "opcode_histogram": hist,
        "instruction_count": sum(hist.values()),
        "string_refs": string_refs,
        "multiname_refs": multiname_refs,
        "class_refs": class_refs,
        "instruction_starts": instruction_starts,
        "branch_targets": branch_targets,
    }


# ---------------------------------------------------------------------------
# SWF tag walker
# ---------------------------------------------------------------------------


def _read_rect(data: bytes, pos: int) -> tuple[int, tuple[int, int, int, int]]:
    """Read a SWF RECT and return (bytes_consumed, (xmin,xmax,ymin,ymax))."""
    if pos >= len(data):
        raise ParseError("cannot read RECT nbits", offset=pos)
    first = data[pos]
    nbits = first >> 3
    total_bits = 5 + 4 * nbits
    total_bytes = (total_bits + 7) // 8
    if pos + total_bytes > len(data):
        raise ParseError("RECT fields exceed data", offset=pos)
    # Bits are packed big-endian.  The first 5 bits are nbits; the next four
    # fields are nbits each as signed integers.
    bits = int.from_bytes(data[pos : pos + total_bytes], "big")
    mask = (1 << nbits) - 1 if nbits else 0
    fields = []
    bit_pos = 5
    for _ in range(4):
        if nbits == 0:
            fields.append(0)
        else:
            shift = total_bytes * 8 - bit_pos - nbits
            raw = (bits >> shift) & mask
            if raw & (1 << (nbits - 1)):
                raw -= 1 << nbits
            fields.append(raw)
        bit_pos += nbits
    return total_bytes, tuple(fields)  # type: ignore[return-value]


def _iter_swf_tags(data: bytes, path: str = ""):
    """Yield (tag_code, tag_body_bytes) for each tag in a decompressed SWF."""
    if len(data) < 8:
        raise ParseError("SWF data too short for header", path=path)

    _ = data[3]  # version byte, preserved for documentation
    file_length = struct.unpack_from("<I", data, 4)[0]
    if file_length != len(data):
        # Some generators round the declared length; warn only if way off.
        pass

    pos = 8
    delta, _rect = _read_rect(data, pos)
    pos += delta
    # FrameRate (UI16) + FrameCount (UI16)
    if pos + 4 > len(data):
        raise ParseError("SWF header truncated before tags", path=path, offset=pos)
    pos += 4

    while True:
        if pos + 2 > len(data):
            raise ParseError(
                "tag header exceeds SWF data", path=path, offset=pos
            )
        header = struct.unpack_from("<H", data, pos)[0]
        tag_code = header >> 6
        tag_len = header & 0x3F
        pos += 2
        if tag_len == 0x3F:
            if pos + 4 > len(data):
                raise ParseError(
                    "long tag length exceeds SWF data", path=path, offset=pos
                )
            tag_len = struct.unpack_from("<I", data, pos)[0]
            pos += 4
        if pos + tag_len > len(data):
            raise ParseError(
                f"tag {tag_code} body exceeds SWF data "
                f"(needs {tag_len} bytes, have {len(data) - pos})",
                path=path,
                offset=pos,
            )
        body = data[pos : pos + tag_len]
        pos += tag_len
        yield tag_code, body
        if tag_code == 0:
            break


def decompress_swf(raw: bytes, path: str = "") -> bytes:
    """Return the uncompressed SWF byte stream (FWS or CWS)."""
    if len(raw) < 8:
        raise ParseError("SWF file too short", path=path)
    sig = raw[:3]
    if sig == b"FWS":
        return raw
    if sig == b"CWS":
        try:
            body = zlib.decompress(raw[8:])
        except zlib.error as exc:
            raise ParseError(f"zlib decompress failed: {exc}", path=path) from exc
        # The decompressed stream is a normal FWS file: keep version and the
        # declared uncompressed length, but change the signature to FWS.
        return b"FWS" + raw[3:8] + body
    raise ParseError(
        f"unrecognized SWF signature {sig!r} (expected FWS or CWS)", path=path
    )


def _extract_tag_body(swf: bytes, tag_code: int) -> list[bytes]:
    """Helper for tests: return all bodies of a given tag code."""
    data = decompress_swf(swf, "")
    return [body for tc, body in _iter_swf_tags(data, "") if tc == tag_code]


# ---------------------------------------------------------------------------
# ABC parser
# ---------------------------------------------------------------------------


class ABCFile:
    """Minimal ABC parser that records structural counts and opcode usage."""

    def __init__(self, data: bytes, source: str = "") -> None:
        self.data = data
        self.source = source
        self.pos = 0

        self.minor = self._u16()
        self.major = self._u16()

        self.pool = self._parse_constant_pool()
        self.method_count = self._u30()
        self._skip_method_infos()
        self.metadata_count = self._u30()
        self._skip_metadata()
        self.instance_count = self._u30()
        self.class_names: list[str] = []
        self.instance_name_indices: list[int] = []
        self._parse_instances()
        self._parse_classes()
        self.script_count = self._u30()
        self._skip_scripts()
        self.method_body_count = self._u30()
        self.total_code_bytes = 0
        self.max_stack = 0
        self.max_scope_depth = 0
        self.opcode_histogram: Counter[int] = Counter()
        self.string_refs: set[int] = set()
        self.multiname_refs: set[int] = set()
        self.class_refs: set[int] = set()
        self.instruction_count = 0
        self.unknown_opcodes: set[int] = set()
        self.method_body_offsets: list[int] = []
        self.method_body_codes: list[bytes] = []
        self.method_body_instruction_starts: list[set[int]] = []
        self.failed_method_bodies: list[dict[str, Any]] = []
        self.boundary_violations: list[dict[str, Any]] = []
        self._parse_method_bodies()

    def _u8(self) -> int:
        delta, value = read_u8(self.data, self.pos)
        self.pos += delta
        return value

    def _u16(self) -> int:
        delta, value = read_u16(self.data, self.pos)
        self.pos += delta
        return value

    def _u30(self) -> int:
        delta, value = read_u30(self.data, self.pos)
        self.pos += delta
        return value

    def _s32(self) -> int:
        delta, value = read_s32(self.data, self.pos)
        self.pos += delta
        return value

    def _u32(self) -> int:
        delta, value = read_u32(self.data, self.pos)
        self.pos += delta
        return value

    def _double(self) -> float:
        delta, value = read_double(self.data, self.pos)
        self.pos += delta
        return value

    def _string(self) -> str:
        delta, value = read_string(self.data, self.pos)
        self.pos += delta
        return value

    def _namespace(self) -> tuple[int, int]:
        kind = self._u8()
        name = self._u30()
        return kind, name

    def _ns_set(self) -> list[int]:
        count = self._u30()
        return [self._u30() for _ in range(count)]

    def _multiname(self) -> tuple[int, list[int]]:
        kind = self._u8()
        rest: list[int] = []
        if kind == 0x07 or kind == 0x0D:  # QName / QNameA
            rest = [self._u30(), self._u30()]
        elif kind == 0x0F or kind == 0x10:  # RTQName / RTQNameA
            rest = [self._u30()]
        elif kind == 0x11 or kind == 0x12:  # RTQNameL / RTQNameLA
            rest = []
        elif kind == 0x09 or kind == 0x0E:  # Multiname / MultinameA
            rest = [self._u30(), self._u30()]
        elif kind == 0x1B or kind == 0x1C:  # MultinameL / MultinameLA
            rest = [self._u30()]
        elif kind == 0x1D:  # TypeName
            rest = [self._u30(), self._u30()]
            for _ in range(rest[1]):
                rest.append(self._u30())
        else:
            raise ParseError(
                f"unknown multiname kind 0x{kind:02X}",
                path=self.source,
                offset=self.pos - 1,
            )
        return kind, rest

    def _parse_constant_pool(self) -> dict[str, int]:
        """Parse the ABC constant pool: each count is followed by its values.

        Index 0 of every pool is implicit (0 / empty string / empty namespace /
        empty ns_set / empty multiname), so a count of N means N-1 stored entries.
        """
        pool: dict[str, int] = {}
        pool["ints"] = self._u30()
        for _ in range(pool["ints"] - 1):
            self._s32()
        pool["uints"] = self._u30()
        for _ in range(pool["uints"] - 1):
            self._u32()
        pool["doubles"] = self._u30()
        for _ in range(pool["doubles"] - 1):
            self._double()
        pool["strings"] = self._u30()
        self.strings: list[str] = [""]
        for _ in range(pool["strings"] - 1):
            self.strings.append(self._string())
        pool["namespaces"] = self._u30()
        self.namespaces: list[tuple[int, int]] = [(0, 0)]
        for _ in range(pool["namespaces"] - 1):
            self.namespaces.append(self._namespace())
        pool["namespace_sets"] = self._u30()
        self.ns_sets: list[list[int]] = [[]]
        for _ in range(pool["namespace_sets"] - 1):
            self.ns_sets.append(self._ns_set())
        pool["multinames"] = self._u30()
        self.multinames: list[tuple[int, list[int]]] = [(0, [])]
        for _ in range(pool["multinames"] - 1):
            self.multinames.append(self._multiname())
        return pool

    def _skip_method_info(self) -> None:
        param_count = self._u30()
        self._u30()  # return_type
        for _ in range(param_count):
            self._u30()  # param_type
        self._u30()  # name
        flags = self._u8()
        if flags & 0x08:  # HAS_OPTIONAL
            option_count = self._u30()
            for _ in range(option_count):
                self._u30()  # val
                self._u8()  # kind
        if flags & 0x80:  # HAS_PARAM_NAMES
            for _ in range(param_count):
                self._u30()

    def _skip_method_infos(self) -> None:
        for _ in range(self.method_count):
            self._skip_method_info()

    def _skip_metadata(self) -> None:
        for _ in range(self.metadata_count):
            self._u30()  # name
            item_count = self._u30()
            for _ in range(item_count):
                self._u30()  # key
                self._u30()  # value

    def _skip_traits(self) -> None:
        count = self._u30()
        for _ in range(count):
            self._u30()  # name
            kind = self._u8()
            trait_kind = kind & 0x0F
            if trait_kind in (0, 6):  # Slot / Const
                self._u30()  # slot_id
                self._u30()  # type_name
                vindex = self._u30()
                if vindex:
                    self._u8()  # vkind
            elif trait_kind in (1, 2, 3):  # Method / Getter / Setter
                self._u30()  # disp_id
                self._u30()  # method
            elif trait_kind == 4:  # Class
                self._u30()  # slot_id
                self._u30()  # classi
            elif trait_kind == 5:  # Function
                self._u30()  # slot_id
                self._u30()  # function
            else:
                raise ParseError(
                    f"unknown trait kind {trait_kind}",
                    path=self.source,
                    offset=self.pos - 1,
                )
            if kind & 0x40:  # ATTR_METADATA
                meta_count = self._u30()
                for _ in range(meta_count):
                    self._u30()

    def _parse_instances(self) -> None:
        for _ in range(self.instance_count):
            name_idx = self._u30()
            _ = self._u30()  # super_name
            flags = self._u8()
            if flags & 0x08:
                self._u30()  # protectedNs
            interface_count = self._u30()
            for _ in range(interface_count):
                self._u30()
            self._u30()  # iinit
            self._skip_traits()

            name = self.strings[name_idx] if name_idx < len(self.strings) else ""
            self.class_names.append(name)
            self.instance_name_indices.append(name_idx)

    def _parse_classes(self) -> None:
        for _ in range(self.instance_count):
            self._u30()  # cinit
            self._skip_traits()

    def _skip_scripts(self) -> None:
        for _ in range(self.script_count):
            self._u30()  # init
            self._skip_traits()

    def _resolve_multiname_to_pairs(
        self, multiname_idx: int
    ) -> list[tuple[str, str]]:
        """Return [(namespace_uri, name)] for a multiname index.

        QName has one namespace; Multiname with a namespace set expands to all
        namespace URIs in the set.  Runtime-qualified names and malformed
        indices return empty lists and are ignored for API-surface counting.
        """
        if multiname_idx <= 0 or multiname_idx >= len(self.multinames):
            return []
        kind, rest = self.multinames[multiname_idx]
        if kind in (0x07, 0x0D):  # QName / QNameA
            ns_idx = rest[0]
            name_idx = rest[1]
            ns_uri = (
                self.strings[self.namespaces[ns_idx][1]]
                if ns_idx < len(self.namespaces)
                and self.namespaces[ns_idx][1] < len(self.strings)
                else ""
            )
            name = self.strings[name_idx] if name_idx < len(self.strings) else ""
            return [(ns_uri, name)]
        if kind in (0x09, 0x0E):  # Multiname / MultinameA
            name_idx = rest[0]
            ns_set_idx = rest[1]
            name = self.strings[name_idx] if name_idx < len(self.strings) else ""
            pairs: list[tuple[str, str]] = []
            if (
                0 <= ns_set_idx < len(self.ns_sets)
                and name
            ):
                for ns_idx in self.ns_sets[ns_set_idx]:
                    if ns_idx < len(self.namespaces):
                        ns_uri = self.strings[self.namespaces[ns_idx][1]]
                        pairs.append((ns_uri, name))
            return pairs
        # RTQName, RTQNameL, MultinameL etc. are runtime-resolved; skip.
        return []

    def _build_api_surface(self) -> dict[str, Any]:
        """Count referenced builtin names grouped by namespace URI."""
        api_refs: set[tuple[str, str]] = set()
        api_opcodes = _API_SURFACE_OPCODES - _CLASS_OPCODES

        for body_index in range(self.method_body_count):
            code = self.method_body_codes[body_index]
            code_length = len(code)
            cpos = 0
            while cpos < code_length:
                opcode = code[cpos]
                cpos += 1
                if opcode not in LEGAL_AVM2_OPCODES:
                    break
                operands = OPCODE_OPERANDS[opcode]
                if operands == ("lookupswitch",):
                    cpos += 3  # default offset
                    delta, case_count = read_u30(code, cpos)
                    cpos += delta
                    cpos += (case_count + 1) * 3
                else:
                    for kind in operands:
                        delta, value = _read_operand(code, cpos, kind)
                        cpos += delta
                        if opcode in api_opcodes and kind == "multiname":
                            api_refs.update(self._resolve_multiname_to_pairs(value))
                        if (
                            opcode in _CLASS_OPCODES
                            and kind == "class"
                            and 0 <= value < len(self.instance_name_indices)
                        ):
                            name_idx = self.instance_name_indices[value]
                            api_refs.update(
                                self._resolve_multiname_to_pairs(name_idx)
                            )

        # Group by namespace URI.
        by_ns: Counter[str] = Counter()
        for ns_uri, _name in api_refs:
            by_ns[ns_uri] += 1

        # Group by package (namespace URI is the package in AVM2).
        package_counts: Counter[str] = Counter()
        for ns_uri, _name in api_refs:
            package_counts[ns_uri] += 1

        # Builtin = flash.* / flashx.* packages.
        builtin_refs: set[tuple[str, str]] = {
            pair for pair in api_refs if pair[0].startswith(("flash.", "flashx."))
        }
        builtin_packages = sorted({ns for ns, _ in builtin_refs})

        # Game namespaces (heuristic: own package roots).
        game_ns_prefixes = {"com.socialpoint"}
        game_defined_classes = [
            name
            for name in self.class_names
            if any(name.startswith(p) for p in game_ns_prefixes)
        ]

        return {
            "namespace_uri_counts": dict(by_ns.most_common()),
            "package_counts": dict(package_counts.most_common()),
            "builtin_name_count": len(builtin_refs),
            "builtin_package_count": len(builtin_packages),
            "builtin_packages": builtin_packages,
            "builtin_top_packages": package_counts.most_common(),
            "game_defined_classes": len(game_defined_classes),
            "game_namespace_prefixes": sorted(game_ns_prefixes),
        }

    def _parse_method_bodies(self) -> None:
        self._method_body_section_offset = self.pos
        self.failed_method_bodies = []
        self.boundary_violations = []
        for body_index in range(self.method_body_count):
            body_start = self.pos
            try:
                self._u30()  # method
                self.max_stack = max(self.max_stack, self._u30())
                self._u30()  # local_count
                self._u30()  # init_scope_depth
                self.max_scope_depth = max(
                    self.max_scope_depth, self._u30()
                )
                code_length = self._u30()
                if code_length > len(self.data) - self.pos:
                    raise ParseError(
                        f"method body code_length {code_length} exceeds ABC data",
                        path=self.source,
                        offset=self.pos,
                    )
                code = self.data[self.pos : self.pos + code_length]
                parsed = parse_bytecode(code, body_index, self.pos, self.source)
                self.total_code_bytes += code_length
                self.method_body_offsets.append(self.pos)
                self.method_body_codes.append(code)
                self.method_body_instruction_starts.append(parsed["instruction_starts"])
                self.opcode_histogram.update(parsed["opcode_histogram"])
                self.string_refs.update(parsed["string_refs"])
                self.multiname_refs.update(parsed["multiname_refs"])
                self.class_refs.update(parsed["class_refs"])
                self.instruction_count += parsed["instruction_count"]
                instruction_starts = parsed["instruction_starts"]
                branch_targets = parsed["branch_targets"]
                self.pos += code_length

                # Validate branch targets land on instruction boundaries.
                # A branch to code_length is a forward jump to the end of the
                # method body; many compilers emit this and it is equivalent to
                # falling through, so we do not count it as a violation.
                for target in branch_targets:
                    if target == code_length:
                        continue
                    if target < 0 or target > code_length or target not in instruction_starts:
                        self.boundary_violations.append(
                            {
                                "kind": "branch",
                                "body_index": body_index,
                                "target": target,
                                "code_length": code_length,
                            }
                        )

                # Parse exceptions for this body and validate handler offsets.
                exception_count = self._u30()
                for _ in range(exception_count):
                    from_offset = self._u30()
                    to_offset = self._u30()
                    target_offset = self._u30()
                    self._u30()  # exc_type
                    self._u30()  # var_name
                    for label, off in (
                        ("from", from_offset),
                        ("target", target_offset),
                    ):
                        if off < 0 or off > code_length or off not in instruction_starts:
                            self.boundary_violations.append(
                                {
                                    "kind": "exception",
                                    "body_index": body_index,
                                    "field": label,
                                    "offset": off,
                                    "code_length": code_length,
                                }
                            )
                    # 'to' may legitimately point to the end of the code.
                    if (
                        to_offset < 0
                        or to_offset > code_length
                        or (
                            to_offset != code_length
                            and to_offset not in instruction_starts
                        )
                    ):
                        self.boundary_violations.append(
                            {
                                "kind": "exception",
                                "body_index": body_index,
                                "field": "to",
                                "offset": to_offset,
                                "code_length": code_length,
                            }
                        )
                self._skip_traits()
            except ParseError as exc:
                self.failed_method_bodies.append(
                    {
                        "body_index": body_index,
                        "offset": exc.offset,
                        "message": str(exc),
                    }
                )
                # Resync at the next method body by skipping the code,
                # exceptions and traits of the failed body.
                self.pos = body_start
                self.method_body_offsets.append(self.pos)
                self.method_body_codes.append(b"")
                self.method_body_instruction_starts.append(set())
                self._u30()  # method
                self._u30()  # max_stack
                self._u30()  # local_count
                self._u30()  # init_scope_depth
                self._u30()  # max_scope_depth
                code_length = self._u30()
                self.pos += code_length
                exception_count = self._u30()
                for _ in range(exception_count):
                    self._u30()  # from
                    self._u30()  # to
                    self._u30()  # target
                    self._u30()  # exc_type
                    self._u30()  # var_name
                self._skip_traits()


# ---------------------------------------------------------------------------
# SWF analyzer
# ---------------------------------------------------------------------------


def analyze_abc(data: bytes, source: str = "") -> dict[str, Any]:
    """Parse an ABC block and return a structured report."""
    abc = ABCFile(data, source)

    used = set(abc.opcode_histogram.keys()) & LEGAL_AVM2_OPCODES
    unused = sorted(LEGAL_AVM2_OPCODES - used)

    top_opcodes = Counter(
        {f"0x{op:02X}": count for op, count in abc.opcode_histogram.items()}
    ).most_common()

    top_classes = Counter(abc.class_names).most_common()

    api_surface = abc._build_api_surface()

    return {
        "minor_version": abc.minor,
        "major_version": abc.major,
        "constant_pool": abc.pool,
        "methods": abc.method_count,
        "metadata": abc.metadata_count,
        "instances": abc.instance_count,
        "classes": abc.instance_count,
        "scripts": abc.script_count,
        "method_bodies": abc.method_body_count,
        "total_bytecode_bytes": abc.total_code_bytes,
        "max_stack": abc.max_stack,
        "max_scope_depth": abc.max_scope_depth,
        "instruction_count": abc.instruction_count,
        "distinct_multiname_refs": len(abc.multiname_refs),
        "distinct_string_refs": len(abc.string_refs),
        "opcode_histogram": {
            f"0x{op:02X}": count for op, count in sorted(abc.opcode_histogram.items())
        },
        "distinct_opcodes_used": len(used),
        "full_avm2_opcode_count": len(LEGAL_AVM2_OPCODES),
        "unused_opcodes": [f"0x{op:02X}" for op in unused],
        "unknown_opcodes_seen": sorted(abc.unknown_opcodes),
        "failed_method_bodies": abc.failed_method_bodies,
        "boundary_violations": abc.boundary_violations,
        "boundary_violation_count": len(abc.boundary_violations),
        "top_opcodes": top_opcodes,
        "top_classes": top_classes,
        "api_surface": api_surface,
    }


def analyze_swf(raw: bytes, path: str = "") -> dict[str, Any]:
    """Analyze one SWF and return a report dict."""
    data = decompress_swf(raw, path)

    do_abc_count = 0
    do_abc_bytes = 0
    do_action_count = 0
    do_action_bytes = 0
    do_init_action_count = 0
    do_init_action_bytes = 0
    abc_reports: list[dict[str, Any]] = []

    for tag_code, body in _iter_swf_tags(data, path):
        if tag_code == 82:  # DoABC / DoABC2
            do_abc_count += 1
            do_abc_bytes += len(body)
            if len(body) < 4:
                raise ParseError(
                    "DoABC tag body too short for flags", path=path
                )
            _ = struct.unpack_from("<I", body, 0)[0]  # flags
            name_start = 4
            # Name is a null-terminated string.  Some generators omit it, so
            # guard against runaway scans.
            name_end = body.find(b"\x00", name_start)
            if name_end == -1:
                raise ParseError(
                    "DoABC tag missing null-terminated name", path=path
                )
            abc_offset = name_end + 1
            abc_data = body[abc_offset:]
            abc_source = f"{path}#DoABC[{do_abc_count - 1}]"
            abc_reports.append(analyze_abc(abc_data, abc_source))
        elif tag_code == 12:  # DoAction
            do_action_count += 1
            do_action_bytes += len(body)
        elif tag_code == 59:  # DoInitAction
            do_init_action_count += 1
            do_init_action_bytes += len(body)
        # Note: DefineSprite (39) bodies are intentionally not recursed into.

    # Determine VM type.  A single DoABC makes the file AVM2 for our purposes;
    # DoAction/DoInitAction are also counted but do not flip an AVM2 file back.
    if do_abc_count:
        vm_type = "AVM2"
    elif do_action_count or do_init_action_count:
        vm_type = "AVM1"
    else:
        vm_type = "None"

    # Aggregate ABC reports.
    aggregated: dict[str, Any] = {
        "methods": 0,
        "metadata": 0,
        "instances": 0,
        "classes": 0,
        "scripts": 0,
        "method_bodies": 0,
        "total_bytecode_bytes": 0,
        "instruction_count": 0,
        "max_stack": 0,
        "max_scope_depth": 0,
        "opcode_histogram": Counter(),
        "distinct_opcodes_used": 0,
        "distinct_multiname_refs": 0,
        "distinct_string_refs": 0,
        "unknown_opcodes_seen": set(),
        "failed_method_bodies": [],
        "boundary_violations": [],
        "top_classes": Counter(),
        "api_surface_namespace_counts": Counter(),
        "api_surface_package_counts": Counter(),
        "api_surface_builtin_name_count": 0,
        "api_surface_builtin_package_count": 0,
        "api_surface_game_defined_classes": 0,
    }
    for rep in abc_reports:
        for key in (
            "methods",
            "metadata",
            "instances",
            "classes",
            "scripts",
            "method_bodies",
            "total_bytecode_bytes",
            "instruction_count",
            "distinct_multiname_refs",
            "distinct_string_refs",
        ):
            aggregated[key] += rep[key]
        aggregated["max_stack"] = max(aggregated["max_stack"], rep["max_stack"])
        aggregated["max_scope_depth"] = max(
            aggregated["max_scope_depth"], rep["max_scope_depth"]
        )
        aggregated["opcode_histogram"].update(
            {int(k, 0): v for k, v in rep["opcode_histogram"].items()}
        )
        aggregated["unknown_opcodes_seen"].update(rep.get("unknown_opcodes_seen", []))
        aggregated["failed_method_bodies"].extend(rep.get("failed_method_bodies", []))
        aggregated["boundary_violations"].extend(rep.get("boundary_violations", []))
        aggregated["top_classes"].update(rep["top_classes"])
        if "api_surface" in rep:
            api = rep["api_surface"]
            for ns, cnt in api.get("namespace_uri_counts", {}).items():
                aggregated["api_surface_namespace_counts"][ns] += cnt
            for pkg, cnt in api.get("package_counts", {}).items():
                aggregated["api_surface_package_counts"][pkg] += cnt
            aggregated["api_surface_builtin_name_count"] += api.get(
                "builtin_name_count", 0
            )
            aggregated["api_surface_builtin_package_count"] += api.get(
                "builtin_package_count", 0
            )
            aggregated["api_surface_game_defined_classes"] += api.get(
                "game_defined_classes", 0
            )

    used = set(aggregated["opcode_histogram"].keys()) & LEGAL_AVM2_OPCODES
    unused = sorted(LEGAL_AVM2_OPCODES - used)
    top_opcodes = Counter(
        {f"0x{op:02X}": count for op, count in aggregated["opcode_histogram"].items()}
    ).most_common()

    return {
        "file": path,
        "vm_type": vm_type,
        "do_abc_count": do_abc_count,
        "do_abc_bytes": do_abc_bytes,
        "do_action_count": do_action_count,
        "do_action_bytes": do_action_bytes,
        "do_init_action_count": do_init_action_count,
        "do_init_action_bytes": do_init_action_bytes,
        "constant_pool": (
            abc_reports[0]["constant_pool"]
            if abc_reports
            else {
                "ints": 0,
                "uints": 0,
                "doubles": 0,
                "strings": 0,
                "namespaces": 0,
                "namespace_sets": 0,
                "multinames": 0,
            }
        ),
        "methods": aggregated["methods"],
        "metadata": aggregated["metadata"],
        "instances": aggregated["instances"],
        "classes": aggregated["classes"],
        "scripts": aggregated["scripts"],
        "method_bodies": aggregated["method_bodies"],
        "total_bytecode_bytes": aggregated["total_bytecode_bytes"],
        "instruction_count": aggregated["instruction_count"],
        "max_stack": aggregated["max_stack"],
        "max_scope_depth": aggregated["max_scope_depth"],
        "distinct_multiname_refs": aggregated["distinct_multiname_refs"],
        "distinct_string_refs": aggregated["distinct_string_refs"],
        "opcode_histogram": {
            f"0x{op:02X}": count
            for op, count in sorted(aggregated["opcode_histogram"].items())
        },
        "distinct_opcodes_used": len(used),
        "full_avm2_opcode_count": len(LEGAL_AVM2_OPCODES),
        "unused_opcodes": [f"0x{op:02X}" for op in unused],
        "unknown_opcodes_seen": sorted(aggregated["unknown_opcodes_seen"]),
        "failed_method_bodies": aggregated["failed_method_bodies"],
        "boundary_violations": aggregated["boundary_violations"],
        "boundary_violation_count": len(aggregated["boundary_violations"]),
        "top_opcodes": top_opcodes,
        "top_classes": aggregated["top_classes"].most_common(),
        "api_surface": {
            "namespace_uri_counts": dict(
                aggregated["api_surface_namespace_counts"].most_common()
            ),
            "package_counts": dict(
                aggregated["api_surface_package_counts"].most_common()
            ),
            "builtin_name_count": aggregated["api_surface_builtin_name_count"],
            "builtin_package_count": aggregated["api_surface_builtin_package_count"],
            "game_defined_classes": aggregated["api_surface_game_defined_classes"],
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _expand_paths(pattern: str) -> list[str]:
    """Expand a glob or literal path, preserving lexicographic order."""
    matches = glob.glob(pattern)
    if not matches and Path(pattern).exists():
        matches = [pattern]
    matches.sort()
    return matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure the AVM2/AVM1 surface of Flash SWF files."
    )
    parser.add_argument("pattern", help="path or glob to one or more SWF files")
    parser.add_argument("--json", dest="json_path", help="write machine-readable report")
    parser.add_argument(
        "--top", type=int, default=10, help="number of top opcodes/classes to report"
    )
    args = parser.parse_args(argv)

    paths = _expand_paths(args.pattern)
    if not paths:
        print(f"No files matched pattern: {args.pattern}", file=sys.stderr)
        return 2

    reports: list[dict[str, Any]] = []
    for path in paths:
        raw = Path(path).read_bytes()
        report = analyze_swf(raw, path)
        reports.append(report)

    if args.json_path:
        out = {
            "files": reports,
            "summary": {
                "files_analyzed": len(reports),
                "avm2_files": sum(1 for r in reports if r["vm_type"] == "AVM2"),
                "avm1_files": sum(1 for r in reports if r["vm_type"] == "AVM1"),
            },
        }
        Path(args.json_path).write_text(json.dumps(out, indent=2))

    for report in reports:
        print(f"\n{report['file']}")
        print(f"  VM: {report['vm_type']}")
        print(f"  DoABC: {report['do_abc_count']} ({report['do_abc_bytes']} bytes)")
        print(
            f"  DoAction: {report['do_action_count']} "
            f"({report['do_action_bytes']} bytes)"
        )
        print(
            f"  Classes: {report['classes']}, Methods: {report['methods']}, "
            f"Method bodies: {report['method_bodies']}"
        )
        print(f"  Total bytecode bytes: {report['total_bytecode_bytes']}")
        print(f"  Instructions: {report['instruction_count']}")
        print(
            f"  Distinct opcodes used: {report['distinct_opcodes_used']} / "
            f"{report['full_avm2_opcode_count']}"
        )
        failed = len(report.get("failed_method_bodies", []))
        print(f"  Method bodies with decode failures: {failed}")
        bv = report.get("boundary_violation_count", 0)
        print(f"  Boundary violations: {bv}")
        unknowns = report.get("unknown_opcodes_seen", [])
        if unknowns:
            preview = ", ".join(f"0x{b:02X}" for b in unknowns[:10])
            if len(unknowns) > 10:
                preview += ", ..."
            print(f"  Unknown bytes at instruction boundary: {preview}")
        print("  Top opcodes:")
        for op, count in report["top_opcodes"][: args.top]:
            print(f"    {op}: {count}")

        api = report.get("api_surface", {})
        print(
            f"  Builtin API surface: {api.get('builtin_name_count', 0)} names "
            f"across {api.get('builtin_package_count', 0)} builtin packages"
        )
        print("  Top builtin packages:")
        pkg_counts = api.get("package_counts", {})
        for pkg, count in list(
            Counter(pkg_counts).most_common(args.top)
        )[: args.top]:
            print(f"    {pkg}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
