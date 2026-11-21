# vibration-monitor

**A machine vibration monitor, end to end: ESP32 firmware with FreeRTOS and an on-device FFT, MQTT, TimescaleDB and Grafana, fed by a real sensor or by public fault datasets.**

![ESP32](https://img.shields.io/badge/ESP32-Arduino%20%2B%20FreeRTOS-2a9d8f)
![Python 3.11](https://img.shields.io/badge/Python-3.11-264653)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-457b9d)

An ESP32 reads an MPU-6050 accelerometer 1000 times a second. Every 1024 samples it computes the RMS and the spectrum of the vibration, and it publishes one small JSON message over MQTT. A Python service stores the messages in TimescaleDB, and Grafana plots them.

The same pipeline can be fed without hardware. A replay program reads recordings of healthy and faulty machines from two public datasets (CWRU and MAFAULDA), reduces them to what the 1 kHz sensor would see, and publishes the same JSON on the same topics. That shows what a cheap sensor can and cannot detect. The answer turned out to be less obvious than expected; see [Results](#results).

**Status: work in progress.** Next steps are an MCP agent that answers questions about the machines from the database, and a small model for the faults that two numbers cannot separate.

## Author

[Davide Cinelli](https://github.com/davidecinelli26). A personal project, built while learning embedded programming. Comments and identifiers in the code are in Italian.

## How it works

```text
MPU-6050 ──I2C──► ESP32 ──WiFi/MQTT──► Mosquitto ──► ingestor (Python) ──► TimescaleDB ◄── Grafana
                                           ▲
             replay (Python, CWRU + MAFAULDA) ┘
```

| Folder | What | Tools |
|---|---|---|
| [`firmware/`](firmware) | ESP32 firmware: sampling, analysis, MQTT | PlatformIO, Arduino core 3, FreeRTOS, Wokwi |
| [`ingestor/`](ingestor) | MQTT → TimescaleDB | Python, paho-mqtt, psycopg, uv |
| [`replay/`](replay) | publishes the public datasets as if they were sensors | Python, numpy, scipy, uv |
| [`infra/`](infra) | broker, database, dashboard | Docker Compose: Mosquitto, TimescaleDB, Grafana |

The parts only talk through MQTT and SQL, so any of them can be swapped: the replay stands in for the board, and the board does not know who reads its data.

### Firmware

- A hardware timer fires every 1 ms. Its interrupt does no work: it only wakes a high-priority FreeRTOS task. The task reads the sensor over I2C and puts the raw sample in a queue. I2C cannot run inside an interrupt, because the Wire driver blocks on semaphores.
- The main loop takes 1024 samples from the queue (about 1 s) and computes the RMS without the mean, so gravity is removed, plus an FFT of its own (radix-2, in place) and the highest peak.
- Two counters make data loss visible instead of silent: `saltati` (timer ticks the reader missed) and `persi` (samples dropped because the queue was full). The queue holds 512 samples. That is enough for the analysis (about 380 ms in the simulator) and the MQTT publish. The MQTT connection is opened before sampling starts, because the first connect alone used to drop about 116 samples.
- Message: `{"dispositivo":"esp32-1","rms_g":0.2121,"picco_hz":49.8,"picco_g":0.2806,"persi":0,"saltati":0}`. Peaks below 0.02 g are sent as `null`.
- Built with the [Wokwi](https://wokwi.com) simulator in VS Code. Wokwi has no vibrating MPU-6050, so the firmware adds a synthetic 50 Hz, 0.3 g vibration when `SIMULA_VIBRAZIONE` is 1.

### Replay

The replay applies the same analysis as the firmware (the tests check it gives the same numbers on the same signal). It sends one window per recording every 1.024 s and starts again when a recording ends.

## Run it

You need Docker, [uv](https://github.com/astral-sh/uv) and, for the firmware, VS Code with PlatformIO and the Wokwi extension.

```bash
# 1. broker, database and Grafana
cd infra && docker compose up -d

# 2. store the measurements
cd ../ingestor && uv run python ingestor.py

# 3a. without hardware: download the data once (a few minutes), then replay it
cd ../replay && uv run python scarica_dati.py && uv run python replay.py

# 3b. or the firmware in the simulator: open firmware/ in VS Code,
#     build with `pio run -e esp32`, then F1 → "Wokwi: Start Simulator"
```

Then open the dashboard at http://localhost:3000/d/vibrazioni.

Tests:

```bash
cd firmware && pio test -e native     # 11 tests: sensor decoding, analysis, JSON
cd ingestor && uv run pytest -q       # 5 tests: message parsing
cd replay && uv run pytest -q         # 7 tests: analysis, plus checks on the real data
```

The passwords in `infra/` are for local development only. The database and Grafana listen on 127.0.0.1, and Grafana has no login.

## Results

The MPU-6050 accelerometer outputs at most 1000 samples a second. Nothing above 500 Hz can be seen. The replay measures what that costs.

**CWRU bearing faults are almost invisible at 1 kHz.** Bearing defects show up mostly at kHz frequencies. In the original recordings (drive-end accelerometer, 0 HP, 0.007" faults), most of the vibration is above 500 Hz:

| Recording | RMS, full band | RMS below 500 Hz | Lost |
|---|---|---|---|
| normal | 0.073 g | 0.021 g | 71% |
| inner race | 0.291 g | 0.027 g | 91% |
| ball | 0.139 g | 0.019 g | 86% |
| outer race | 0.669 g | 0.024 g | 96% |

At full bandwidth a faulty bearing vibrates 2 to 9 times more than a healthy one. Below 500 Hz they all sit around 0.02 g. Each fault still keeps a small, stable peak (360, 455, 419 and 449 Hz). These peaks belong to that test rig, not to textbook fault frequencies.

**MAFAULDA imbalance is clearly visible; misalignment is not.** At about 29.5 revolutions per second (underhang radial accelerometer):

| Recording | RMS | Peak |
|---|---|---|
| normal | 0.168 | 29.3 Hz, 0.15 |
| imbalance 6 g | 0.242 | 29.3 Hz, 0.30 |
| imbalance 20 g | 0.520 | 29.3 Hz, 0.67 |
| imbalance 35 g | 0.718 | 30.3 Hz, 0.67 |
| horizontal misalignment 2.0 mm | 0.136 | 29.3 Hz, 0.14 |
| vertical misalignment 1.90 mm | 0.145 | 30.3 Hz, 0.11 |

Imbalance shakes the shaft once per turn, so the peak sits at the rotation speed and grows with the added mass. Misalignment was not separable from the healthy machine with RMS and the 1×, 2× and 3× harmonics, on any of the three axes. That is the motivation for a model that looks at the whole spectrum.

Two notes on MAFAULDA. The dataset page says 50 kHz, but the file names (the rotation speed) only match the tachometer pulses at 51.2 kHz. 51.2 kHz is also the rate of the NI 9234 board used to record it, so the replay uses 51.2 kHz; at 50 kHz every frequency would be 2% low. The page does not state the unit of the values, so they are used as they are; comparisons between recordings do not depend on it.

## Data

The datasets are not in this repository. `replay/scarica_dati.py` downloads them from the original sources:

- **CWRU**: Case Western Reserve University Bearing Data Center, https://engineering.case.edu/bearingdatacenter
- **MAFAULDA**: Machinery Fault Database, Federal University of Rio de Janeiro, https://www02.smt.ufrj.br/~offshore/mfs/page_01.html
