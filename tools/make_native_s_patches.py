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


def main() -> None:
	for source in sorted(PATCH_DIR.glob("*.p16")):
		make_native_s_patch(source, source.with_suffix(".p16n"))


if __name__ == "__main__":
	main()
