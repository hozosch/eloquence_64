import cmath
import importlib.util
import math
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = ROOT / "addon" / "synthDrivers" / "eloquence"
SCRIPT_PATH = ROOT / "tools" / "make_native_s_patches.py"


def _bundled_syns():
	# Windows globbing is case-insensitive, so the two patterns can return the
	# same file twice. Path equality follows the platform's case rules.
	return sorted(set(PATCH_DIR.glob("*.syn")) | set(PATCH_DIR.glob("*.SYN")))


def _pe_rva_for_raw_offset(data: bytes, raw_offset: int) -> int:
	pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
	assert data[pe_offset : pe_offset + 4] == b"PE\0\0"
	section_count = struct.unpack_from("<H", data, pe_offset + 6)[0]
	optional_header_size = struct.unpack_from("<H", data, pe_offset + 20)[0]
	section_table = pe_offset + 24 + optional_header_size
	for index in range(section_count):
		header = section_table + index * 40
		virtual_address = struct.unpack_from("<I", data, header + 12)[0]
		raw_size = struct.unpack_from("<I", data, header + 16)[0]
		raw_pointer = struct.unpack_from("<I", data, header + 20)[0]
		if raw_pointer <= raw_offset < raw_pointer + raw_size:
			return virtual_address + raw_offset - raw_pointer
	raise AssertionError(f"Raw offset {raw_offset:#x} is not inside a PE section")


