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


def test_wide_b6_patches_hook_only_the_sixth_bandwidth_load(tmp_path):
	builder = _load_patch_builder()
	for native_s in sorted(PATCH_DIR.glob("*.p16n")):
		for suffix, multiplier in ((".p16b15", 1.5), (".p16b20", 2.0)):
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


def test_wide_b6_patches_apply_to_bundled_engines(tmp_path):
	builder = _load_patch_builder()
	for syn in sorted(PATCH_DIR.glob("*.syn")):
		patch = syn.with_suffix(".p16b20")
		original = bytearray(syn.read_bytes())
		original_size, patched_size, runs = builder._read_runs(patch.read_bytes())
		assert len(original) == original_size
		patched = original + bytearray(patched_size - original_size)
		for offset, old, new in runs:
			assert patched[offset : offset + len(old)] == old
			patched[offset : offset + len(new)] = new
		hook = next(new for _offset, old, new in runs if old == builder.B6_LOAD)
		assert hook[:1] == b"\xe8"
