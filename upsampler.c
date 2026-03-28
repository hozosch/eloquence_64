#include <stdint.h>

static int32_t last = 0, s1z1 = 0, s1z2 = 0, s2z1 = 0, s2z2 = 0;
static int32_t nz1 = 0, nz2 = 0, nz3 = 0, nz4 = 0;
static int strength = 50;

__declspec(dllexport) void set_strength(int s) { 
    strength = (s < 0) ? 0 : (s > 140 ? 100 : s); 
}

__declspec(dllexport) void process(int16_t* in, int n_samples, int16_t* out) {
    int delta = strength - 50;

    // A2: 12000 @ 50. Drops to 5000 @ 0. Caps at 13250 @ 100.
    int A2 = 12000 + (delta * (delta < 0 ? 100 : 25));

    // Volume Compensation: Heavy cut at 0 (factor 6), slight boost at 100.
    int g_comp = 1024 + (delta * (delta < 0 ? 6 : 1));

    // Filter Coefficients
    const int B0 = 1974, B1 = 3948, B2 = 1974, A1 = -15871;
    const int N1_B0 = 11160, N1_B1 = -11540, N1_B2 = 11160, N1_A1 = -11540, N1_A2 = 8000;
    const int N2_B0 = 8000, N2_B1 = 0, N2_B2 = 8000, N2_A1 = -12000, N2_A2 = 6000;

    for (int i = 0, o = 0; i < n_samples; i++) {
        int32_t c_s = in[i];
        for (int j = 0; j < 4; j++) {
            // 4x Oversampling Linear Interpolation
            int32_t smp = last + ((c_s - last) * j >> 2);

            // Stages 1 & 2 (Saturation & Character)
            int32_t v1 = (smp * B0 + s1z1) >> 14;
            s1z1 = smp * B1 - A1 * v1 + s1z2; 
            s1z2 = smp * B2 - A2 * v1;

            int32_t v2 = (v1 * B0 + s2z1) >> 14;
            s2z1 = v1 * B1 - A1 * v2 + s2z2; 
            s2z2 = v1 * B2 - A2 * v2;

            // Dual Notch Filters (Anti-Aliasing)
            int32_t vn1 = v2 - ((N1_A1 * nz1 + N1_A2 * nz2) >> 14);
            int32_t o_n1 = (N1_B0 * vn1 + N1_B1 * nz1 + N1_B2 * nz2) >> 14;
            nz2 = nz1; nz1 = vn1;

            int32_t vn2 = o_n1 - ((N2_A1 * nz3 + N2_A2 * nz4) >> 14);
            int32_t o_n2 = (N2_B0 * vn2 + N2_B1 * nz3 + N2_B2 * nz4) >> 14;
            nz4 = nz3; nz3 = vn2;

            // Final Mix with Asymmetric Treble Cap
            int32_t b_val = 50 + (delta < 0 ? delta : (delta >> 2) + (delta >> 4));
            int32_t final_s = (o_n2 + (o_n2 >> 2) + (o_n2 * b_val >> 7));
            
            // Apply Compensation and Clamp
            final_s = (final_s * g_comp) >> 10;
            final_s = (final_s > 32767) ? 32767 : (final_s < -32768 ? -32768 : final_s);

            out[o++] = (int16_t)final_s;
        }
        last = c_s;
    }
}

__declspec(dllexport) void reset() { 
    last = s1z1 = s1z2 = s2z1 = s2z2 = nz1 = nz2 = nz3 = nz4 = 0; 
}
