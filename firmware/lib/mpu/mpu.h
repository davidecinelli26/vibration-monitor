#pragma once
#include <stdint.h>

/* Indirizzo e registri dell'MPU-6050 (dal register map) */
const uint8_t MPU_INDIRIZZO    = 0x68;
const uint8_t REG_ACCEL_CONFIG = 0x1C;   /* bit 4-3: fondo scala */
const uint8_t REG_ACCEL_XOUT_H = 0x3B;   /* 6 byte: X alto, X basso, Y alto, Y basso, Z alto, Z basso */
const uint8_t REG_PWR_MGMT_1   = 0x6B;   /* bit 6: SLEEP, a 1 dopo l'accensione */
const uint8_t REG_WHO_AM_I     = 0x75;   /* risponde 0x68 */

const float LSB_PER_G = 16384.0f;        /* con fondo scala ±2g */

/* Unisce due byte (prima l'alto) in un intero con segno. */
int16_t da_byte(uint8_t alto, uint8_t basso);

/* Converte i 6 byte letti da ACCEL_XOUT_H in accelerazioni in g: g[0]=X, g[1]=Y, g[2]=Z. */
void decodifica_accel(const uint8_t byte[6], float g[3]);