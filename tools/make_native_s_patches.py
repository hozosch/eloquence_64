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
B6_LOAD = bytes.fromhex("d947548b4758")
CASCADE_PROCESS_COUNT_LOAD = bytes.fromhex("8b864b180000")
FRICATION_BUFFER_LOAD = bytes.fromhex("8b942408010000")
XFLT_ENTRY = bytes.fromhex("50e80000000058d98046000000")
FRICATION_FILTER_CODE = bytes.fromhex(
	"60e80000000058052602000083be5b18000000750f31d2891089500489500889500ceb1d8b8ef3"
	"14000085c97e136a0050518d969b0d000052e81200000083c410618b94240c010000c36690669066"
	"90e86d01000081c2cb01000083ec1c837c242c008b4c24248b4424280f84ef000000d982a8ffff"
	"ffd982acffffffd982b0ffffffd95c2418d982b4ffffffd95c2414d982b8ffffffd95c2410d982"
	"bcffffffd95c240cd982c0ffffffd95c2408d982c4ffffffd95c2404d982c8ffffffd91c24d982"
	"ccffffffd982d0ffffff85c97e7e8b5424208d0c8a8db42600000000d90283c204d9c2d8c9d800"
	"d90424d8cad9442408d8cadee9d84004d918d9c9d84c2404d944240cd8cadee9d95804d9442410"
	"d8c9d84008d9442414d8cad9c5d8cadee9d8400cd95808d9c9d84c2418d9c5d8cadee9d9580cd8"
	"c9d95afc39d1759fddd8ddd8ddd8ddd8eb0d2e8d742600ddd8ddd8ddd8ddd883c41cc38d742600"
	"d982d4ffffffd982d8ffffffd982dcffffffd95c2418d982e0ffffffd95c2414d982e4ffffffd95c"
	"2410d982e8ffffffd95c240cd982ecffffffd95c2408d982f0ffffffd95c2404d982f4ffffffd91c"
	"24d982f8ffffffd982fcffffffe90cffffff8b1424c300009a41f63e6aa4a43f18af0f3fa429ad3f"
	"3f675a3f8055303e042d743dd359743e12d1a2be22d5a73f3d0a573fe0f48b3e487e403f8defdc"
	"3e07e47f3fea1c183f0bbf2f3eac9d8f3cd569933e53890ebf8ca0ba3fae47613f000000000000"
	"00000000000000000000000000000000000000000000"
)
FRICATION_FILTER_MODE_OFFSET = 47


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


def make_six_parallel_formant_patch(source: Path, destination: Path) -> None:
	"""Keep five cascade formants while processing six parallel formants."""
	original_size, patched_size, runs = _read_runs(source.read_bytes())
	cascade_runs = [run for run in runs if run[1] == b"\x8b\x85\x36\x0a" and run[2] == b"\xb8\x06\x00\x00"]
	if len(cascade_runs) != 1:
		raise ValueError(f"Could not uniquely locate formant-count instruction in {source}")

	# Keep the shared formant count at six so coefficient setup and the parallel
	# consonant path both initialize all six filters. Override only the later
	# voiced-cascade processing loop with five.
	count_offset, _count_old, _count_new = cascade_runs[0]
	cascade_process_count_offset = count_offset + 0x1A79
	runs.append(
		(cascade_process_count_offset, CASCADE_PROCESS_COUNT_LOAD, b"\xb8\x05\x00\x00\x00\x90")
	)
	_write_runs(destination, original_size, patched_size, runs)


def _read_runs(data: bytes) -> tuple[int, int, list[tuple[int, bytes, bytes]]]:
	if data[:4] != b"P16D":
		raise ValueError("Not a P16 patch")
	original_size, patched_size, count = struct.unpack_from("<III", data, 4)
	position = 16
	runs = []
	for _ in range(count):
		offset, old_length, new_length = struct.unpack_from("<III", data, position)
		position += 12
		old = data[position : position + old_length]
		position += old_length
		new = data[position : position + new_length]
		position += new_length
		runs.append((offset, old, new))
	if position != len(data):
		raise ValueError("Trailing data in P16 patch")
	return original_size, patched_size, runs


def _write_runs(
	destination: Path,
	original_size: int,
	patched_size: int,
	runs: list[tuple[int, bytes, bytes]],
) -> None:
	data = bytearray(b"P16D")
	data.extend(struct.pack("<III", original_size, patched_size, len(runs)))
	for offset, old, new in runs:
		data.extend(struct.pack("<III", offset, len(old), len(new)))
		data.extend(old)
		data.extend(new)
	destination.write_bytes(data)


