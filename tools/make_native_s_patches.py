"""Build native-s comparison patches from the established native-16 patches."""

from __future__ import annotations

import struct
from pathlib import Path


PATCH_DIR = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "eloquence"
TABLE_SUFFIX = bytes.fromhex(
	"11f93f3f1aaab53ea220fd3f2be52abf629e9c3ee9d5e3be58012fbe"
	"9a085e3fae2a6abd011bf63eae2a6a3d352cb2be1dc47b3f9d1ee83f"
	"497e543f9d1ee8bf664250bf"
)


def make_native_s_patch(source: Path, destination: Path) -> None:
	data = bytearray(source.read_bytes())
	if data[:4] != b"P16D":
		raise ValueError(f"Not a P16 patch: {source}")

	match = data.find(TABLE_SUFFIX)
	if match < 8 or data.find(TABLE_SUFFIX, match + 1) >= 0:
		raise ValueError(f"Could not uniquely locate sibilance table in {source}")

	blend_offset = match - 8
	blend_bytes = bytes(data[blend_offset : blend_offset + 4])
	if blend_bytes not in (struct.pack("<f", 0.2), struct.pack("<f", 1.0)):
		blend = struct.unpack("<f", blend_bytes)[0]
		raise ValueError(f"Unexpected shaped-s blend {blend!r} in {source}")

	# The output expression is native + blend * (shaped - native).  A zero
	# blend selects Eloquence's native sibilance path without altering the
	# separate frication filter whose tuning improved /f/.
	struct.pack_into("<f", data, blend_offset, 0.0)
	destination.write_bytes(data)


def make_five_cascade_patch(source: Path, destination: Path) -> None:
	"""Derive a native-s patch that leaves the cascade count at five."""
	data = bytearray(source.read_bytes())
	if data[:4] != b"P16D":
		raise ValueError(f"Not a P16 patch: {source}")

	position = 16
	count = struct.unpack_from("<I", data, 12)[0]
	matches = []
	for _ in range(count):
		_offset, old_length, new_length = struct.unpack_from("<III", data, position)
		position += 12
		old = bytes(data[position : position + old_length])
		position += old_length
		new_position = position
		new = bytes(data[position : position + new_length])
		position += new_length
		if old == b"\x8b\x85\x36\x0a" and new == b"\xb8\x06\x00\x00":
			matches.append(new_position)
	if len(matches) != 1:
		raise ValueError(f"Could not uniquely locate cascade-count instruction in {source}")

	# Keep the first header patch (five PE sections -> six): the appended .xflt
	# section must remain mapped.  Only change the synthesis loop bound from six
	# cascade formants to five.
	data[matches[0] + 1] = 5
	destination.write_bytes(data)


def main() -> None:
	for source in sorted(PATCH_DIR.glob("*.p16")):
		native_s = source.with_suffix(".p16n")
		make_native_s_patch(source, native_s)
		make_five_cascade_patch(native_s, source.with_suffix(".p16b5"))


if __name__ == "__main__":
	main()
