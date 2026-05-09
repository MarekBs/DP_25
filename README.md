# Behaviorálna biometria – Android aplikácia

Android aplikácia slúži na **zber behaviorálnych biometrických dát** a **autentifikáciu používateľa**.  
Používateľ je rozpoznávaný podľa spôsobu vykonávania dotykových gest a pohybov zariadenia.

Tréningové skripty, dáta a server sa nachádzajú v repozitári [DP_25_ml](https://github.com/MarekBs/DP_25_ml).

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
- Google Services (`google-services.json`)

---

## Použitie

1. Otvor projekt v Android Studio
2. Pripoj Android zariadenie alebo spusti emulátor
3. Spusti aplikáciu (Run → Run 'app')

Pre autentifikáciu je potrebný bežiaci Flask server z repozitára [DP_25_ml](https://github.com/MarekBs/DP_25_ml).
