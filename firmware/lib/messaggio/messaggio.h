#pragma once
#include <stddef.h>
#include <stdint.h>

/* Riassunto di una finestra di campioni. */
struct Misura {
    float    rms_g;      /* quanto vibra */
    float    picco_hz;   /* frequenza del bin più alto */
    float    picco_g;    /* ampiezza di quel bin */
    uint32_t persi;
    uint32_t saltati;
    const char *classe;      /* cosa dice il classificatore */
    float    confidenza;  /* probabilità di quella classe, da 0 a 1 */
};

/* Sotto questa ampiezza il picco è rumore: nel messaggio diventa null. */
const float SOGLIA_PICCO_G = 0.02f;

/* Scrive in buf il messaggio JSON della misura.
   Restituisce la lunghezza scritta, oppure -1 se buf è troppo piccolo. */
int componi_messaggio(char *buf, size_t dim, const char *dispositivo, const Misura *m);
