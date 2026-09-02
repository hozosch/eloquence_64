"""Small dependency-free filters for experimental native-rate comparisons."""

from __future__ import annotations

import array
import math


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
