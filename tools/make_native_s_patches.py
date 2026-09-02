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
	"60e8000000005805ce01000083be5b18000000751231d2891089500489500889500c895010eb1c"
	"8b8ef314000085c97e126a005051ffb69b0d0000e81000000083c410618b94240c010000c36690"
	"66905653e833010000057101000083ec048b7424148b5424188b5c241c85f60f8e130100008b4c"
	"2410d9ee8d34b18d742600d901d9c0d9cadbf17606d9cad9e0d9cad902dcead9eed91424d9c3d9"
	"c9dff4760fd9e0d9cceb0b2e8db4260000000090d9ccd888c8ffffffd888ccffffffd880d0ffff"
	"ffd888d4ffffffd880d8ffffffdefcd9e8d91424d9ccdbf4dddc7719d9cbd888dcffffffd880e0"
	"ffffffdecad9c9d9caeb098d7600dddbd9c9d9ca85dbdec2d9c9d912746ed94208d8e9d888e4ff"
	"ffffd94204d888e8ffffffdec1d9c0d8c1d94204d8e9d95a04d9c9d888ecffffffd84208d8c0d8"
	"6208d95a08dec1d9c0d888f0ffffffd9420cd8c1d980f4ffffffd91424dccbd8c9deebd9cad842"
	"10d95a0cd980f8ffffffd8cadee9d95a10d888fcffffff83c104d959fc39ce0f85fcfeffffddd858"
	"5b5ec38b0424c30000cdcc4c3f00000038cdcc4c3e00001643bd3786359a99193fcdcccc3e18aa"
	"8f3e1f46c73d7c8f3840b235563f0118d23f646b2c3f0000003f00000000000000000000000000"
	"00000000000000000000000000000000000000"
)
FRICATION_FILTER_MODE_OFFSET = 50


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


def make_native_frication_patch(source: Path, destination: Path, full_treatment: bool) -> None:
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
	code[FRICATION_FILTER_MODE_OFFSET] = int(full_treatment)
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
