#include "analisi.h"
#include <math.h>

static const float DUE_PI = 6.28318531f;

float media(const float *x, int n) {
    float sum = 0;
    for (int i = 0; i < n; i++) {
        sum += x[i];
    }
    return sum / n;
}

float rms_senza_media(const float *x, int n) {
    float m = media(x, n);
    float sum = 0;
    for (int i = 0; i < n; i++) {
        float diff = x[i] - m;
        sum += diff * diff;
    }
    return sqrtf(sum / n);
}

void fft(float *re, float *im, int n) {
    /* 1. riordina gli elementi invertendo i bit dell'indice */
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) {
            float t = re[i]; re[i] = re[j]; re[j] = t;
            t = im[i]; im[i] = im[j]; im[j] = t;
        }
    }
    /* 2. combina blocchi da 2, 4, 8, ... n elementi */
    for (int len = 2; len <= n; len <<= 1) {
        float ang = -DUE_PI / len;
        float wr = cosf(ang), wi = sinf(ang);
        for (int i = 0; i < n; i += len) {
            float cr = 1, ci = 0;
            for (int k = 0; k < len / 2; k++) {
                int a = i + k, b = i + k + len / 2;
                float tr = re[b] * cr - im[b] * ci;
                float ti = re[b] * ci + im[b] * cr;
                re[b] = re[a] - tr;  im[b] = im[a] - ti;
                re[a] += tr;         im[a] += ti;
                float ncr = cr * wr - ci * wi;
                ci = cr * wi + ci * wr;
                cr = ncr;
            }
        }
    }
}

void spettro(const float *x, int n, float *re, float *im, float *ampiezza) {
    float m = media(x, n);
    for (int i = 0; i < n; i++) { re[i] = x[i] - m; im[i] = 0; }
    fft(re, im, n);
    for (int k = 0; k <= n / 2; k++) {
        float modulo = sqrtf(re[k] * re[k] + im[k] * im[k]);
        ampiezza[k] = (k == 0 || k == n / 2) ? modulo / n : 2 * modulo / n;
    }
}

int picco(const float *ampiezza, int n_bin) {
    /* da k = 1: il bin 0 è la media, già tolta */
    int k_max = 1;
    for (int k = 2; k < n_bin; k++) {
        if (ampiezza[k] > ampiezza[k_max]) k_max = k;
    }
    return k_max;
}