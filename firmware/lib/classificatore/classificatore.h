#pragma once
#include "modello.h"

/* Probabilità di ogni classe in prob[0..N_CLASSI-1], date le caratteristiche di energia_bande.
   Ritorna l'indice della classe più probabile, il nome è NOMI_CLASSI[indice]; oppure SCONOSCIUTA
   se una caratteristica è a più di LIMITE deviazioni standard da quelle viste in addestramento. */
int classifica(const float *caratteristiche, float *prob);
