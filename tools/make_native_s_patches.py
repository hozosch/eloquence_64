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
	"60e8000000005805ce01000083be5b18000000751231d2891089500489500889500c895010eb1d"
	"8b8ef314000085c97e136a0050518d969b0d000052e80f00000083c410618b94240c010000c366"
	"90905653e833010000057101000083ec048b7424148b5424188b5c241c85f60f8e130100008b4c"
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
SPLIT_FRICATION_FILTER_CODE = bytes.fromhex(
	"89500c895010578db8f401000089d0b90a000000f3ab5fc32e8db42600000000d84c244052e8000000005a83bc2400010000"
	"00757283bc240401000000756883ec08d91c24d98286010000d80c24d8829e010000d95c2404d9828a010000d80c24d98292"
	"010000d84c2404d9e0dec1d882a2010000d99a9e010000d9828e010000d80c24d98296010000d84c2404d9e0dec1d99aa201"
	"0000d9442404d88a9a01000083c408eb0e31c089829e0100008982a20100005a83c40458c3eb432e8db426000000002e8db4"
	"26000000002e8db426000000002e8db426000000002e8db426000000002e8db426000000002e8db426000000002e8db42600"
	"0000008d760060e8000000005d89d883e80d83f8030f87920000008dbcc5ca0000008b54240c83baf400000000757783baf8"
	"00000000756e8b9ee31300008b8ef314000085c97e6583ec08d903d91c24d985aa000000d80c24d807d95c2404d985ae0000"
	"00d80c24d985b6000000d84c2404d9e0dec1d84704d91fd985b2000000d80c24d985ba000000d84c2404d9e0dec1d95f04d9"
	"442404d91b83c3044975aa83c408eb0731d2891789570461e953010000906690ad58583f49c80c3fd122563ec26ccabe1a204c"
	"3e18594b3f00000000000000000000000000000000000000000000000000000000000000000000000000000000"
)
SPLIT_FILTER_BLOCK_OFFSET = 0x300
DIRECT_FILTER_PROCESS_OFFSET = 0x320
PARALLEL_FILTER_PROCESS_OFFSET = 0x400
ORIGINAL_PARALLEL_MIXER_OFFSET = 0x600
DIRECT_TAIL_OFFSET = 0x3F
DIRECT_TAIL = bytes.fromhex("d84c243c58")
PARALLEL_MIXER_RUN_DELTA = 0x1EC1
FRICATION_PROCESS_CALL_OFFSET = 0x3C
FRICATION_PROCESS_OFFSET = 0x150
FRICATION_INACTIVE_TAIL_OFFSET = 0x1F
FRICATION_INACTIVE_TAIL = bytes.fromhex("89500c895010eb1d")
SPLIT_BAND_COEFFICIENTS = (
	0.8451030710061816,
	0.5499311376530391,
	0.20911718551258923,
	-0.39536100764539944,
	0.199341207209701,
)
DIRECT_PATH_GAIN = 0.7943282347242815
SIBILANCE_TARGET_STACK_OFFSETS = (0xF0, 0xF4)


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


def _xflt_runtime_offset(runs: list[tuple[int, bytes, bytes]], source: Path) -> int:
	"""Return the appended section's call coordinate in the original code section.

	PE raw offsets and runtime RVAs do not have the same delta in every Eloquence
	module. The established native-16 entry hook already contains the correct
	runtime-relative displacement, so derive all later hook targets from it.
	"""
	xflt_hooks = [
		run
		for run in runs
		if len(run[1]) == 6
		and run[1] != B6_LOAD
		and run[2][:1] == b"\xe8"
		and run[2][5:] == b"\x90"
	]
	if len(xflt_hooks) != 1:
		raise ValueError(f"Could not uniquely locate .xflt entry hook in {source}")
	hook_offset, _hook_old, hook_new = xflt_hooks[0]
	return hook_offset + 5 + struct.unpack_from("<i", hook_new, 1)[0]


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
	xflt_entry_offset = _xflt_runtime_offset(runs, source)
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
	filter_code_offset = _xflt_runtime_offset(runs, source) + 0x100
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


