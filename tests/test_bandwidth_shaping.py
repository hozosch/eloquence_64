import importlib.util
import math
from array import array
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "addon" / "synthDrivers" / "_bandwidth_shaping.py"
SPEC = importlib.util.spec_from_file_location("_bandwidth_shaping", MODULE_PATH)
shaping = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shaping)


def _tone(frequency, sample_rate=16000, length=16000, amplitude=12000):
	return array(
		"h",
		(round(amplitude * math.sin(2.0 * math.pi * frequency * n / sample_rate)) for n in range(length)),
	).tobytes()


def _rms(data):
	samples = array("h")
	samples.frombytes(data)
	return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


class HighShelfFilterTests(unittest.TestCase):
	def test_preserves_low_band_and_attenuates_extension(self):
		filt = shaping.HighShelfFilter(16000, 5500, -6.0)
		low_ratio = _rms(filt.process(_tone(1000))) / _rms(_tone(1000))
		filt.reset()
		high_ratio = _rms(filt.process(_tone(7500))) / _rms(_tone(7500))
		self.assertGreater(low_ratio, 0.98)
		self.assertLess(high_ratio, 0.52)

	def test_chunk_boundaries_preserve_filter_state(self):
		data = _tone(7000, length=4000)
		whole = shaping.HighShelfFilter(16000, 5500, -3.0).process(data)
		chunked_filter = shaping.HighShelfFilter(16000, 5500, -3.0)
		chunked = chunked_filter.process(data[:3000]) + chunked_filter.process(data[3000:])
		self.assertEqual(whole, chunked)

	def test_rejects_frequency_at_nyquist(self):
		with self.assertRaises(ValueError):
			shaping.HighShelfFilter(16000, 8000, -3.0)

	def test_rejects_nonpositive_slope(self):
		with self.assertRaises(ValueError):
			shaping.HighShelfFilter(16000, 5500, -3.0, slope=0.0)


if __name__ == "__main__":
	unittest.main()
