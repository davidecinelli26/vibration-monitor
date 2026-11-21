#pragma once

/* Media di n valori. */
float media(const float *x, int n);

/* RMS dopo aver tolto la media: quanto il segnale oscilla attorno al suo valore medio. */
float rms_senza_media(const float *x, int n);

/* FFT in place. n deve essere una potenza di 2. re e im entrano come segnale, escono come spettro. */
void fft(float *re, float *im, int n);

/* Toglie la media da x, fa la FFT e scrive in ampiezza[0..n/2] l'ampiezza di ogni frequenza,
   nella stessa unità di x. re e im sono spazio di lavoro da n elementi. */
void spettro(const float *x, int n, float *re, float *im, float *ampiezza);

/* Indice k (da 1 a n_bin-1) dell'ampiezza più grande. La frequenza è k * fs / n. */
int picco(const float *ampiezza, int n_bin);