#include "classificatore.h"
#include <math.h>

int classifica(const float *caratteristiche, float *prob) {
    float x[N_CARATTERISTICHE];
    bool fuori = false;
    for (int j = 0; j < N_CARATTERISTICHE; j++) {
        x[j] = (caratteristiche[j] - MEDIA[j]) / SCALA[j];
        if (fabsf(x[j]) > LIMITE) fuori = true;
    }

    int migliore = 0;
    for (int c = 0; c < N_CLASSI; c++) {
        prob[c] = BIAS[c];
        for (int j = 0; j < N_CARATTERISTICHE; j++) prob[c] += PESI[c][j] * x[j];
        if (prob[c] > prob[migliore]) migliore = c;
    }
    /* softmax; togliere il massimo evita che expf vada fuori scala */
    float massimo = prob[migliore], somma = 0;
    for (int c = 0; c < N_CLASSI; c++) { prob[c] = expf(prob[c] - massimo); somma += prob[c]; }
    for (int c = 0; c < N_CLASSI; c++) prob[c] /= somma;
    return fuori ? SCONOSCIUTA : migliore;
}
