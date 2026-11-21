#include <unity.h>
#include <string.h>
#include "messaggio.h"

void setUp() {}
void tearDown() {}

void test_con_picco() {
    Misura m = {0.212f, 49.8f, 0.28f, 0, 3};
    char buf[200];
    int n = componi_messaggio(buf, sizeof(buf), "esp32-1", &m);
    TEST_ASSERT_EQUAL_STRING(
        "{\"dispositivo\":\"esp32-1\",\"rms_g\":0.2120,\"picco_hz\":49.8,\"picco_g\":0.2800,"
        "\"persi\":0,\"saltati\":3}", buf);
    TEST_ASSERT_EQUAL_INT((int)strlen(buf), n);
}

void test_picco_sotto_soglia_diventa_null() {
    Misura m = {0.001f, 0.98f, 0.005f, 0, 0};
    char buf[200];
    componi_messaggio(buf, sizeof(buf), "esp32-1", &m);
    TEST_ASSERT_EQUAL_STRING(
        "{\"dispositivo\":\"esp32-1\",\"rms_g\":0.0010,\"picco_hz\":null,\"picco_g\":null,"
        "\"persi\":0,\"saltati\":0}", buf);
}

void test_buffer_piccolo() {
    Misura m = {0.212f, 49.8f, 0.28f, 0, 0};
    char buf[20];
    TEST_ASSERT_EQUAL_INT(-1, componi_messaggio(buf, sizeof(buf), "esp32-1", &m));
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_con_picco);
    RUN_TEST(test_picco_sotto_soglia_diventa_null);
    RUN_TEST(test_buffer_piccolo);
    return UNITY_END();
}
