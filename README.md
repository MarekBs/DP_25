# Behaviorálna biometria – Android aplikácia

Android aplikácia slúži na **zber behaviorálnych biometrických dát** a **autentifikáciu používateľa**.  
Používateľ je rozpoznávaný podľa spôsobu vykonávania dotykových gest a pohybov zariadenia.

Tréningové skripty, dáta a server sa nachádzajú v repozitári [DP_25_ml](https://github.com/MarekBs/DP_25_ml).

APK na stiahnutie: [github.com/MarekBs/apk-release/releases](https://github.com/MarekBs/apk-release/releases)

---

## Funkcie aplikácie

- **Zber dát** – zaznamenávanie dotykových gest (swipe, zoom) a pohybov zariadenia (chôdza, položenie na stôl, zdvihnutie k uchu) spolu so senzormi (akcelerometer, gyroskop)
- **Autentifikácia** – overenie identity používateľa na základe natrénovaných ML modelov cez Flask server

---

## Štruktúra projektu

```
├── app/             # Android aplikácia (Kotlin)
│   └── src/         # Zdrojový kód
├── gradle/          # Gradle wrapper
└── build.gradle.kts # Konfigurácia buildu
```

---

## Požiadavky

- Android Studio
- Android SDK 26+
