import importlib.util
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = ROOT / "addon" / "synthDrivers" / "eloquence"
SCRIPT_PATH = ROOT / "tools" / "make_native_s_patches.py"


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
	assert len(builder.FRICATION_FILTER_CODE) == 572
	# d9b is an inline float array, not a stored pointer. The hook must pass
	# &engine->d9b (LEA), never interpret its first audio sample as an address.
	assert builder.FRICATION_FILTER_CODE[48:57] == bytes.fromhex("50518d969b0d000052")
	assert bytes.fromhex("ffb69b0d0000") not in builder.FRICATION_FILTER_CODE
	for wide_b6 in sorted(PATCH_DIR.glob("*.p16b40")):
		for suffix, hybrid in ((".p16fs", False), (".p16fu", True)):
			generated = tmp_path / wide_b6.with_suffix(suffix).name
			builder.make_native_frication_patch(wide_b6, generated, hybrid)
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
			assert call_target == original_size + code_offset
			code = append[code_offset : code_offset + len(builder.FRICATION_FILTER_CODE)]
			assert code[builder.FRICATION_FILTER_MODE_OFFSET] == int(hybrid)


def test_wide_b6_patches_apply_to_bundled_engines(tmp_path):
	builder = _load_patch_builder()
	for syn in sorted(PATCH_DIR.glob("*.syn")):
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
	for syn in sorted(PATCH_DIR.glob("*.syn")):
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
	for syn in sorted(PATCH_DIR.glob("*.syn")):
		for suffix in (".p16fs", ".p16fu"):
			patch = syn.with_suffix(suffix)
			original = bytearray(syn.read_bytes())
			original_size, patched_size, runs = builder._read_runs(patch.read_bytes())
			assert len(original) == original_size
			patched = original + bytearray(patched_size - original_size)
			for offset, old, new in runs:
				assert patched[offset : offset + len(old)] == old
				patched[offset : offset + len(new)] = new
