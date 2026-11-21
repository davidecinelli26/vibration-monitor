#include <unity.h>
#include "mpu.h"

void setUp() {}
void tearDown() {}

void test_da_byte() {
    TEST_ASSERT_EQUAL_INT16(16384, da_byte(0x40, 0x00));
    TEST_ASSERT_EQUAL_INT16(-16384, da_byte(0xC0, 0x00));
    TEST_ASSERT_EQUAL_INT16(-1, da_byte(0xFF, 0xFF));
    TEST_ASSERT_EQUAL_INT16(32767, da_byte(0x7F, 0xFF));
    TEST_ASSERT_EQUAL_INT16(-32768, da_byte(0x80, 0x00));
    TEST_ASSERT_EQUAL_INT16(0x1234, da_byte(0x12, 0x34));
}

void test_decodifica_fermo_in_piano() {
    /* X = 0, Y = 0, Z = +1 g */
    const uint8_t b[6] = {0x00, 0x00, 0x00, 0x00, 0x40, 0x00};
    float g[3];
    decodifica_accel(b, g);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 0.0f, g[0]);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 0.0f, g[1]);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 1.0f, g[2]);
}

void test_decodifica_ordine_e_segno() {
    /* X = +0.5 g, Y = -1 g, Z = -0.25 g */
    const uint8_t b[6] = {0x20, 0x00, 0xC0, 0x00, 0xF0, 0x00};
    float g[3];
    decodifica_accel(b, g);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, 0.5f, g[0]);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, -1.0f, g[1]);
    TEST_ASSERT_FLOAT_WITHIN(0.0001f, -0.25f, g[2]);
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_da_byte);
    RUN_TEST(test_decodifica_fermo_in_piano);
    RUN_TEST(test_decodifica_ordine_e_segno);
    return UNITY_END();
}