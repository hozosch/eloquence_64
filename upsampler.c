#include <stdint.h>
#include <math.h>

/**
 * Eloquence DSP Pipeline (22.05 kHz domain)
 *
 * Input:  11.025 kHz speech signal
 * Output: 22.05 kHz internal processing rate (2x interpolation)
 *
 * Signal chain:
 * 1. Adaptive smoothing (anti-zipper stability layer)
 * 2. SVF-based high-frequency enhancement (presence reconstruction)
 * 3. Narrow-band notch filtering (~7.5 kHz artifact suppression)
 * 4. Deterministic dither + hard safety limiting
 *
 * Empirically tuned coefficients for speech clarity without artifacts.
 */

#define FS			22050.0f
#define PI			3.14159265358979323846f
#define TWO_PI		(2.0f * PI)

#define INT16_NORM	32768.0f
#define CLIP_LEVEL	32760.0f

#define HIST_SIZE	 8
#define HIST_MASK	 (HIST_SIZE - 1)

#define UINT32_SCALE  (1.0f / 4294967296.0f)

static float hist[HIST_SIZE];
static int hist_idx;

static float slew_state;
static float svf_state[2];
static float notch_state[2];
static uint32_t rng = 0x12345678;

__declspec(dllexport)
void process(int16_t * restrict in,
			 int n_samples,
			 int16_t * restrict out) {
	const float hf_presence_gain = 2.0f;
	const float output_gain = 0.85f;

	/* SVF tuning (~6.3 kHz, speech presence region) */
	const float svf_g = tanf(PI * 6300.0f / FS);
	const float a1 = 1.0f / (1.0f + svf_g * (svf_g + 1.0f / 3.0f));
	const float a2 = svf_g * a1;

	/* Notch filter (~7.5 kHz) */
	const float w0 = TWO_PI * 7500.0f / FS;
	const float alpha = sinf(w0);
	const float cosw = cosf(w0);

	const float inv_na0 = 1.0f / (1.0f + alpha);

	const float b0 = inv_na0;
	const float b1 = (-2.0f * cosw) * inv_na0;
	const float b2 = inv_na0;

	const float a1n = (-2.0f * cosw) * inv_na0;
	const float a2n = (1.0f - alpha) * inv_na0;

	for (int i = 0; i < n_samples; i++) {

		/* ring buffer write */
		hist[hist_idx] = (float)in[i];

		float h0 = hist[(hist_idx - 7) & HIST_MASK];
		float h1 = hist[(hist_idx - 6) & HIST_MASK];
		float h2 = hist[(hist_idx - 5) & HIST_MASK];
		float h3 = hist[(hist_idx - 4) & HIST_MASK];
		float h4 = hist[(hist_idx - 3) & HIST_MASK];
		float h5 = hist[(hist_idx - 2) & HIST_MASK];
		float h6 = hist[(hist_idx - 1) & HIST_MASK];
		float h7 = hist[hist_idx];

		hist_idx = (hist_idx + 1) & HIST_MASK;

		/* 2x interpolation */
		float s0 = h3;
		float s1 =
			h0 * -0.015f +
			h1 *  0.055f +
			h2 * -0.155f +
			h3 *  0.615f +
			h4 *  0.615f +
			h5 * -0.155f +
			h6 *  0.055f +
			h7 * -0.015f;

		for (int j = 0; j < 2; j++) {

			float x = (j == 0) ? s0 : s1;

			/* adaptive slew smoothing */
			float diff = x - slew_state;
			float thr = 150.0f * (0.2f + 0.8f * (fabsf(x) / INT16_NORM));

			float ratio = fabsf(diff) / (thr + 1e-6f);
			if (ratio > 1.0f) ratio = 1.0f;

			float mix = 0.4f + (0.6f * ratio);

			x = slew_state + diff * mix;
			slew_state = x;

			/* SVF presence shaping */
			float v1 = a1 * svf_state[0] + a2 * (x - svf_state[1]);
			float v2 = svf_state[1] + svf_g * v1;

			svf_state[0] = 2.0f * v1 - svf_state[0];
			svf_state[1] = 2.0f * v2 - svf_state[1];

			float y = x + (v1 * hf_presence_gain);

			/* notch filter */
			float yn = b0 * y + notch_state[0];

			notch_state[0] = b1 * y - a1n * yn + notch_state[1];
			notch_state[1] = b2 * y - a2n * yn;

			/* deterministic dither */
			rng = 1664525u * rng + 1013904223u;
			float noise = (float)rng * UINT32_SCALE;

			float final = (yn + noise * 0.5f) * output_gain;

			/* hard clip */
			if (final > CLIP_LEVEL) final = CLIP_LEVEL;
			else if (final < -CLIP_LEVEL) final = -CLIP_LEVEL;

			out[i * 2 + j] =
				(int16_t)(final + (final > 0 ? 0.5f : -0.5f));
		}
	}
}

__declspec(dllexport)
void reset() {
	for (int i = 0; i < HIST_SIZE; i++) {
		hist[i] = 0.0f;
	}

	hist_idx = 0;

	slew_state = 0.0f;
	svf_state[0] = 0.0f;
	svf_state[1] = 0.0f;
	notch_state[0] = 0.0f;
	notch_state[1] = 0.0f;
}