def make_b6_bandwidth_patch(source: Path, destination: Path, multiplier: float) -> None:
	"""Widen only the sixth cascade formant inside the native Klatt engine."""
	if multiplier <= 1.0:
		raise ValueError("B6 bandwidth multiplier must be greater than one")
	original_size, patched_size, runs = _read_runs(source.read_bytes())

	cascade_runs = [run for run in runs if run[1] == b"\x8b\x85\x36\x0a" and run[2] == b"\xb8\x06\x00\x00"]
	if len(cascade_runs) != 1:
		raise ValueError(f"Could not uniquely locate cascade-count instruction in {source}")
	# The F6/B6 load is at a fixed offset inside the same synthesis routine.
	b6_load_offset = cascade_runs[0][0] + 0x486

	# The first existing hook enters the appended .xflt section.  Deriving its
	# target from the relative call keeps this independent of each SYN's size.
	xflt_hooks = [run for run in runs if len(run[1]) == 6 and run[2][:1] == b"\xe8" and run[2][5:] == b"\x90"]
	if len(xflt_hooks) != 1:
		raise ValueError(f"Could not uniquely locate .xflt entry hook in {source}")
	hook_offset, _hook_old, hook_new = xflt_hooks[0]
	xflt_entry_offset = hook_offset + 5 + struct.unpack_from("<i", hook_new, 1)[0]
	b6_code_offset = xflt_entry_offset + 0x60

	append_indices = [i for i, (offset, old, _new) in enumerate(runs) if offset == original_size and not old]
	if len(append_indices) != 1:
		raise ValueError(f"Could not uniquely locate appended .xflt data in {source}")
	append_index = append_indices[0]
	append_offset, append_old, append_new = runs[append_index]
	entry_in_append = append_new.find(XFLT_ENTRY)
	if entry_in_append < 0 or append_new.find(XFLT_ENTRY, entry_in_append + 1) >= 0:
		raise ValueError(f"Could not uniquely locate .xflt code in {source}")
	code_in_append = entry_in_append + 0x60
	code = (
		b"\xd9\x47\x54"  # fld dword ptr [edi+54h] (F6)
		+ b"\x68" + struct.pack("<f", multiplier)  # temporary multiplier
		+ b"\xd9\x47\x58"  # fld dword ptr [edi+58h] (B6)
		+ b"\xd8\x0c\x24"  # fmul dword ptr [esp]
		+ b"\xd9\x1c\x24"  # fstp dword ptr [esp]
		+ b"\x58\xc3"  # pop eax; ret (F6 remains on the x87 stack)
	)
	if append_new[code_in_append : code_in_append + len(code)] != b"\x90" * len(code):
		raise ValueError(f"B6 code cave is not empty in {source}")
	modified_append = bytearray(append_new)
	modified_append[code_in_append : code_in_append + len(code)] = code
	runs[append_index] = (append_offset, append_old, bytes(modified_append))

	relative_call = b6_code_offset - (b6_load_offset + 5)
	runs.insert(append_index, (b6_load_offset, B6_LOAD, b"\xe8" + struct.pack("<i", relative_call) + b"\x90"))
	_write_runs(destination, original_size, patched_size, runs)


def make_native_frication_patch(source: Path, destination: Path, hybrid: bool) -> None:
	"""Process only Eloquence's internal frication buffer before it is mixed."""
	original_size, patched_size, runs = _read_runs(source.read_bytes())
	count_runs = [run for run in runs if run[1] == b"\x8b\x85\x36\x0a" and run[2] == b"\xb8\x06\x00\x00"]
	if len(count_runs) != 1:
		raise ValueError(f"Could not uniquely locate formant-count instruction in {source}")
	frication_hook_offset = count_runs[0][0] + 0x1D90

	append_indices = [i for i, (offset, old, _new) in enumerate(runs) if offset == original_size and not old]
	if len(append_indices) != 1:
		raise ValueError(f"Could not uniquely locate appended .xflt data in {source}")
	append_index = append_indices[0]
	append_offset, append_old, append_new = runs[append_index]
	entry_in_append = append_new.find(XFLT_ENTRY)
	if entry_in_append < 0 or append_new.find(XFLT_ENTRY, entry_in_append + 1) >= 0:
		raise ValueError(f"Could not uniquely locate .xflt code in {source}")
	filter_code_offset = original_size + entry_in_append + 0x100
	code_in_append = entry_in_append + 0x100
	code = bytearray(FRICATION_FILTER_CODE)
	code[FRICATION_FILTER_MODE_OFFSET] = int(hybrid)
	if append_new[code_in_append : code_in_append + len(code)] != b"\x90" * len(code):
		raise ValueError(f"Frication-filter code cave is not empty in {source}")
	modified_append = bytearray(append_new)
	modified_append[code_in_append : code_in_append + len(code)] = code
	runs[append_index] = (append_offset, append_old, bytes(modified_append))

	relative_call = filter_code_offset - (frication_hook_offset + 5)
	runs.insert(
		append_index,
		(frication_hook_offset, FRICATION_BUFFER_LOAD, b"\xe8" + struct.pack("<i", relative_call) + b"\x90\x90"),
	)
	_write_runs(destination, original_size, patched_size, runs)


def main() -> None:
	for source in sorted(PATCH_DIR.glob("*.p16")):
		native_s = source.with_suffix(".p16n")
		make_native_s_patch(source, native_s)
		make_five_cascade_patch(native_s, source.with_suffix(".p16b5"))
		make_six_parallel_formant_patch(native_s, source.with_suffix(".p16c6"))
		make_b6_bandwidth_patch(native_s, source.with_suffix(".p16b15"), 1.5)
		make_b6_bandwidth_patch(native_s, source.with_suffix(".p16b20"), 2.0)
		make_b6_bandwidth_patch(native_s, source.with_suffix(".p16b30"), 3.0)
		make_b6_bandwidth_patch(native_s, source.with_suffix(".p16b40"), 4.0)
		wide_b6 = source.with_suffix(".p16b40")
		make_native_frication_patch(wide_b6, source.with_suffix(".p16fs"), False)
		make_native_frication_patch(wide_b6, source.with_suffix(".p16fu"), True)


if __name__ == "__main__":
	main()
