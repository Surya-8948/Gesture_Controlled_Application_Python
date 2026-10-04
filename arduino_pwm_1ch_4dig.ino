/*

#define MIRROR_CH4 9 forusin relay

#define MIRROR_CH5 10

#include <Arduino.h>

// ── Pin configuration ─────────────────────────────────────────────────────────
static const uint8_t PIN_PWM   = 3;     // CH1 — hardware PWM
static const uint8_t PIN_DIG[] = {4, 5, 6, 7};  // CH2-CH5 — digital
static const uint8_t NUM_DIG   = 4;

// ── Watchdog ──────────────────────────────────────────────────────────────────
static const uint32_t WATCHDOG_MS = 3000UL;
static uint32_t lastActivity      = 0;
static bool     watchdogFired     = false;

// ── System state ──────────────────────────────────────────────────────────────
static bool    sysOn           = false;
static uint8_t pwmValue        = 0;
static uint8_t digValue[4]     = {0, 0, 0, 0};

// ── Serial parser ─────────────────────────────────────────────────────────────
static const uint8_t BUF_SIZE = 48;
static char          rxBuf[BUF_SIZE];
static uint8_t       rxIdx   = 0;

// ═════════════════════════════════════════════════════════════════════════════

void applyOutputs() {
    if (sysOn) {
        analogWrite(PIN_PWM, pwmValue);
        for (uint8_t i = 0; i < NUM_DIG; i++) {
            digitalWrite(PIN_DIG[i], digValue[i] ? HIGH : LOW);
          digitalWrite(MIRROR_CH4, digValue[2] ? LOW : HIGH);  // CH4 ka ulta
          digitalWrite(MIRROR_CH5, digValue[3] ? LOW : HIGH);  // CH5 ka ulta
        }
        
         
    } else {
        analogWrite(PIN_PWM, 0);
        for (uint8_t i = 0; i < NUM_DIG; i++) {
            digitalWrite(PIN_DIG[i], LOW);
            digitalWrite(MIRROR_CH4, HIGH);
            digitalWrite(MIRROR_CH5, HIGH);
        }
    }
}

void zeroAll() {
    pwmValue = 0;
    for (uint8_t i = 0; i < NUM_DIG; i++) digValue[i] = 0;
    applyOutputs();
}

// ─────────────────────────────────────────────────────────────────────────────
bool startsWith(const char *s, const char *pfx) {
    while (*pfx) { if (*s++ != *pfx++) return false; }
    return true;
}

// Parse "$STATE:pwm,d1,d2,d3,d4"
bool parseState(const char *msg) {
    // Skip "$STATE:"
    const char *p = msg + 7;
    char *end;

    // PWM value
    long v = strtol(p, &end, 10);
    if (end == p) return false;
    pwmValue = (uint8_t)constrain(v, 0, 255);
    p = end;

    // 4 digital values
    for (uint8_t i = 0; i < NUM_DIG; i++) {
        if (*p != ',') return false;
        p++;
        v = strtol(p, &end, 10);
        if (end == p) return false;
        digValue[i] = (v != 0) ? 1 : 0;
        p = end;
    }
    return true;
}

// ─────────────────────────────────────────────────────────────────────────────
void processMessage(const char *msg) {
    lastActivity  = millis();
    watchdogFired = false;

    if (startsWith(msg, "$SYS:ON")) {
        sysOn = true;
        applyOutputs();
        Serial.println("ACK_ON");
    }
    else if (startsWith(msg, "$SYS:OFF")) {
        sysOn = false;
        zeroAll();
        Serial.println("ACK_OFF");
    }
    else if (startsWith(msg, "$STATE:")) {
        if (parseState(msg)) {
            applyOutputs();
            // Echo confirmation
            Serial.print("ACK_STATE:");
            Serial.print(pwmValue);
            for (uint8_t i = 0; i < NUM_DIG; i++) {
                Serial.print(',');
                Serial.print(digValue[i]);
            }
            Serial.println();
        }
    }
    else if (startsWith(msg, "$HB")) {
        // Heartbeat — watchdog reset already done above
    }
}

// ─────────────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    // Pin modes
    pinMode(PIN_PWM, OUTPUT);
    for (uint8_t i = 0; i < NUM_DIG; i++) {
        pinMode(PIN_DIG[i], OUTPUT);
    }

    zeroAll();
    lastActivity = millis();
    Serial.println("READY");
    pinMode(MIRROR_CH4, OUTPUT);
    pinMode(MIRROR_CH5, OUTPUT);
}

void loop() {
    // ── Non-blocking serial receive ──────────────────────────────────────────
    while (Serial.available()) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            if (rxIdx > 0) {
                rxBuf[rxIdx] = '\0';
                processMessage(rxBuf);
                rxIdx = 0;
            }
        } else {
            if (rxIdx < BUF_SIZE - 1) {
                rxBuf[rxIdx++] = c;
            } else {
                rxIdx = 0;   // overflow — discard
            }
        }
    }

    // ── Watchdog ──────────────────────────────────────────────────────────────
    if (!watchdogFired && (millis() - lastActivity > WATCHDOG_MS)) {
        watchdogFired = true;
        sysOn         = false;
        zeroAll();
        Serial.println("WDOG_TIMEOUT");
    }
}
*/