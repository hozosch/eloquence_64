"""Small dependency-free filters for experimental native-rate comparisons."""

from __future__ import annotations

import array
import math
from typing import Sequence, Tuple


class HighShelfFilter:
	"""Stateful mono PCM16 high shelf based on the RBJ cookbook equations."""

	def __init__(self, sample_rate: int, frequency: float, gain_db: float, slope: float = 1.4) -> None:
		if not 0.0 < frequency < sample_rate / 2.0:
			raise ValueError("shelf frequency must be between DC and Nyquist")
		if slope <= 0.0:
			raise ValueError("shelf slope must be positive")
		a = 10.0 ** (gain_db / 40.0)
		w0 = 2.0 * math.pi * frequency / sample_rate
		cos_w0 = math.cos(w0)
		radical = (a + 1.0 / a) * (1.0 / slope - 1.0) + 2.0
		if radical <= 0.0:
			raise ValueError("shelf slope is too steep for this gain")
		alpha = math.sin(w0) * math.sqrt(radical) / 2.0
		two_sqrt_a_alpha = 2.0 * math.sqrt(a) * alpha
		a0 = (a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha
		self._b0 = a * ((a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha) / a0
		self._b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0) / a0
		self._b2 = a * ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
		self._a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0) / a0
		self._a2 = ((a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
		self.reset()

	def reset(self) -> None:
		self._z1 = 0.0
		self._z2 = 0.0

	def process(self, data: bytes) -> bytes:
		if not data or len(data) % 2:
			return data
		samples = array.array("h")
		samples.frombytes(data)
		z1 = self._z1
		z2 = self._z2
		for i, sample in enumerate(samples):
			y = self._b0 * sample + z1
			z1 = self._b1 * sample - self._a1 * y + z2
			z2 = self._b2 * sample - self._a2 * y
			samples[i] = max(-32768, min(32767, round(y)))
		self._z1 = z1
		self._z2 = z2
		return samples.tobytes()


class LowShelfFilter:
	"""Stateful mono PCM16 low shelf based on the RBJ cookbook equations."""

	def __init__(self, sample_rate: int, frequency: float, gain_db: float, slope: float = 1.0) -> None:
		if not 0.0 < frequency < sample_rate / 2.0:
			raise ValueError("shelf frequency must be between DC and Nyquist")
		if slope <= 0.0:
			raise ValueError("shelf slope must be positive")
		a = 10.0 ** (gain_db / 40.0)
		w0 = 2.0 * math.pi * frequency / sample_rate
		cos_w0 = math.cos(w0)
		radical = (a + 1.0 / a) * (1.0 / slope - 1.0) + 2.0
		if radical <= 0.0:
			raise ValueError("shelf slope is too steep for this gain")
		alpha = math.sin(w0) * math.sqrt(radical) / 2.0
		two_sqrt_a_alpha = 2.0 * math.sqrt(a) * alpha
		a0 = (a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha
		self._b0 = a * ((a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha) / a0
		self._b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0) / a0
		self._b2 = a * ((a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
		self._a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0) / a0
		self._a2 = ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha) / a0
		self.reset()

	def reset(self) -> None:
		self._z1 = 0.0
		self._z2 = 0.0

	def process(self, data: bytes) -> bytes:
		if not data or len(data) % 2:
			return data
		samples = array.array("h")
		samples.frombytes(data)
		z1 = self._z1
		z2 = self._z2
		for i, sample in enumerate(samples):
			y = self._b0 * sample + z1
			z1 = self._b1 * sample - self._a1 * y + z2
			z2 = self._b2 * sample - self._a2 * y
			samples[i] = max(-32768, min(32767, round(y)))
		self._z1 = z1
		self._z2 = z2
		return samples.tobytes()


class PeakingEQFilter:
	"""Stateful mono PCM16 peaking EQ based on the RBJ cookbook equations."""

	def __init__(self, sample_rate: int, frequency: float, gain_db: float, quality: float) -> None:
		if not 0.0 < frequency < sample_rate / 2.0:
			raise ValueError("peak frequency must be between DC and Nyquist")
		if quality <= 0.0:
			raise ValueError("peak quality must be positive")
		a = 10.0 ** (gain_db / 40.0)
		w0 = 2.0 * math.pi * frequency / sample_rate
		alpha = math.sin(w0) / (2.0 * quality)
		cos_w0 = math.cos(w0)
		a0 = 1.0 + alpha / a
		self._b0 = (1.0 + alpha * a) / a0
		self._b1 = (-2.0 * cos_w0) / a0
		self._b2 = (1.0 - alpha * a) / a0
		self._a1 = (-2.0 * cos_w0) / a0
		self._a2 = (1.0 - alpha / a) / a0
		self.reset()

	def reset(self) -> None:
		self._z1 = 0.0
		self._z2 = 0.0

	def process(self, data: bytes) -> bytes:
		if not data or len(data) % 2:
			return data
		samples = array.array("h")
		samples.frombytes(data)
		z1 = self._z1
		z2 = self._z2
		for i, sample in enumerate(samples):
			y = self._b0 * sample + z1
			z1 = self._b1 * sample - self._a1 * y + z2
			z2 = self._b2 * sample - self._a2 * y
			samples[i] = max(-32768, min(32767, round(y)))
		self._z1 = z1
		self._z2 = z2
		return samples.tobytes()


class FilterChain:
	"""Run several stateful PCM filters as one resettable filter."""

	def __init__(self, filters: Sequence[object]) -> None:
		self._filters = tuple(filters)

	def reset(self) -> None:
		for filt in self._filters:
			filt.reset()

	def process(self, data: bytes) -> bytes:
		for filt in self._filters:
			data = filt.process(data)
		return data


class CascadedHighShelfFilter:
	"""Apply several shelves as one continuous comparison curve."""

	def __init__(self, sample_rate: int, stages: Sequence[Tuple[float, float, float]]) -> None:
		self._stages = [HighShelfFilter(sample_rate, frequency, gain_db, slope) for frequency, gain_db, slope in stages]

	def reset(self) -> None:
		for stage in self._stages:
			stage.reset()

	def process(self, data: bytes) -> bytes:
		for stage in self._stages:
			data = stage.process(data)
		return data


class VoicedHighShelfFilter:
	"""Blend a shelf in only while the signal has voiced, low-band energy."""

	def __init__(
		self,
		sample_rate: int,
		stages: Sequence[Tuple[float, float, float]],
		lowpass_frequency: float = 1400.0,
	) -> None:
		self._wet = CascadedHighShelfFilter(sample_rate, stages)
		self._lowpass_coefficient = 1.0 - math.exp(-2.0 * math.pi * lowpass_frequency / sample_rate)
		self._energy_coefficient = 1.0 - math.exp(-1.0 / (sample_rate * 0.0025))
		self._attack_coefficient = 1.0 - math.exp(-1.0 / (sample_rate * 0.010))
		self._release_coefficient = 1.0 - math.exp(-1.0 / (sample_rate * 0.003))
		self.reset()

	def reset(self) -> None:
		self._wet.reset()
		self._lowpass = 0.0
		self._low_energy = 0.0
		self._total_energy = 0.0
		self._mix = 0.0

	def process(self, data: bytes) -> bytes:
		if not data or len(data) % 2:
			return data
		dry = array.array("h")
		dry.frombytes(data)
		wet = array.array("h")
		wet.frombytes(self._wet.process(data))
		lowpass = self._lowpass
		low_energy = self._low_energy
		total_energy = self._total_energy
		mix = self._mix
		for i, sample in enumerate(dry):
			lowpass += self._lowpass_coefficient * (sample - lowpass)
			low_energy += self._energy_coefficient * (lowpass * lowpass - low_energy)
			total_energy += self._energy_coefficient * (sample * sample - total_energy)
			if total_energy < 256.0:
				target = 0.0
			else:
				ratio = low_energy / total_energy
				target = max(0.0, min(1.0, (ratio - 0.38) / 0.30))
				# A smoothstep avoids a hard tonal/noise boundary.
				target = target * target * (3.0 - 2.0 * target)
			coefficient = self._attack_coefficient if target > mix else self._release_coefficient
			mix += coefficient * (target - mix)
			value = sample + mix * (wet[i] - sample)
			dry[i] = max(-32768, min(32767, round(value)))
		self._lowpass = lowpass
		self._low_energy = low_energy
		self._total_energy = total_energy
		self._mix = mix
		return dry.tobytes()
