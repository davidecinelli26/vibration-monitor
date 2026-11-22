#include <unity.h>
#include <math.h>
#include "analisi.h"
#include "classificatore.h"
#include "esempi.h"

const int N = 1024;
static float re[N], im[N];

void setUp() {}
void tearDown() {}

void test_bande_come_il_python() {
    for (const Esempio &e : ESEMPI) {
        float car[N_CARATTERISTICHE];
        energia_bande(e.finestra, N, re, im, car);
        TEST_ASSERT_FLOAT_ARRAY_WITHIN(1e-3f, e.caratteristiche, car, N_CARATTERISTICHE);
    }
}

void test_classifica_come_il_python() {
    for (const Esempio &e : ESEMPI) {
        float prob[N_CLASSI];
        TEST_ASSERT_EQUAL_INT(e.classe, classifica(e.caratteristiche, prob));
        TEST_ASSERT_FLOAT_ARRAY_WITHIN(1e-4f, e.probabilita, prob, N_CLASSI);
    }
}

void test_dalla_finestra_alla_classe() {
    for (const Esempio &e : ESEMPI) {
        float car[N_CARATTERISTICHE], prob[N_CLASSI];
        energia_bande(e.finestra, N, re, im, car);
        TEST_ASSERT_EQUAL_STRING(NOMI_CLASSI[e.classe], NOMI_CLASSI[classifica(car, prob)]);
    }
}

int main() {
    UNITY_BEGIN();
    RUN_TEST(test_classifica_come_il_python);
    RUN_TEST(test_bande_come_il_python);
    RUN_TEST(test_dalla_finestra_alla_classe);
    return UNITY_END();
}
