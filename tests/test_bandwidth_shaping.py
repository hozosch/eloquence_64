import importlib.util
import math
import random
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


def _mixed_tone(length=16000):
	return array(
		"h",
		(
			round(
				2000 * math.sin(2.0 * math.pi * 200 * n / 16000)
				+ 500 * math.sin(2.0 * math.pi * 7000 * n / 16000)
			)
			for n in range(length)
		),
	).tobytes()


def _tone_amplitude(data, frequency, sample_rate=16000):
	samples = array("h")
	samples.frombytes(data)
	sine = sum(sample * math.sin(2.0 * math.pi * frequency * n / sample_rate) for n, sample in enumerate(samples))
	cosine = sum(sample * math.cos(2.0 * math.pi * frequency * n / sample_rate) for n, sample in enumerate(samples))
	return 2.0 * math.hypot(sine, cosine) / len(samples)


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


class PeakingEQFilterTests(unittest.TestCase):
	def test_boost_is_centered_at_four_khz_without_raising_the_top(self):
		def gain_db(frequency):
			data = _tone(frequency)
			result = shaping.PeakingEQFilter(16000, 4000.0, 8.0, 2.0).process(data)
			return 20.0 * math.log10(_rms(result) / _rms(data))

		self.assertAlmostEqual(gain_db(4000), 8.0, delta=0.15)
		self.assertAlmostEqual(gain_db(3000), 2.23, delta=0.15)
		self.assertLess(gain_db(7000), 0.2)

	def test_chunk_boundaries_preserve_filter_state(self):
		data = _tone(4000, length=4000)
		whole = shaping.PeakingEQFilter(16000, 4000.0, 8.0, 2.0).process(data)
		chunked_filter = shaping.PeakingEQFilter(16000, 4000.0, 8.0, 2.0)
		chunked = chunked_filter.process(data[:3000]) + chunked_filter.process(data[3000:])
		self.assertEqual(whole, chunked)

	def test_rejects_nonpositive_quality(self):
		with self.assertRaises(ValueError):
			shaping.PeakingEQFilter(16000, 4000.0, 8.0, 0.0)


class CascadedHighShelfFilterTests(unittest.TestCase):

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

	def test_measured_voiced_balance_matches_reference_curve(self):
		filt = shaping.CascadedHighShelfFilter(16000, ((3430.0, 8.0, 0.406),))
		two_khz_ratio = _rms(filt.process(_tone(2000))) / _rms(_tone(2000))
		filt.reset()
		four_khz_ratio = _rms(filt.process(_tone(4000))) / _rms(_tone(4000))
		filt.reset()
		seven_khz_ratio = _rms(filt.process(_tone(7000))) / _rms(_tone(7000))
		self.assertAlmostEqual(20.0 * math.log10(two_khz_ratio), 2.1, delta=0.15)
		self.assertAlmostEqual(20.0 * math.log10(four_khz_ratio), 4.7, delta=0.15)
		self.assertAlmostEqual(20.0 * math.log10(seven_khz_ratio), 7.7, delta=0.15)

	def test_upper_mid_window_adds_body_without_more_high_frequency_gain(self):
		stages = (
			(3430.0, 8.0, 0.406),
			(1800.0, 3.0, 1.0),
			(6000.0, -3.0, 1.0),
		)
		filt = shaping.CascadedHighShelfFilter(16000, stages)
		two_khz_ratio = _rms(filt.process(_tone(2000))) / _rms(_tone(2000))
		filt.reset()
		four_khz_ratio = _rms(filt.process(_tone(4000))) / _rms(_tone(4000))
		filt.reset()
		seven_khz_ratio = _rms(filt.process(_tone(7000))) / _rms(_tone(7000))
		self.assertAlmostEqual(20.0 * math.log10(two_khz_ratio), 3.9, delta=0.15)
		self.assertAlmostEqual(20.0 * math.log10(four_khz_ratio), 7.6, delta=0.15)
		self.assertAlmostEqual(20.0 * math.log10(seven_khz_ratio), 7.9, delta=0.15)

	def test_voiced_only_shelf_leaves_unvoiced_highband_native(self):
		data = _tone(7000)
		result = shaping.VoicedHighShelfFilter(16000, ((3430.0, 8.0, 0.406),)).process(data)
		half = len(data) // 2
		self.assertAlmostEqual(_rms(result[half:]) / _rms(data[half:]), 1.0, delta=0.01)

	def test_voiced_only_shelf_leaves_broadband_noise_native(self):
		rng = random.Random(1)
		data = array("h", (rng.randrange(-2000, 2001) for _ in range(16000))).tobytes()
		result = shaping.VoicedHighShelfFilter(16000, ((3430.0, 8.0, 0.406),)).process(data)
		half = len(data) // 2
		self.assertAlmostEqual(_rms(result[half:]) / _rms(data[half:]), 1.0, delta=0.01)

	def test_voiced_only_shelf_boosts_tonal_audio(self):
		data = _mixed_tone()
		result = shaping.VoicedHighShelfFilter(16000, ((3430.0, 8.0, 0.406),)).process(data)
		half = len(data) // 2
		self.assertGreater(_tone_amplitude(result[half:], 7000), _tone_amplitude(data[half:], 7000) * 2.3)
		self.assertAlmostEqual(_tone_amplitude(result[half:], 200), _tone_amplitude(data[half:], 200), delta=15.0)

	def test_voiced_only_shelf_preserves_state_across_chunks(self):
		data = _mixed_tone(length=4000) + _tone(7000, length=4000)
		whole = shaping.VoicedHighShelfFilter(16000, ((3430.0, 8.0, 0.406),)).process(data)
		chunked_filter = shaping.VoicedHighShelfFilter(16000, ((3430.0, 8.0, 0.406),))
		chunked = chunked_filter.process(data[:5000]) + chunked_filter.process(data[5000:])
		self.assertEqual(whole, chunked)


if __name__ == "__main__":
	unittest.main()
