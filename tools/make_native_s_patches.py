"""Build native-s comparison patches from the established native-16 patches."""

from __future__ import annotations

import math
import struct
from pathlib import Path


PATCH_DIR = Path(__file__).resolve().parents[1] / "addon" / "synthDrivers" / "eloquence"
TABLE_SUFFIX = bytes.fromhex(
	"11f93f3f1aaab53ea220fd3f2be52abf629e9c3ee9d5e3be58012fbe"
	"9a085e3fae2a6abd011bf63eae2a6a3d352cb2be1dc47b3f9d1ee83f"
	"497e543f9d1ee8bf664250bf"
)
B6_LOAD = bytes.fromhex("d947548b4758")
B6_CODE_OFFSET = 0x60
B6_MULTIPLIER_OFFSET = 4
BASE_B6_MULTIPLIER = 4.0
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
SIBILANCE_ROLLOFF_FILTER_CODE = bytes.fromhex(
	"89500c895010578db85c02000089d0b90e000000f3abe8050500005fc38d7600d84c244052e8000000005a83bc240001000000757283bc240401000000756883ec08d91c24d982d2010000d80c24d88206020000d95c2404d982d6010000d80c24d982de010000d84c2404d9e0dec1d8820a020000d99a06020000d982da010000d80c"
	"24d982e2010000d84c2404d9e0dec1d99a0a020000d9442404d88a0202000083c408eb0e31c089820602000089820a0200005a83c40458c3eb432e8db426000000002e8db426000000002e8db426000000002e8db426000000002e8db426000000002e8db426000000002e8db426000000002e8db426000000008d7600"
	"60e8000000005d89d883e80d83f8050f87e00000008b54240c83baf400000000752b83baf800000000752283f80377118dbcc5320100008d95f600000031c0eb4e83e8048dbcc552010000eb3983f803762d83e8048dbcc55201000083be5318000000752131c0909090909090909090909090909090908d950a010000eb108d"
	"bcc53201000031c9890f894f04eb668b9ee31300008b8ef314000085c97e5683ec08d903d91c24d902d80c24d807d95c2404d94204d80c24d9420cd84c2404d9e0dec1d84704d91fd94208d80c24d94210d84c2404d9e0dec1d95f04d944240490909090909090909090d91b83c3044975b083c40861e90501000090ad58583f"
	"49c80c3fd122563ec26ccabe1a204c3e0000803f000000000000000000000000000000000000803f0000803f18594b3f0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
	"908db4260000000060e8000000005d8b8ef314000085c97e168bbe930d0000d907d88db2ffffffd91f83c7044975f0618b942410010000c3"
)
NATIVE_OUTPUT_EQ_CODE = bytes.fromhex(
	"60e8000000005d8dbd4a01000031c0b906000000f3ab61c32e8db4260000000060e8000000005d8b8ef314000085c97e738bbe930d000083ec08d907d91c248d85ee0000008d9d2a0100008bb5da000000d900d80c24d803d95c2404d94004d80c24d9400cd84c2404d9e0dec1d84304d91bd94008d80c24d94010d84c2404d9e0dec1d95b04d9442404d91c2483c01483c3084e75bbd90424d91f83c70449759983c408618b86f3140000c3909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090909090"
	"020000000000803f0000803f0000803f0ad7233d0000803f000000000000000000000000000000000000803f000000000000000000000000000000000000803f00000000000000000000000000000000000000000000000000000000000000000000000000000000"
)
SIBILANCE_FILTER_COEFFICIENT_OFFSET = 0x210
# Keep the proven v21.2 voiced-sibilance architecture untouched and move only
# the shared S roll-off higher. The steeper cut retains the same attenuation at
# 7.5 kHz as the preceding 6.8 kHz shaped test while raising the 6-7 kHz band.
SIBILANCE_FILTER_FREQUENCY = 7100.0
SIBILANCE_FILTER_GAIN_DB = -20.0
SIBILANCE_FILTER_MAKEUP_DB = 0.0
HISTORICAL_SIBILANCE_LANGUAGES = frozenset({"CHS", "ENG", "ENU"})
HISTORICAL_SIBILANCE_BLEND = 0.2
ACTIVE_VOICE_BYPASS = bytes.fromhex("83be5318000000752131c0") + b"\x90" * 16
# Pre-v21 tests 91/92 used the current phone's +0xac field as the stable
# voiced/unvoiced discriminator. At this hook the phone pointer is saved at
# esp+0x12c. It is tied to the current phone instead of the following global
# voicing state, which can fall away at the end of short words. Keep all
# routing variants the same length so following coefficient/state offsets stay.
HISTORICAL_PHONE_VOICE_BYPASS = bytes.fromhex(
	"8b94242c01000085d2740983baac00000000751631c0"
) + b"\x90" * 5
FILTER_ALL_SIBILANCE = b"\x31\xc0" + b"\x90" * 25
VOICE_ONLY_BLEND_CODE = bytes.fromhex("d8642424d88d00000000d8442424")
VOICE_ONLY_BLEND_HELPER_OFFSET = 0x9C0
VOICE_ONLY_BLEND_HELPER_CODE = bytes.fromhex(
	"f744242c00010000750c"
	"d8642428d84d00d8442428c3"
	"ddd8d9442428c3"
)
# English voiced sibilants are composite in the old Eloquence engine: their
# lower component uses parallel stages 1-4 while the high frication component
# can be presented separately as an unvoiced stage-5/6 phone.  The surrounding
# synthesis frame exposes exact target flags for all six stages.  Use the lower
# four target flags to associate that separately classified high component with
# the same composite consonant, without changing a plain unvoiced s.
SIBILANCE_CLASSIFIER_CODE = bytes.fromhex(
	"31d283fb11740583fb12750383ca01"
	"8b84242c01000085c0740f83b8ac00000000750681ca00010000"
)
SIBILANCE_CLASSIFIER_OFFSET = 0x601
COMPOSITE_SIBILANCE_CLASSIFIER_OFFSET = 0x9E0
COMPOSITE_SIBILANCE_CLASSIFIER_CODE = bytes.fromhex(
	"31d283fb11740583fb12750383ca018b84243001000085c0740f83b8ac00000000750681ca0001"
	"0000f7c2010000007436f7c200010000742e8b44241083b8e400000000751b83b8e80000000075"
	"1283b8ec00000000750983b8f000000000740681e2fffeffffc3"
)
VOICED_GAIN_DB = -1.5
EARLY_VOICED_HOOK_DELTA = 0x1965
EARLY_VOICED_HOOK_OLD = bytes.fromhex("8b8ef3140000")
EARLY_VOICED_HELPER_OFFSET = 0x5A0
VOICED_S_GAIN = struct.pack("<f", 0.7498942017555237)
FRICATION_MIX_GAIN = struct.pack("<f", 0.3548133969306946)
VOICED_S_GAIN_TABLE_TAIL = VOICED_S_GAIN + FRICATION_MIX_GAIN
OUTPUT_EQ_SAMPLE_RATE = 16000.0
LOW_BASS_EQ = (220.0, 2.0, 1.0)
V21_REFERENCE_EQ = (3430.0, 8.0, 0.406)
PRESENCE_EQ = (4000.0, 8.0, 1.5)
SPLIT_FILTER_BLOCK_OFFSET = 0x300
DIRECT_FILTER_PROCESS_OFFSET = 0x320
PARALLEL_FILTER_PROCESS_OFFSET = 0x400
ORIGINAL_PARALLEL_MIXER_OFFSET = 0x600
NATIVE_OUTPUT_EQ_OFFSET = 0x820
NATIVE_OUTPUT_EQ_PROCESS_OFFSET = 0x20
NATIVE_OUTPUT_EQ_STAGE_COUNT_OFFSET = 0x100
NATIVE_OUTPUT_EQ_COEFFICIENT_OFFSET = 0x114
VOICED_GAIN_OFFSET = 0x228
VOICED_BUFFER_PROCESS_OFFSET = 0x270
DIRECT_TAIL_OFFSET = 0x3F
DIRECT_TAIL = bytes.fromhex("d84c243c58")
PARALLEL_MIXER_RUN_DELTA = 0x1EC1
FRICATION_PROCESS_CALL_OFFSET = 0x3C
FRICATION_PROCESS_OFFSET = 0x150
FRICATION_INACTIVE_TAIL_OFFSET = 0x1F
FRICATION_INACTIVE_TAIL = bytes.fromhex("89500c895010eb1d")
FRICATION_RETURN_TAIL_OFFSET = 0x44
FRICATION_RETURN_TAIL = bytes.fromhex("618b94240c010000c3")
FINAL_BUFFER_COUNT_LOAD = bytes.fromhex("8b86f3140000")
FINAL_OUTPUT_HOOK_DELTA = 0x1F3C
SPLIT_BAND_COEFFICIENTS = (
	0.8451030710061816,
	0.5499311376530391,
	0.20911718551258923,
	-0.39536100764539944,
	0.199341207209701,
)
DIRECT_PATH_GAIN = 0.7943282347242815
SIBILANCE_TARGET_STACK_OFFSETS = (0xF0, 0xF4)
NATIVE_EQ_RESET_CALL = bytes.fromhex("e805050000")