def make_targeted_consonant_damping_patch(source: Path, destination: Path) -> None:
	"""Split post-Mode-19 frication processing at the engine's real branches.

	The direct f/w/b/p output gets the spectral pivot plus 2 dB attenuation.
	Parallel stages 1--4 get the same pivot for ch/sch. The engine's exact current
	target flags for dedicated sibilance stages 5 and 6 select the native route;
	their interpolated gains are deliberately ignored because those decay into
	the next consonant.
	Stages 5--6 themselves always reach the original mixer unchanged.
	"""
	original_size, patched_size, runs = _read_runs(source.read_bytes())
	count_runs = [run for run in runs if run[1] == b"\x8b\x85\x36\x0a" and run[2] == b"\xb8\x06\x00\x00"]
	if len(count_runs) != 1:
		raise ValueError(f"Could not uniquely locate formant-count instruction in {source}")
	xflt_runtime_offset = _xflt_runtime_offset(runs, source)

	append_indices = [i for i, (offset, old, _new) in enumerate(runs) if offset == original_size and not old]
	if len(append_indices) != 1:
		raise ValueError(f"Could not uniquely locate appended .xflt data in {source}")
	append_index = append_indices[0]
	append_offset, append_old, append_new = runs[append_index]
	entry_in_append = append_new.find(XFLT_ENTRY)
	if entry_in_append < 0 or append_new.find(XFLT_ENTRY, entry_in_append + 1) >= 0:
		raise ValueError(f"Could not uniquely locate .xflt code in {source}")
	filter_in_append = entry_in_append + 0x100
	code_in_append = entry_in_append + SPLIT_FILTER_BLOCK_OFFSET
	for offset, code, label in (
		(filter_in_append, FRICATION_FILTER_CODE, "frication-filter"),
		(code_in_append, SPLIT_FRICATION_FILTER_CODE, "split-frication-filter"),
	):
		if append_new[offset : offset + len(code)] != b"\x90" * len(code):
			raise ValueError(f"{label} code cave is not empty in {source}")

	parallel_mixer_offset = count_runs[0][0] + PARALLEL_MIXER_RUN_DELTA
	parallel_mixer_indices = [
		i
		for i, (offset, _old, new) in enumerate(runs)
		if offset == parallel_mixer_offset and new[:1] == b"\xe8"
	]
	if len(parallel_mixer_indices) != 1:
		raise ValueError(f"Could not uniquely locate parallel mixer hook in {source}")
	parallel_mixer_index = parallel_mixer_indices[0]
	parallel_offset, parallel_old, parallel_new = runs[parallel_mixer_index]
	parallel_target = parallel_offset + 5 + struct.unpack_from("<i", parallel_new, 1)[0]
	if parallel_target != xflt_runtime_offset + ORIGINAL_PARALLEL_MIXER_OFFSET:
		raise ValueError(f"Parallel mixer hook has an unexpected target in {source}")

	modified_append = bytearray(append_new)
	full_treatment_code = bytearray(FRICATION_FILTER_CODE)
	full_treatment_code[FRICATION_FILTER_MODE_OFFSET] = 1
	process_call = FRICATION_PROCESS_CALL_OFFSET
	if full_treatment_code[process_call] != 0xE8:
		raise ValueError(f"Established frication process call not found in {source}")
	process_target = 0x100 + process_call + 5 + struct.unpack_from("<i", full_treatment_code, process_call + 1)[0]
	if process_target != FRICATION_PROCESS_OFFSET:
		raise ValueError(f"Established frication process call has an unexpected target in {source}")
	inactive_tail = FRICATION_INACTIVE_TAIL_OFFSET
	if full_treatment_code[inactive_tail : inactive_tail + len(FRICATION_INACTIVE_TAIL)] != (
		FRICATION_INACTIVE_TAIL
	):
		raise ValueError(f"Established inactive-state reset not found in {source}")
	reset_call_offset = 0x100 + inactive_tail
	reset_relative_call = SPLIT_FILTER_BLOCK_OFFSET - (reset_call_offset + 5)
	full_treatment_code[inactive_tail : inactive_tail + len(FRICATION_INACTIVE_TAIL)] = (
		b"\xe8" + struct.pack("<i", reset_relative_call) + b"\xeb\x1e\x90"
	)
	modified_append[filter_in_append : filter_in_append + len(full_treatment_code)] = full_treatment_code

	direct_tail_in_append = entry_in_append + DIRECT_TAIL_OFFSET
	if modified_append[direct_tail_in_append : direct_tail_in_append + len(DIRECT_TAIL)] != DIRECT_TAIL:
		raise ValueError(f"Direct-frication tail not found in {source}")
	direct_relative_call = DIRECT_FILTER_PROCESS_OFFSET - (DIRECT_TAIL_OFFSET + 5)
	modified_append[direct_tail_in_append : direct_tail_in_append + len(DIRECT_TAIL)] = (
		b"\xe8" + struct.pack("<i", direct_relative_call)
	)
	modified_append[code_in_append : code_in_append + len(SPLIT_FRICATION_FILTER_CODE)] = (
		SPLIT_FRICATION_FILTER_CODE
	)
	runs[append_index] = (append_offset, append_old, bytes(modified_append))

	modified_parallel = bytearray(parallel_new)
	parallel_relative_call = xflt_runtime_offset + PARALLEL_FILTER_PROCESS_OFFSET - (parallel_offset + 5)
	struct.pack_into("<i", modified_parallel, 1, parallel_relative_call)
	runs[parallel_mixer_index] = (parallel_offset, parallel_old, bytes(modified_parallel))

	full_hook_offset = count_runs[0][0] + 0x1D90
	full_hook_target = xflt_runtime_offset + 0x100
	full_relative_call = full_hook_target - (full_hook_offset + 5)
	runs.insert(
		append_index,
		(full_hook_offset, FRICATION_BUFFER_LOAD, b"\xe8" + struct.pack("<i", full_relative_call) + b"\x90\x90"),
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
		make_targeted_consonant_damping_patch(wide_b6, source.with_suffix(".p16st"))


if __name__ == "__main__":
	main()
