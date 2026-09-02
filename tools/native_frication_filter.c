/*
 * Reference source for the position-independent x86 filter embedded by
 * make_native_s_patches.py. The committed patch generator contains the
 * assembled bytes, so building the NVDA add-on does not require a C compiler.
 */

void processNativeFrication(float *buffer, int count, float *state, int hybrid) {
	/* Two cascaded high shelves form a broad consonant band.  The first one
	 * restores the 4--6.5 kHz energy measured in the 22 kHz reference; the
	 * second one controls the unnatural native noise close to the 8 kHz
	 * Nyquist limit.  Mode zero follows the reference more closely, while mode
	 * one deliberately retains more of native 16 kHz's upper-band clarity. */
	const float bandB0 = hybrid ? 1.311191840f : 1.458024495f;
	const float bandB1 = hybrid ? -0.3180013311f : -0.5567828729f;
	const float bandB2 = hybrid ? 0.2386238987f : 0.2879168242f;
	const float bandA1 = hybrid ? 0.05961324397f : 0.01753123939f;
	const float bandA2 = hybrid ? 0.1722011632f : 0.1716272071f;
	const float limitB0 = hybrid ? 0.8531379273f : 0.5941912212f;
	const float limitB1 = hybrid ? 1.352833304f : 0.9995731663f;
	const float limitB2 = hybrid ? 0.5612654804f : 0.4315151363f;
	const float limitA1 = hybrid ? 1.286267475f : 0.7519269033f;
	const float limitA2 = hybrid ? 0.4809692373f : 0.2733526205f;
	const float outputGain = hybrid ? 0.84f : 0.88f;

	for (int i = 0; i < count; ++i) {
		float x = buffer[i];
		float band = bandB0 * x + state[0];
		state[0] = bandB1 * x - bandA1 * band + state[1];
		state[1] = bandB2 * x - bandA2 * band;
		float limited = limitB0 * band + state[2];
		state[2] = limitB1 * band - limitA1 * limited + state[3];
		state[3] = limitB2 * band - limitA2 * limited;
		buffer[i] = limited * outputGain;
	}
}