def _sibilance_filter_coefficients(
	frequency: float,
	gain_db: float,
	makeup_db: float,
	sample_rate: float = 16000.0,
) -> tuple[float, float, float, float, float]:
	"""Return a high-shelf roll-off with makeup gain folded into its numerator."""
	if not 0.0 < frequency < sample_rate / 2.0:
		raise ValueError("sibilance filter frequency must be between DC and Nyquist")
	if gain_db >= 0.0:
		raise ValueError("sibilance filter gain must be negative")
	if not 0.0 <= makeup_db < -gain_db:
		raise ValueError("sibilance makeup must be nonnegative and smaller than the cut")

	a = 10.0 ** (gain_db / 40.0)
	w0 = 2.0 * math.pi * frequency / sample_rate
	cos_w0 = math.cos(w0)
	alpha = math.sin(w0) * math.sqrt(2.0) / 2.0
	two_sqrt_a_alpha = 2.0 * math.sqrt(a) * alpha
	a0 = (a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha
	makeup = 10.0 ** (makeup_db / 20.0)
	b0 = makeup * a * ((a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha) / a0
	b1 = makeup * -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0) / a0
	b2 = makeup * a * ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
	a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0) / a0
	a2 = ((a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
	return b0, b1, b2, a1, a2


def _low_shelf_coefficients(
	frequency: float,
	gain_db: float,
	slope: float,
	sample_rate: float = OUTPUT_EQ_SAMPLE_RATE,
) -> tuple[float, float, float, float, float]:
	"""Return the native low-shelf biquad in direct-form coefficient order."""
	a = 10.0 ** (gain_db / 40.0)
	w0 = 2.0 * math.pi * frequency / sample_rate
	cos_w0 = math.cos(w0)
	radical = (a + 1.0 / a) * (1.0 / slope - 1.0) + 2.0
	if radical <= 0.0:
		raise ValueError("Low-shelf slope is too steep for this gain")
	alpha = math.sin(w0) * math.sqrt(radical) / 2.0
	two_sqrt_a_alpha = 2.0 * math.sqrt(a) * alpha
	a0 = (a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha
	b0 = a * ((a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha) / a0
	b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0) / a0
	b2 = a * ((a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
	a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0) / a0
	a2 = ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
	return b0, b1, b2, a1, a2


def _high_shelf_coefficients(
	frequency: float,
	gain_db: float,
	slope: float,
	sample_rate: float = OUTPUT_EQ_SAMPLE_RATE,
) -> tuple[float, float, float, float, float]:
	"""Return the v21-reference high-shelf biquad."""
	a = 10.0 ** (gain_db / 40.0)
	w0 = 2.0 * math.pi * frequency / sample_rate
	cos_w0 = math.cos(w0)
	radical = (a + 1.0 / a) * (1.0 / slope - 1.0) + 2.0
	if radical <= 0.0:
		raise ValueError("High-shelf slope is too steep for this gain")
	alpha = math.sin(w0) * math.sqrt(radical) / 2.0
	two_sqrt_a_alpha = 2.0 * math.sqrt(a) * alpha
	a0 = (a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha
	b0 = a * ((a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha) / a0
	b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0) / a0
	b2 = a * ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
	a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0) / a0
	a2 = ((a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
	return b0, b1, b2, a1, a2


def _peaking_eq_coefficients(
	frequency: float,
	gain_db: float,
	quality: float,
	sample_rate: float = OUTPUT_EQ_SAMPLE_RATE,
) -> tuple[float, float, float, float, float]:
	"""Return the optional 4 kHz presence biquad."""
	a = 10.0 ** (gain_db / 40.0)
	w0 = 2.0 * math.pi * frequency / sample_rate
	alpha = math.sin(w0) / (2.0 * quality)
	cos_w0 = math.cos(w0)
	a0 = 1.0 + alpha / a
	b0 = (1.0 + alpha * a) / a0
	b1 = (-2.0 * cos_w0) / a0
	b2 = (1.0 - alpha * a) / a0
	a1 = (-2.0 * cos_w0) / a0
	a2 = (1.0 - alpha / a) / a0
	return b0, b1, b2, a1, a2


def _native_output_eq_coefficients(presence_enabled: bool) -> tuple[float, ...]:
	coefficients = (
		*_low_shelf_coefficients(*LOW_BASS_EQ),
		*_high_shelf_coefficients(*V21_REFERENCE_EQ),
	)
	if presence_enabled:
		coefficients += _peaking_eq_coefficients(*PRESENCE_EQ)
	else:
		coefficients += (1.0, 0.0, 0.0, 0.0, 0.0)
	return coefficients


def _early_voiced_gain_code(gain_db: float) -> bytes:
	"""Scale the still-separated cascade/voicing buffer at the proven early hook."""
	code = bytes.fromhex(
		"60"                    # pushad
		"e800000000"            # call next instruction
		"5b"                    # pop ebx: position-independent base
		"8b8ef3140000"          # mov ecx, [esi+14f3h]
		"85c9"                  # test ecx, ecx
		"7e1a"                  # jle done
		"8b96930d0000"          # mov edx, [esi+0d93h]
		"d9832e000000"          # fld gain at helper+34h
		"d902"                  # loop: fld [edx]
		"d8c9"                  # fmul st, st(1)
		"d91a"                  # fstp [edx]
		"83c204"                # add edx, 4
		"49"                    # dec ecx
		"75f4"                  # jne loop
		"ddd8"                  # fstp st(0)
		"61"                    # popad
		"8b8ef3140000"          # displaced mov ecx, [esi+14f3h]
		"c3"                    # ret
		"90"                    # align gain to helper+34h
	)
	if len(code) != 0x34:
		raise AssertionError(len(code))
	return code + struct.pack("<f", 10.0 ** (gain_db / 20.0))


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
		and run[1] not in (B6_LOAD, FINAL_BUFFER_COUNT_LOAD)
		and run[2][:1] == b"\xe8"
		and run[2][5:] == b"\x90"
	]
	if len(xflt_hooks) != 1:
		raise ValueError(f"Could not uniquely locate .xflt entry hook in {source}")
	hook_offset, _hook_old, hook_new = xflt_hooks[0]
	return hook_offset + 5 + struct.unpack_from("<i", hook_new, 1)[0]


def _b6_bandwidth_code(multiplier: float) -> bytes:
	return (
		b"\xd9\x47\x54"  # fld dword ptr [edi+54h] (F6)
		+ b"\x68" + struct.pack("<f", multiplier)  # temporary multiplier
		+ b"\xd9\x47\x58"  # fld dword ptr [edi+58h] (B6)
		+ b"\xd8\x0c\x24"  # fmul dword ptr [esp]
		+ b"\xd9\x1c\x24"  # fstp dword ptr [esp]
		+ b"\x58\xc3"  # pop eax; ret (F6 remains on the x87 stack)
	)


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
	b6_code_offset = xflt_entry_offset + B6_CODE_OFFSET

	append_indices = [i for i, (offset, old, _new) in enumerate(runs) if offset == original_size and not old]
	if len(append_indices) != 1:
		raise ValueError(f"Could not uniquely locate appended .xflt data in {source}")
	append_index = append_indices[0]
	append_offset, append_old, append_new = runs[append_index]
	entry_in_append = append_new.find(XFLT_ENTRY)
	if entry_in_append < 0 or append_new.find(XFLT_ENTRY, entry_in_append + 1) >= 0:
		raise ValueError(f"Could not uniquely locate .xflt code in {source}")
	code_in_append = entry_in_append + B6_CODE_OFFSET
	code = _b6_bandwidth_code(multiplier)
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


def _make_consonant_damping_patch(
	source: Path,
	destination: Path,
	split_filter_code: bytes,
) -> None:
	"""Install one hard-routed post-Mode-19 consonant filter implementation."""
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
		(code_in_append, split_filter_code, "split-frication-filter"),
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
	modified_append[code_in_append : code_in_append + len(split_filter_code)] = split_filter_code
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


def make_targeted_consonant_damping_patch(source: Path, destination: Path) -> None:
	"""Filter f/w/b/p and ch/sch while preserving native s/t/z unchanged."""
	_make_consonant_damping_patch(source, destination, SPLIT_FRICATION_FILTER_CODE)


def make_sibilance_rolloff_patch(
	source: Path,
	destination: Path,
	gain_db: float,
	makeup_db: float,
	b6_multiplier: float,
	voiced_gain_db: float = 0.0,
	presence_enabled: bool = True,
) -> None:
	"""Build the release native-16 split, fixed voiced-path gain, and output EQ."""
	if b6_multiplier < BASE_B6_MULTIPLIER:
		raise ValueError("Comparison B6 multiplier must not be narrower than its base")
	if voiced_gain_db > 0.0:
		raise ValueError("Voiced comparison gain must not boost the general voiced path")
	coefficients = _sibilance_filter_coefficients(
		SIBILANCE_FILTER_FREQUENCY,
		gain_db,
		makeup_db,
	)
	original_size, patched_size, runs = _read_runs(source.read_bytes())
	xflt_runtime_offset = _xflt_runtime_offset(runs, source)
	count_runs = [
		run for run in runs if run[1] == b"\x8b\x85\x36\x0a" and run[2] == b"\xb8\x06\x00\x00"
	]
	if len(count_runs) != 1:
		raise ValueError(f"Could not uniquely locate formant-count instruction in {source}")
	append_indices = [i for i, (offset, old, _new) in enumerate(runs) if offset == original_size and not old]
	if len(append_indices) != 1:
		raise ValueError(f"Could not uniquely locate appended .xflt data in {source}")
	append_index = append_indices[0]
	append_offset, append_old, append_new = runs[append_index]
	entry_in_append = append_new.find(XFLT_ENTRY)
	if entry_in_append < 0 or append_new.find(XFLT_ENTRY, entry_in_append + 1) >= 0:
		raise ValueError(f"Could not uniquely locate .xflt code in {source}")
	b6_code_in_append = entry_in_append + B6_CODE_OFFSET
	base_b6_code = _b6_bandwidth_code(BASE_B6_MULTIPLIER)
	if append_new[b6_code_in_append : b6_code_in_append + len(base_b6_code)] != base_b6_code:
		raise ValueError(f"Base B6 bandwidth code was not found in {source}")
	code_in_append = entry_in_append + SPLIT_FILTER_BLOCK_OFFSET
	base_end = code_in_append + len(SPLIT_FRICATION_FILTER_CODE)
	code_end = code_in_append + len(SIBILANCE_ROLLOFF_FILTER_CODE)
	if append_new[code_in_append:base_end] != SPLIT_FRICATION_FILTER_CODE:
		raise ValueError(f"Base split-frication code was not found in {source}")
	if append_new[base_end:code_end] != b"\x90" * (code_end - base_end):
		raise ValueError(f"Sibilance-filter extension overlaps nonempty code in {source}")
	if len(SIBILANCE_ROLLOFF_FILTER_CODE) > ORIGINAL_PARALLEL_MIXER_OFFSET - SPLIT_FILTER_BLOCK_OFFSET:
		raise ValueError("Sibilance filter overlaps the original parallel mixer")
	output_eq_in_append = entry_in_append + NATIVE_OUTPUT_EQ_OFFSET
	output_eq_end = output_eq_in_append + len(NATIVE_OUTPUT_EQ_CODE)
	if append_new[output_eq_in_append:output_eq_end] != b"\x90" * len(NATIVE_OUTPUT_EQ_CODE):
		raise ValueError(f"Native output EQ overlaps nonempty code in {source}")

	code = bytearray(SIBILANCE_ROLLOFF_FILTER_CODE)
	language = source.stem.upper()
	active_voice_bypass = code.find(ACTIVE_VOICE_BYPASS)
	if (
		active_voice_bypass < 0
		or code.find(ACTIVE_VOICE_BYPASS, active_voice_bypass + 1) >= 0
	):
		raise ValueError(f"Could not uniquely locate active-voice bypass in {source}")
	voice_routing = (
		HISTORICAL_PHONE_VOICE_BYPASS
		if language in HISTORICAL_SIBILANCE_LANGUAGES
		else FILTER_ALL_SIBILANCE
	)
	code[
		active_voice_bypass : active_voice_bypass + len(ACTIVE_VOICE_BYPASS)
	] = voice_routing
	struct.pack_into("<5f", code, SIBILANCE_FILTER_COEFFICIENT_OFFSET, *coefficients)
	struct.pack_into(
		"<f",
		code,
		VOICED_GAIN_OFFSET,
		10.0 ** (voiced_gain_db / 20.0),
	)
	reset_calls = [
		offset
		for offset in range(len(code) - len(NATIVE_EQ_RESET_CALL) + 1)
		if code[offset : offset + len(NATIVE_EQ_RESET_CALL)] == NATIVE_EQ_RESET_CALL
	]
	if len(reset_calls) != 1:
		raise ValueError(f"Could not uniquely locate native-EQ reset call in {source}")
	reset_call = reset_calls[0]
	reset_target = reset_call + 5 + struct.unpack_from("<i", code, reset_call + 1)[0]
	if reset_target != NATIVE_OUTPUT_EQ_OFFSET - SPLIT_FILTER_BLOCK_OFFSET:
		raise ValueError(f"Native-EQ reset call has an unexpected target in {source}")
	code[reset_call : reset_call + 5] = b"\x90" * 5
	output_eq_code = bytearray(NATIVE_OUTPUT_EQ_CODE)
	struct.pack_into(
		"<I",
		output_eq_code,
		NATIVE_OUTPUT_EQ_STAGE_COUNT_OFFSET,
		3 if presence_enabled else 2,
	)
	struct.pack_into(
		"<15f",
		output_eq_code,
		NATIVE_OUTPUT_EQ_COEFFICIENT_OFFSET,
		*_native_output_eq_coefficients(presence_enabled),
	)
	modified_append = bytearray(append_new)
	table_suffix = append_new.find(TABLE_SUFFIX)
	if table_suffix < 8 or append_new.find(TABLE_SUFFIX, table_suffix + 1) >= 0:
		raise ValueError(f"Could not uniquely locate sibilance blend in {source}")
	blend_offset = table_suffix - 8
	if append_new[blend_offset : blend_offset + 4] != struct.pack("<f", 0.0):
		raise ValueError(f"Native sibilance blend was not found in {source}")
	if language in HISTORICAL_SIBILANCE_LANGUAGES:
		struct.pack_into(
			"<f",
			modified_append,
			blend_offset,
			HISTORICAL_SIBILANCE_BLEND,
		)
		blend_code_offset = append_new.find(VOICE_ONLY_BLEND_CODE)
		if (
			blend_code_offset < 0
			or append_new.find(VOICE_ONLY_BLEND_CODE, blend_code_offset + 1) >= 0
		):
			raise ValueError(f"Could not uniquely locate sibilance blend code in {source}")
		helper_in_append = entry_in_append + VOICE_ONLY_BLEND_HELPER_OFFSET
		helper_end = helper_in_append + len(VOICE_ONLY_BLEND_HELPER_CODE)
		if append_new[helper_in_append:helper_end] != b"\x90" * len(
			VOICE_ONLY_BLEND_HELPER_CODE
		):
			raise ValueError(f"Voiced-sibilance blend helper overlaps nonempty code in {source}")
		blend_call = b"\xe8" + struct.pack(
			"<i",
			helper_in_append - (blend_code_offset + 5),
		)
		modified_append[
			blend_code_offset : blend_code_offset + len(VOICE_ONLY_BLEND_CODE)
		] = blend_call + b"\x90" * (len(VOICE_ONLY_BLEND_CODE) - len(blend_call))
		modified_append[helper_in_append:helper_end] = VOICE_ONLY_BLEND_HELPER_CODE
		classifier_in_append = entry_in_append + SIBILANCE_CLASSIFIER_OFFSET
		classifier_end = classifier_in_append + len(SIBILANCE_CLASSIFIER_CODE)
		if append_new[classifier_in_append:classifier_end] != SIBILANCE_CLASSIFIER_CODE:
			raise ValueError(f"Original sibilance classifier was not found in {source}")
		composite_classifier_in_append = (
			entry_in_append + COMPOSITE_SIBILANCE_CLASSIFIER_OFFSET
		)
		composite_classifier_end = (
			composite_classifier_in_append + len(COMPOSITE_SIBILANCE_CLASSIFIER_CODE)
		)
		if append_new[
			composite_classifier_in_append:composite_classifier_end
		] != b"\x90" * len(
			COMPOSITE_SIBILANCE_CLASSIFIER_CODE
		):
			raise ValueError(f"Composite sibilance classifier overlaps nonempty code in {source}")
		classifier_call = b"\xe8" + struct.pack(
			"<i",
			composite_classifier_in_append - (classifier_in_append + 5),
		)
		modified_append[classifier_in_append:classifier_end] = (
			classifier_call + b"\x90" * (len(SIBILANCE_CLASSIFIER_CODE) - len(classifier_call))
		)
		modified_append[
			composite_classifier_in_append:composite_classifier_end
		] = COMPOSITE_SIBILANCE_CLASSIFIER_CODE
	voiced_s_hits = []
	search_from = 0
	while True:
		hit = append_new.find(VOICED_S_GAIN_TABLE_TAIL, search_from)
		if hit < 0:
			break
		voiced_s_hits.append(hit)
		search_from = hit + 1
	if len(voiced_s_hits) != 1 or voiced_s_hits[0] < 4:
		raise ValueError(f"Could not uniquely locate voiced-S gain table in {source}")
	voiced_s_gain_offset = voiced_s_hits[0]
	unvoiced_s_gain = append_new[voiced_s_gain_offset - 4 : voiced_s_gain_offset]
	modified_append[voiced_s_gain_offset : voiced_s_gain_offset + 4] = unvoiced_s_gain
	modified_append[b6_code_in_append : b6_code_in_append + len(base_b6_code)] = (
		_b6_bandwidth_code(b6_multiplier)
	)
	modified_append[code_in_append : code_in_append + len(code)] = code
	modified_append[output_eq_in_append:output_eq_end] = output_eq_code

	frication_return = entry_in_append + 0x100 + FRICATION_RETURN_TAIL_OFFSET
	if modified_append[frication_return : frication_return + len(FRICATION_RETURN_TAIL)] != (
		FRICATION_RETURN_TAIL
	):
		raise ValueError(f"Native-frication return tail was not found in {source}")
	if voiced_gain_db < 0.0:
		helper = _early_voiced_gain_code(voiced_gain_db)
		helper_in_append = entry_in_append + EARLY_VOICED_HELPER_OFFSET
		if modified_append[helper_in_append : helper_in_append + len(helper)] != b"\x90" * len(helper):
			raise ValueError(f"Early voiced-gain code cave is not empty in {source}")
		modified_append[helper_in_append : helper_in_append + len(helper)] = helper
	runs[append_index] = (append_offset, append_old, bytes(modified_append))

	final_hook_offset = count_runs[0][0] + FINAL_OUTPUT_HOOK_DELTA
	final_hook_target = (
		xflt_runtime_offset
		+ NATIVE_OUTPUT_EQ_OFFSET
		+ NATIVE_OUTPUT_EQ_PROCESS_OFFSET
	)
	call_displacement = final_hook_target - (final_hook_offset + 5)
	final_hook = b"\xe8" + struct.pack("<i", call_displacement) + b"\x90"
	runs.insert(
		append_index,
		(final_hook_offset, FINAL_BUFFER_COUNT_LOAD, final_hook),
	)
	if voiced_gain_db < 0.0:
		early_hook_offset = count_runs[0][0] + EARLY_VOICED_HOOK_DELTA
		early_hook_target = xflt_runtime_offset + EARLY_VOICED_HELPER_OFFSET
		early_call = b"\xe8" + struct.pack(
			"<i",
			early_hook_target - (early_hook_offset + 5),
		) + b"\x90"
		insert_at = next(
			(index for index, (offset, _old, _new) in enumerate(runs) if offset > early_hook_offset),
			append_index,
		)
		runs.insert(insert_at, (early_hook_offset, EARLY_VOICED_HOOK_OLD, early_call))
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
		for suffix, presence_enabled in ((".p16s0", False), (".p16s1", True)):
			make_sibilance_rolloff_patch(
				source.with_suffix(".p16st"),
				source.with_suffix(suffix),
				SIBILANCE_FILTER_GAIN_DB,
				SIBILANCE_FILTER_MAKEUP_DB,
				4.5,
				VOICED_GAIN_DB,
				presence_enabled,
			)


if __name__ == "__main__":
	main()
