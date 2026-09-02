/*
 * Reference source for the position-independent x86 filter embedded by
 * make_native_s_patches.py. The committed patch generator contains the
 * assembled bytes, so building the NVDA add-on does not require a C compiler.
 */

void processNativeFrication(float *buffer, int count, float *state, int fullTreatment) {
	const float sampleScale = 1.0f / 32768.0f;
	const float svfG = 2.8837576798659024f;
	const float svfA1 = 0.097301717167033f;
	const float svfA2 = 0.2805945741445713f;
	const float notchB0 = 0.836756838857996f;
	const float notchB1 = 1.6413575816573207f;
	const float notchB2 = 0.836756838857996f;
	const float notchA1 = 1.6413575816573207f;
	const float notchA2 = 0.6735136777159921f;

	for (int i = 0; i < count; ++i) {
		float x = buffer[i];
		float absoluteX = x < 0.0f ? -x : x;
		float difference = x - state[0];
		float absoluteDifference = difference < 0.0f ? -difference : difference;
		float threshold = 150.0f * (0.2f + 0.8f * absoluteX * sampleScale);
		float ratio = absoluteDifference / (threshold + 0.000001f);
		if (ratio > 1.0f) {
			ratio = 1.0f;
		}
		float mix = 0.4f + 0.6f * ratio;
		x = state[0] + difference * mix;
		state[0] = x;

		if (fullTreatment) {
			float v1 = svfA1 * state[1] + svfA2 * (x - state[2]);
			float v2 = state[2] + svfG * v1;
			state[1] = 2.0f * v1 - state[1];
			state[2] = 2.0f * v2 - state[2];
			float presence = x + 2.0f * v1;

			float output = notchB0 * presence + state[3];
			state[3] = notchB1 * presence - notchA1 * output + state[4];
			state[4] = notchB2 * presence - notchA2 * output;
			/* Native 16 kHz noise contains far more true upper-band energy than
			 * the interpolated 11 kHz source, so compensate the presence stage. */
			x = output * 0.5f;
		}
		buffer[i] = x;
	}
}
