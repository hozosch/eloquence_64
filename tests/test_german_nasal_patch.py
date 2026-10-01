import struct

import pytest

from fetch_eci import GERMAN_NASAL_MIDRANGE_FIELDS, _rewrite_german_nasal_midrange_fields


def _fixture(values):
	data = bytearray(max(offset for offset, _old, _new in GERMAN_NASAL_MIDRANGE_FIELDS) + 2)
	for (offset, _old, _new), value in zip(GERMAN_NASAL_MIDRANGE_FIELDS, values):
		struct.pack_into("<H", data, offset, value)
	return bytes(data)


def test_german_nasal_midrange_uses_the_selected_v21_3_values():
	originals = [old for _offset, old, _new in GERMAN_NASAL_MIDRANGE_FIELDS]
	replacements = [new for _offset, _old, new in GERMAN_NASAL_MIDRANGE_FIELDS]
	patched = _rewrite_german_nasal_midrange_fields(_fixture(originals))
	assert [
		struct.unpack_from("<H", patched, offset)[0]
		for offset, _old, _new in GERMAN_NASAL_MIDRANGE_FIELDS
	] == replacements
	assert _rewrite_german_nasal_midrange_fields(patched) == patched


def test_german_nasal_midrange_rejects_an_unknown_layout():
	values = [old for _offset, old, _new in GERMAN_NASAL_MIDRANGE_FIELDS]
	values[2] = 1234
	with pytest.raises(ValueError, match="Unexpected DEU.SYN nasal value"):
		_rewrite_german_nasal_midrange_fields(_fixture(values))
