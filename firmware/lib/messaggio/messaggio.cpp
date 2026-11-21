#include "messaggio.h"
#include <stdio.h>

int componi_messaggio(char *buf, size_t dim, const char *dispositivo, const Misura *m) {
    int n;
    if (m->picco_g >= SOGLIA_PICCO_G) {
        n = snprintf(buf, dim,
                     "{\"dispositivo\":\"%s\",\"rms_g\":%.4f,\"picco_hz\":%.1f,\"picco_g\":%.4f,"
                     "\"persi\":%lu,\"saltati\":%lu}",
                     dispositivo, m->rms_g, m->picco_hz, m->picco_g,
                     (unsigned long)m->persi, (unsigned long)m->saltati);
    } else {
        n = snprintf(buf, dim,
                     "{\"dispositivo\":\"%s\",\"rms_g\":%.4f,\"picco_hz\":null,\"picco_g\":null,"
                     "\"persi\":%lu,\"saltati\":%lu}",
                     dispositivo, m->rms_g,
                     (unsigned long)m->persi, (unsigned long)m->saltati);
    }
    if (n < 0 || (size_t)n >= dim) return -1;
    return n;
}
