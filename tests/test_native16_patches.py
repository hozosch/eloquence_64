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
