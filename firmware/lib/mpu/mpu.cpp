#include "mpu.h"

int16_t da_byte(uint8_t alto, uint8_t basso) {
    return (int16_t)((uint16_t)alto << 8 | basso);
}

void decodifica_accel(const uint8_t byte[6], float g[3]) {
    g[0] = da_byte(byte[0], byte[1]) / LSB_PER_G;
    g[1] = da_byte(byte[2], byte[3]) / LSB_PER_G;
    g[2] = da_byte(byte[4], byte[5]) / LSB_PER_G;
}