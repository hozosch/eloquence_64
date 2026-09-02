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
