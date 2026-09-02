import importlib.util
import math
from array import array
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "addon" / "synthDrivers" / "_bandwidth_shaping.py"
SPEC = importlib.util.spec_from_file_location("_bandwidth_shaping", MODULE_PATH)
shaping = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shaping)


def _tone(frequency, sample_rate=16000, length=16000, amplitude=2000):
	return array(
		"h",
		(round(amplitude * math.sin(2.0 * math.pi * frequency * n / sample_rate)) for n in range(length)),
	).tobytes()


def _rms(data):
	samples = array("h")
	samples.frombytes(data)
	return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


class HighShelfFilterTests(unittest.TestCase):
	def test_preserves_low_band_and_boosts_the_extension_by_ten_db(self):
		filt = shaping.HighShelfFilter(16000, 4800, 10.0)
		low_ratio = _rms(filt.process(_tone(1000))) / _rms(_tone(1000))
		filt.reset()
		high_ratio = _rms(filt.process(_tone(7500))) / _rms(_tone(7500))
		self.assertGreater(low_ratio, 0.98)
		self.assertLess(low_ratio, 1.02)
		self.assertGreater(high_ratio, 3.1)
		self.assertLess(high_ratio, 3.3)

	def test_chunk_boundaries_preserve_filter_state(self):
		data = _tone(7000, length=4000)
		whole = shaping.HighShelfFilter(16000, 4800, 10.0).process(data)
		chunked_filter = shaping.HighShelfFilter(16000, 4800, 10.0)
		chunked = chunked_filter.process(data[:3000]) + chunked_filter.process(data[3000:])
		self.assertEqual(whole, chunked)

	def test_saturates_instead_of_wrapping_on_overload(self):
		result = shaping.HighShelfFilter(16000, 4800, 10.0).process(_tone(7500, amplitude=20000))
		samples = array("h")
		samples.frombytes(result)
		self.assertLessEqual(max(samples), 32767)
		self.assertGreaterEqual(min(samples), -32768)

	def test_rejects_frequency_at_nyquist(self):
		with self.assertRaises(ValueError):
			shaping.HighShelfFilter(16000, 8000, 10.0)

	def test_rejects_nonpositive_slope(self):
		with self.assertRaises(ValueError):
			shaping.HighShelfFilter(16000, 4800, 10.0, slope=0.0)

	def test_cascaded_curve_preserves_state_across_chunks(self):
		stages = ((2700.0, 4.0, 1.0), (4800.0, 6.0, 1.2))
		data = _tone(4000, length=4000)
		whole = shaping.CascadedHighShelfFilter(16000, stages).process(data)
		chunked_filter = shaping.CascadedHighShelfFilter(16000, stages)
		chunked = chunked_filter.process(data[:3000]) + chunked_filter.process(data[3000:])
		self.assertEqual(whole, chunked)

	def test_cascaded_curve_starts_earlier_but_still_ends_at_ten_db(self):
		stages = ((2700.0, 4.0, 1.0), (4800.0, 6.0, 1.2))
		filt = shaping.CascadedHighShelfFilter(16000, stages)
		mid_ratio = _rms(filt.process(_tone(4000))) / _rms(_tone(4000))
		filt.reset()
		high_ratio = _rms(filt.process(_tone(7500))) / _rms(_tone(7500))
		self.assertGreater(mid_ratio, 1.65)
		self.assertLess(mid_ratio, 1.75)
		self.assertGreater(high_ratio, 3.1)
		self.assertLess(high_ratio, 3.3)


if __name__ == "__main__":
	unittest.main()