def _load_patch_builder():
	spec = importlib.util.spec_from_file_location("make_native_s_patches", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	spec.loader.exec_module(module)
	return module


def test_native_s_patches_only_disable_the_shaped_s_blend(tmp_path):
	builder = _load_patch_builder()
	sources = sorted(PATCH_DIR.glob("*.p16"))
	assert len(sources) == 13

	for source in sources:
		generated = tmp_path / source.with_suffix(".p16n").name
		builder.make_native_s_patch(source, generated)
		committed = source.with_suffix(".p16n")
		assert generated.read_bytes() == committed.read_bytes()

		original = source.read_bytes()
		native_s = committed.read_bytes()
		assert len(original) == len(native_s)
		suffix_offset = original.index(builder.TABLE_SUFFIX)
		blend_offset = suffix_offset - 8
		assert struct.unpack_from("<f", native_s, blend_offset)[0] == 0.0
		assert original[:blend_offset] == native_s[:blend_offset]
		assert original[blend_offset + 4 :] == native_s[blend_offset + 4 :]


def test_five_cascade_patches_only_restore_the_original_cascade_count(tmp_path):
	builder = _load_patch_builder()
	for native_s in sorted(PATCH_DIR.glob("*.p16n")):
		generated = tmp_path / native_s.with_suffix(".p16b5").name
		builder.make_five_cascade_patch(native_s, generated)
		committed = native_s.with_suffix(".p16b5")
		assert generated.read_bytes() == committed.read_bytes()

		six_cascades = native_s.read_bytes()
		five_cascades = committed.read_bytes()
		differences = [i for i, pair in enumerate(zip(six_cascades, five_cascades)) if pair[0] != pair[1]]
		assert len(differences) == 1
		assert six_cascades[differences[0]] == 6
		assert five_cascades[differences[0]] == 5
		# The first run expands the PE section count from five to six. It must be
		# unchanged so the injected .xflt code remains mapped and executable.
		assert six_cascades[29] == 6
		assert five_cascades[29] == 6
		assert differences[0] != 29


def test_six_parallel_formant_patches_split_voice_and_consonant_counts(tmp_path):
	builder = _load_patch_builder()
	for native_s in sorted(PATCH_DIR.glob("*.p16n")):
		generated = tmp_path / native_s.with_suffix(".p16c6").name
		builder.make_six_parallel_formant_patch(native_s, generated)
		committed = native_s.with_suffix(".p16c6")
		assert generated.read_bytes() == committed.read_bytes()

		_original_size, _patched_size, runs = builder._read_runs(committed.read_bytes())
		cascade_run = next(run for run in runs if run[1] == b"\x8b\x85\x36\x0a")
		assert cascade_run[2] == b"\xb8\x06\x00\x00"
		voice_run = next(run for run in runs if run[1] == builder.CASCADE_PROCESS_COUNT_LOAD)
		assert voice_run[2] == b"\xb8\x05\x00\x00\x00\x90"
		assert voice_run[0] == cascade_run[0] + 0x1A79


def test_wide_b6_patches_hook_only_the_sixth_bandwidth_load(tmp_path):
	builder = _load_patch_builder()
	for native_s in sorted(PATCH_DIR.glob("*.p16n")):
		for suffix, multiplier in ((".p16b15", 1.5), (".p16b20", 2.0), (".p16b30", 3.0), (".p16b40", 4.0)):
			generated = tmp_path / native_s.with_suffix(suffix).name
			builder.make_b6_bandwidth_patch(native_s, generated, multiplier)
			committed = native_s.with_suffix(suffix)
			assert generated.read_bytes() == committed.read_bytes()

			_original_size, _patched_size, base_runs = builder._read_runs(native_s.read_bytes())
			_original_size, _patched_size, wide_runs = builder._read_runs(committed.read_bytes())
			extra_runs = [run for run in wide_runs if run not in base_runs]
			assert any(old == builder.B6_LOAD and new[:1] == b"\xe8" for _off, old, new in extra_runs)
			append = next(new for _off, old, new in wide_runs if not old and builder.XFLT_ENTRY in new)
			code_offset = append.index(builder.XFLT_ENTRY) + 0x60
			assert struct.unpack_from("<f", append, code_offset + 4)[0] == multiplier


def test_native_frication_patches_use_the_internal_noise_buffer(tmp_path):
	builder = _load_patch_builder()
	assert len(builder.FRICATION_FILTER_CODE) == 488
	# d9b is an inline float array, not a stored pointer. The hook must pass
	# &engine->d9b (LEA), never interpret its first audio sample as an address.
	assert builder.FRICATION_FILTER_CODE[51:60] == bytes.fromhex("50518d969b0d000052")
	assert bytes.fromhex("ffb69b0d0000") not in builder.FRICATION_FILTER_CODE
	for wide_b6 in sorted(PATCH_DIR.glob("*.p16b40")):
		for suffix, full_treatment in ((".p16fs", False), (".p16fu", True)):
			generated = tmp_path / wide_b6.with_suffix(suffix).name
			builder.make_native_frication_patch(wide_b6, generated, full_treatment)
			committed = wide_b6.with_suffix(suffix)
			assert generated.read_bytes() == committed.read_bytes()

			original_size, _patched_size, runs = builder._read_runs(committed.read_bytes())
			count_run = next(run for run in runs if run[1] == b"\x8b\x85\x36\x0a")
			frication_run = next(run for run in runs if run[1] == builder.FRICATION_BUFFER_LOAD)
			assert frication_run[0] == count_run[0] + 0x1D90
			assert frication_run[2][:1] == b"\xe8"

			append = next(new for offset, old, new in runs if offset == original_size and not old)
			code_offset = append.index(builder.XFLT_ENTRY) + 0x100
			call_target = frication_run[0] + 5 + struct.unpack_from("<i", frication_run[2], 1)[0]
			assert call_target == builder._xflt_runtime_offset(runs, committed) + 0x100
			code = append[code_offset : code_offset + len(builder.FRICATION_FILTER_CODE)]
			assert code[builder.FRICATION_FILTER_MODE_OFFSET] == int(full_treatment)


def test_frication_hooks_account_for_pe_raw_to_runtime_differences():
	builder = _load_patch_builder()
	deltas = {}
	for wide_b6 in sorted(PATCH_DIR.glob("*.p16b40")):
		original_size, _patched_size, runs = builder._read_runs(wide_b6.read_bytes())
		append = next(new for offset, old, new in runs if offset == original_size and not old)
		raw_offset = original_size + append.index(builder.XFLT_ENTRY)
		deltas[wide_b6.stem] = builder._xflt_runtime_offset(runs, wide_b6) - raw_offset
	assert deltas == {
		"DEU": 0,
		"ENG": 0x1000,
		"ENU": 0,
		"ESM": 0,
		"ESP": 0,
		"FIN": 0x1000,
		"FRA": 0,
		"FRC": 0,
		"ITA": 0,
		"PTB": 0x1000,
		"chs": -0x1000,
		"jpn": -0x2000,
		"kor": -0x2000,
	}


def test_frication_calls_reach_mapped_filter_code_in_every_engine():
	builder = _load_patch_builder()
	for syn in _bundled_syns():
		for suffix in (".p16fs", ".p16fu", ".p16st"):
			patch = syn.with_suffix(suffix)
			original_size, patched_size, runs = builder._read_runs(patch.read_bytes())
			patched = bytearray(syn.read_bytes()) + bytearray(patched_size - original_size)
			for offset, old, new in runs:
				assert patched[offset : offset + len(old)] == old
				patched[offset : offset + len(new)] = new

			append = next(new for offset, old, new in runs if offset == original_size and not old)
			entry = append.index(builder.XFLT_ENTRY)
			frication_run = next(run for run in runs if run[1] == builder.FRICATION_BUFFER_LOAD)
			source_rva = _pe_rva_for_raw_offset(patched, frication_run[0])
			actual_target_rva = source_rva + 5 + struct.unpack_from("<i", frication_run[2], 1)[0]
			expected_target_rva = _pe_rva_for_raw_offset(patched, original_size + entry + 0x100)
			assert actual_target_rva == expected_target_rva, (syn.name, suffix)


def test_split_frication_patches_use_real_direct_and_parallel_branches(tmp_path):
	builder = _load_patch_builder()
	assert len(builder.SPLIT_FRICATION_FILTER_CODE) == 496
	for wide_b6 in sorted(PATCH_DIR.glob("*.p16b40")):
		generated = tmp_path / wide_b6.with_suffix(".p16st").name
		builder.make_targeted_consonant_damping_patch(wide_b6, generated)
		committed = wide_b6.with_suffix(".p16st")
		assert generated.read_bytes() == committed.read_bytes()

		original_size, _patched_size, runs = builder._read_runs(committed.read_bytes())
		mode19_original_size, _mode19_patched_size, mode19_runs = builder._read_runs(
			wide_b6.with_suffix(".p16fu").read_bytes()
		)
		assert mode19_original_size == original_size

		count_run = next(run for run in runs if run[1] == b"\x8b\x85\x36\x0a")
		parallel_offset = count_run[0] + builder.PARALLEL_MIXER_RUN_DELTA
		assert [run for run in runs if run[0] not in (original_size, parallel_offset)] == [
			run for run in mode19_runs if run[0] not in (original_size, parallel_offset)
		]
		full_run = next(run for run in runs if run[1] == builder.FRICATION_BUFFER_LOAD)
		assert full_run[0] == count_run[0] + 0x1D90

		append = next(new for offset, old, new in runs if offset == original_size and not old)
		mode19_append = next(new for offset, old, new in mode19_runs if offset == original_size and not old)
		entry = append.index(builder.XFLT_ENTRY)
		assert mode19_append.index(builder.XFLT_ENTRY) == entry
		filter_offset = entry + 0x100
		mode20_filter = append[filter_offset : filter_offset + len(builder.FRICATION_FILTER_CODE)]
		mode19_filter = mode19_append[filter_offset : filter_offset + len(builder.FRICATION_FILTER_CODE)]
		assert mode20_filter[builder.FRICATION_FILTER_MODE_OFFSET] == 1
		assert mode19_filter[builder.FRICATION_FILTER_MODE_OFFSET] == 1

		process_call = builder.FRICATION_PROCESS_CALL_OFFSET
		process_target = 0x100 + process_call + 5 + struct.unpack_from("<i", mode20_filter, process_call + 1)[0]
		assert process_target == builder.FRICATION_PROCESS_OFFSET
		assert mode20_filter[process_call : process_call + 5] == mode19_filter[process_call : process_call + 5]
		assert mode20_filter[process_call + 5 :] == mode19_filter[process_call + 5 :]

		inactive_tail = builder.FRICATION_INACTIVE_TAIL_OFFSET
		assert mode19_filter[inactive_tail : inactive_tail + len(builder.FRICATION_INACTIVE_TAIL)] == (
			builder.FRICATION_INACTIVE_TAIL
		)
		reset_target = 0x100 + inactive_tail + 5 + struct.unpack_from("<i", mode20_filter, inactive_tail + 1)[0]
		assert reset_target == builder.SPLIT_FILTER_BLOCK_OFFSET

		code_offset = entry + builder.SPLIT_FILTER_BLOCK_OFFSET
		assert append[code_offset : code_offset + len(builder.SPLIT_FRICATION_FILTER_CODE)] == (
			builder.SPLIT_FRICATION_FILTER_CODE
		)
		# The original stage mixer, including its dedicated stage-5/6 s/t branch,
		# remains byte-identical. The new wrapper reaches only stages 1--4.
		assert append[entry + 0x600 : entry + 0x808] == mode19_append[entry + 0x600 : entry + 0x808]

		direct_tail = entry + builder.DIRECT_TAIL_OFFSET
		assert mode19_append[direct_tail : direct_tail + len(builder.DIRECT_TAIL)] == builder.DIRECT_TAIL
		direct_target = (
			builder.DIRECT_TAIL_OFFSET
			+ 5
			+ struct.unpack_from("<i", append, direct_tail + 1)[0]
		)
		assert direct_target == builder.DIRECT_FILTER_PROCESS_OFFSET

		parallel_run = next(run for run in runs if run[0] == parallel_offset)
		mode19_parallel_run = next(run for run in mode19_runs if run[0] == parallel_offset)
		assert parallel_run[1] == mode19_parallel_run[1]
		assert parallel_run[2][5:] == mode19_parallel_run[2][5:]
		parallel_target = parallel_offset + 5 + struct.unpack_from("<i", parallel_run[2], 1)[0]
		mode19_parallel_target = parallel_offset + 5 + struct.unpack_from("<i", mode19_parallel_run[2], 1)[0]
		assert parallel_target == builder._xflt_runtime_offset(runs, committed) + builder.PARALLEL_FILTER_PROCESS_OFFSET
		assert mode19_parallel_target == (
			builder._xflt_runtime_offset(mode19_runs, wide_b6.with_suffix(".p16fu"))
			+ builder.ORIGINAL_PARALLEL_MIXER_OFFSET
		)

		parallel_tail = builder.SPLIT_FRICATION_FILTER_CODE.rfind(b"\x61\xe9") + 1
		assert parallel_tail > 1
		parallel_tail_target = (
			builder.SPLIT_FILTER_BLOCK_OFFSET
			+ parallel_tail
			+ 5
			+ struct.unpack_from("<i", builder.SPLIT_FRICATION_FILTER_CODE, parallel_tail + 1)[0]
		)
		assert parallel_tail_target == builder.ORIGINAL_PARALLEL_MIXER_OFFSET

		differences = {i for i, pair in enumerate(zip(append, mode19_append)) if pair[0] != pair[1]}
		assert differences
		allowed_differences = set(range(code_offset, code_offset + len(builder.SPLIT_FRICATION_FILTER_CODE)))
		allowed_differences |= set(range(filter_offset + inactive_tail, filter_offset + inactive_tail + 8))
		allowed_differences |= set(range(direct_tail, direct_tail + 5))
		assert differences <= allowed_differences
		assert all(
			struct.pack("<f", coefficient) in builder.SPLIT_FRICATION_FILTER_CODE
			for coefficient in builder.SPLIT_BAND_COEFFICIENTS
		)
		assert struct.pack("<f", builder.DIRECT_PATH_GAIN) in builder.SPLIT_FRICATION_FILTER_CODE
		# The direct path and parallel stages 1--4 read the exact current target
		# flags of stages 5/6. They do not use the interpolated stage gains or a
		# time-based hold that could leak into an adjacent consonant.
		parallel_entry = builder.PARALLEL_FILTER_PROCESS_OFFSET - builder.SPLIT_FILTER_BLOCK_OFFSET
		direct_code = builder.SPLIT_FRICATION_FILTER_CODE[:parallel_entry]
		parallel_code = builder.SPLIT_FRICATION_FILTER_CODE[parallel_entry:]
		assert bytes.fromhex("b90a000000f3ab") in direct_code
		direct_stage_5_target = direct_code.index(bytes.fromhex("83bc240001000000"))
		direct_stage_6_target = direct_code.index(bytes.fromhex("83bc240401000000"))
		direct_state_clear = direct_code.index(bytes.fromhex("31c089829e0100008982a2010000"))
		assert direct_stage_5_target < direct_stage_6_target < direct_state_clear

		stage_selector = parallel_code.index(
			bytes.fromhex("89d883e80d83f803")
		)
		saved_outer_stack = parallel_code.index(bytes.fromhex("8b54240c"))
		stage_5_target = parallel_code.index(bytes.fromhex("83baf400000000"))
		stage_6_target = parallel_code.index(bytes.fromhex("83baf800000000"))
		assert stage_selector < saved_outer_stack < stage_5_target < stage_6_target
		assert bytes.fromhex("83be5318000000") not in builder.SPLIT_FRICATION_FILTER_CODE
		assert bytes.fromhex("8b86ee050000") not in builder.SPLIT_FRICATION_FILTER_CODE
		assert bytes.fromhex("8b863e060000") not in builder.SPLIT_FRICATION_FILTER_CODE
		assert builder.SIBILANCE_TARGET_STACK_OFFSETS == (0xF0, 0xF4)
		full_target = full_run[0] + 5 + struct.unpack_from("<i", full_run[2], 1)[0]
		assert full_target == builder._xflt_runtime_offset(runs, committed) + 0x100


def test_targeted_spectral_pivot_raises_lows_and_rolls_off_upper_frication():
	builder = _load_patch_builder()
	tilt = builder.SPLIT_BAND_COEFFICIENTS

	def response_db(frequency):
		z = cmath.exp(-2j * math.pi * frequency / 16000)

		def biquad_response(coefficients):
			b0, b1, b2, a1, a2 = coefficients
			return (b0 + b1 * z + b2 * z * z) / (1 + a1 * z + a2 * z * z)

		response = biquad_response(tilt)
		return 20 * math.log10(abs(response))

	assert 5.9 < response_db(0) < 6.1
	assert 5.4 < response_db(2000) < 5.7
	assert 3.4 < response_db(3000) < 3.8
	assert -0.7 < response_db(4000) < -0.3
	assert -5.6 < response_db(5000) < -5.2
	assert -9.1 < response_db(6000) < -8.7
	assert -10.1 < response_db(7000) < -9.8
	assert -10.1 < response_db(8000) < -9.9


def test_direct_frication_branch_is_two_decibels_quieter_than_ch_and_sch():
	builder = _load_patch_builder()
	assert -2.01 < 20 * math.log10(builder.DIRECT_PATH_GAIN) < -1.99


def test_wide_b6_patches_apply_to_bundled_engines(tmp_path):
	builder = _load_patch_builder()
	assert len(_bundled_syns()) == 13
	for syn in _bundled_syns():
		for suffix in (".p16b15", ".p16b20", ".p16b30", ".p16b40"):
			patch = syn.with_suffix(suffix)
			original = bytearray(syn.read_bytes())
			original_size, patched_size, runs = builder._read_runs(patch.read_bytes())
			assert len(original) == original_size
			patched = original + bytearray(patched_size - original_size)
			for offset, old, new in runs:
				assert patched[offset : offset + len(old)] == old
				patched[offset : offset + len(new)] = new
			hook = next(new for _offset, old, new in runs if old == builder.B6_LOAD)
			assert hook[:1] == b"\xe8"


def test_six_parallel_formant_patches_apply_to_bundled_engines():
	builder = _load_patch_builder()
	assert len(_bundled_syns()) == 13
	for syn in _bundled_syns():
		patch = syn.with_suffix(".p16c6")
		original = bytearray(syn.read_bytes())
		original_size, patched_size, runs = builder._read_runs(patch.read_bytes())
		assert len(original) == original_size
		patched = original + bytearray(patched_size - original_size)
		for offset, old, new in runs:
			assert patched[offset : offset + len(old)] == old
			patched[offset : offset + len(new)] = new


def test_native_frication_patches_apply_to_bundled_engines():
	builder = _load_patch_builder()
	assert len(_bundled_syns()) == 13
	for syn in _bundled_syns():
		for suffix in (".p16fs", ".p16fu"):
			patch = syn.with_suffix(suffix)
			original = bytearray(syn.read_bytes())
			original_size, patched_size, runs = builder._read_runs(patch.read_bytes())
			assert len(original) == original_size
			patched = original + bytearray(patched_size - original_size)
			for offset, old, new in runs:
				assert patched[offset : offset + len(old)] == old
				patched[offset : offset + len(new)] = new


def test_split_frication_patches_apply_with_mapped_targets_to_all_engines():
	builder = _load_patch_builder()
	syns = _bundled_syns()
	assert len(syns) == 13
	for syn in syns:
		patch = syn.with_suffix(".p16st")
		original = bytearray(syn.read_bytes())
		original_size, patched_size, runs = builder._read_runs(patch.read_bytes())
		assert len(original) == original_size
		patched = original + bytearray(patched_size - original_size)
		for offset, old, new in runs:
			assert patched[offset : offset + len(old)] == old
			patched[offset : offset + len(new)] = new

		append = next(new for offset, old, new in runs if offset == original_size and not old)
		entry = append.index(builder.XFLT_ENTRY)
		internal_calls = (
			(
				0x100 + builder.FRICATION_PROCESS_CALL_OFFSET,
				builder.FRICATION_PROCESS_OFFSET,
			),
			(
				0x100 + builder.FRICATION_INACTIVE_TAIL_OFFSET,
				builder.SPLIT_FILTER_BLOCK_OFFSET,
			),
			(builder.DIRECT_TAIL_OFFSET, builder.DIRECT_FILTER_PROCESS_OFFSET),
		)
		for source_offset, target_offset in internal_calls:
			source_raw = original_size + entry + source_offset
			source_rva = _pe_rva_for_raw_offset(patched, source_raw)
			assert patched[source_raw] == 0xE8
			actual_target_rva = source_rva + 5 + struct.unpack_from("<i", patched, source_raw + 1)[0]
			expected_target_rva = _pe_rva_for_raw_offset(patched, original_size + entry + target_offset)
			assert actual_target_rva == expected_target_rva, (syn.name, source_offset)

		count_run = next(run for run in runs if run[1] == b"\x8b\x85\x36\x0a")
		count_offset = count_run[0]
		# Every language engine computes the current (unsmoothed) stage-5/6
		# targets into the same two synthesis-frame slots. Later, the stock mixer
		# reads the matching per-stage slot through EBP before it decays the gain.
		assert original[count_offset + 0x46C : count_offset + 0x473] == bytes.fromhex(
			"898424f0000000"
		), syn.name
		assert original[count_offset + 0x4EC : count_offset + 0x4F3] == bytes.fromhex(
			"898424f4000000"
		), syn.name
		assert original[count_offset + 0x1DFE : count_offset + 0x1E05] == bytes.fromhex(
			"8dac24e0000000"
		), syn.name
		assert original[count_offset + 0x1E91 : count_offset + 0x1E94] == bytes.fromhex(
			"db4500"
		), syn.name
		parallel_source = count_run[0] + builder.PARALLEL_MIXER_RUN_DELTA
		parallel_run = next(run for run in runs if run[0] == parallel_source)
		assert parallel_run[2][:1] == b"\xe8"
		parallel_source_rva = _pe_rva_for_raw_offset(patched, parallel_source)
		parallel_target_rva = parallel_source_rva + 5 + struct.unpack_from("<i", patched, parallel_source + 1)[0]
		expected_parallel_rva = _pe_rva_for_raw_offset(
			patched,
			original_size + entry + builder.PARALLEL_FILTER_PROCESS_OFFSET,
		)
		assert parallel_target_rva == expected_parallel_rva, syn.name
