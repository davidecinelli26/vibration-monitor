#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <math.h>
#include "mpu.h"
#include "analisi.h"
#include "messaggio.h"

const char    *WIFI_RETE   = "Wokwi-GUEST";          /* la rete simulata di Wokwi, senza password */
const char    *MQTT_HOST   = "host.wokwi.internal";  /* il PC su cui gira il simulatore */
const uint16_t MQTT_PORTA  = 1883;
const char    *DISPOSITIVO = "esp32-1";
const char    *TOPIC       = "vibrazioni/esp32-1";

WiFiClient   rete;
PubSubClient mqtt(rete);

/* 1: aggiunge al valore letto una vibrazione finta (per provare in simulazione) */
#define SIMULA_VIBRAZIONE 1

const uint8_t PIN_SDA = 21, PIN_SCL = 22;

struct Campione {
    uint32_t n;      /* numero progressivo */
    int16_t  z;      /* Z grezzo, come esce dal sensore */
};

hw_timer_t   *timer   = nullptr;
TaskHandle_t  lettore = nullptr;
QueueHandle_t coda    = nullptr;
volatile uint32_t persi   = 0;   /* campioni letti ma non entrati in coda */
volatile uint32_t saltati = 0;   /* tick arrivati mentre il lettore era ancora occupato */

/* Scrive un byte in un registro. Restituisce true se il sensore ha risposto. */
bool scrivi_registro(uint8_t reg, uint8_t valore) {
    Wire.beginTransmission(MPU_INDIRIZZO);
    Wire.write(reg);
    Wire.write(valore);
    return Wire.endTransmission() == 0;
}

/* Legge n registri consecutivi a partire da reg. Restituisce true se sono arrivati tutti. */
bool leggi_registri(uint8_t reg, uint8_t *dest, uint8_t n) {
    Wire.beginTransmission(MPU_INDIRIZZO);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return false;   /* false: niente STOP, segue la lettura */
    if (Wire.requestFrom(MPU_INDIRIZZO, n) != n) return false;
    for (uint8_t i = 0; i < n; i++) dest[i] = Wire.read();
    return true;
}

/* ISR del timer: non legge niente, sveglia il task lettore. */
void IRAM_ATTR ogni_ms() {
    BaseType_t sveglia_subito = pdFALSE;
    vTaskNotifyGiveFromISR(lettore, &sveglia_subito);
    portYIELD_FROM_ISR(sveglia_subito);
}

void task_lettore(void *) {
    uint32_t n = 0;
    for (;;) {
        /* Una sola chiamata: dorme finché il timer non suona, poi dice QUANTE volte ha suonato. */
        uint32_t notifiche = ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
        if (notifiche > 1) {
            saltati = saltati + (notifiche - 1);
        }
        uint8_t buf[6];
        if (!leggi_registri(REG_ACCEL_XOUT_H, buf, 6)) continue;

        Campione c;
        c.n = n++;
        c.z = da_byte(buf[4], buf[5]);   /* solo interi qui: i calcoli float li fa il loop */
        if (xQueueSend(coda, &c, 0) != pdTRUE) {
            persi = persi + 1;
        }
    }
}

void setup() {
    Serial.begin(115200);
    Wire.begin(PIN_SDA, PIN_SCL, 400000);        /* bus a 400 kHz */
    uint8_t chi = 0;
    while (!leggi_registri(REG_WHO_AM_I, &chi, 1) || chi != 0x68) {
        Serial.printf("MPU-6050 non trovato, riprovo\r\n");
        delay(1000);
    }
    scrivi_registro(REG_PWR_MGMT_1, 0x00);
    scrivi_registro(REG_ACCEL_CONFIG, 0x00);

    WiFi.begin(WIFI_RETE, "", 6);   /* canale 6: salta la ricerca delle reti */
    while (WiFi.status() != WL_CONNECTED) {
        delay(250);
    }
    Serial.printf("WiFi collegato, IP %s\r\n", WiFi.localIP().toString().c_str());
    mqtt.setServer(MQTT_HOST, MQTT_PORTA);

    while (!mqtt.connect(DISPOSITIVO)) {
        Serial.printf("MQTT non raggiungibile (stato %d), riprovo\r\n", mqtt.state());
        delay(1000);
    }
    Serial.printf("MQTT collegato\r\n");

    coda = xQueueCreate(512, sizeof(Campione));   /* 512 ms di margine; 512 × 8 byte = 4 KB */
    xTaskCreatePinnedToCore(task_lettore, "lettore", 4096, nullptr, 5, &lettore, 1);

    timer = timerBegin(1000000);
    timerAttachInterrupt(timer, ogni_ms);
    timerAlarm(timer, 1000, true, 0);
    Serial.printf("Avviato\r\n");
}


const int N = 1024;            /* campioni per finestra: circa 1 secondo */
const float FS = 1000.0f;      /* campioni al secondo */

/* globali, non nello stack del loop: sono 4 KB l'uno */
static float z[N], re[N], im[N], amp[N / 2 + 1];

void loop() {
    /* 1. riempi la finestra con N valori di Z presi dalla coda */
    Campione c = {};
    int i = 0;
    while (i < N) {
        if (xQueueReceive(coda, &c, pdMS_TO_TICKS(100)) == pdTRUE) {
            float g = c.z / LSB_PER_G;
#if SIMULA_VIBRAZIONE
            g += 0.3f * sinf(6.28318531f * 50.0f * c.n / FS);   /* vibrazione finta: 50 Hz, 0.3 g */
#endif
            z[i++] = g;
        }
    }
    /* 2. analizza la finestra */
    uint32_t t0 = micros();
    float r = rms_senza_media(z, N);
    spettro(z, N, re, im, amp);
    int k = picco(amp, N / 2 + 1);
    uint32_t durata = micros() - t0;

    /* 3. componi il messaggio e invialo */
    Misura m = {r, k * FS / N, amp[k], persi, saltati};
    char json[200];
    if (componi_messaggio(json, sizeof(json), DISPOSITIVO, &m) < 0) return;

    if (!mqtt.connected()) {
        Serial.printf("MQTT: collego a %s:%u ... ", MQTT_HOST, MQTT_PORTA);
        if (mqtt.connect(DISPOSITIVO)) Serial.printf("ok\r\n");
        else Serial.printf("fallito (stato %d)\r\n", mqtt.state());
    }
    bool inviato = mqtt.connected() && mqtt.publish(TOPIC, json);
    mqtt.loop();
    Serial.printf("%s %s (calcolo %lu us)\r\n", inviato ? "inviato" : "NON inviato", json, (unsigned long)durata);
}