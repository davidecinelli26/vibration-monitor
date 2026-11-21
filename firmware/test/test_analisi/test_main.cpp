#include <unity.h>
#include <math.h>
#include "analisi.h"

const int N = 1024;
const float FS = 1000.0f;            /* campioni al secondo */
const float DUE_PI = 6.28318531f;

static float x[N], re[N], im[N], amp[N / 2 + 1];

void setUp() {}
void tearDown() {}

/* 1 g di gravità + una sinusoide di ampiezza a e frequenza f */
static void genera(float a, float f) {
    for (int i = 0; i < N; i++) x[i] = 1.0f + a * sinf(DUE_PI * f * i / FS);
}

void test_media_e_rms() {
    const float v[4] = {1, 3, 1, 3};
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 2.0f, media(v, 4));
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 1.0f, rms_senza_media(v, 4));
}

void test_fermo_rms_zero() {
    genera(0.0f, 0.0f);
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 1.0f, media(x, N));
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 0.0f, rms_senza_media(x, N));
}

void test_sinusoide_su_un_bin() {
    /* 62.5 Hz = 64 * 1000 / 1024: cade esattamente sul bin 64 */
    genera(0.5f, 62.5f);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.5f / sqrtf(2.0f), rms_senza_media(x, N));
    spettro(x, N, re, im, amp);
    int k = picco(amp, N / 2 + 1);
    TEST_ASSERT_EQUAL_INT(64, k);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 62.5f, k * FS / N);
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.5f, amp[k]);
}

void test_due_sinusoidi() {
    for (int i = 0; i < N; i++) {
        x[i] = 1.0f + 0.5f * sinf(DUE_PI * 62.5f * i / FS) + 0.2f * sinf(DUE_PI * 195.3125f * i / FS);
    }
    spettro(x, N, re, im, amp);
    TEST_ASSERT_EQUAL_INT(64, picco(amp, N / 2 + 1));
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.2f, amp[200]);   /* 195.3125 Hz = bin 200 */
    TEST_ASSERT_FLOAT_WITHIN(1e-3f, 0.0f, amp[100]);   /* dove non c'è niente */
}

void test_frequenza_fuori_bin() {
    /* 50 Hz cade tra i bin 51 (49.8 Hz) e 52 (50.8 Hz) */
    genera(0.5f, 50.0f);
    spettro(x, N, re, im, amp);
    int k = picco(amp, N / 2 + 1);
    TEST_ASSERT_FLOAT_WITHIN(1.0f, 50.0f, k * FS / N);   /* giusta entro un bin */
    TEST_ASSERT_TRUE(amp[k] < 0.5f);                      /* l'ampiezza si sparpaglia sui vicini */
    TEST_ASSERT_TRUE(amp[k] > 0.3f);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_media_e_rms);
    RUN_TEST(test_fermo_rms_zero);
    RUN_TEST(test_sinusoide_su_un_bin);
    RUN_TEST(test_due_sinusoidi);
    RUN_TEST(test_frequenza_fuori_bin);
    return UNITY_END();
}