# Behaviorálna biometria – Android aplikácia

Android aplikácia na autentifikáciu používateľa na základe behaviorálnych biometrík.  
Používateľ je rozpoznávaný podľa spôsobu vykonávania dotykových gest a pohybov zariadenia.

Tréningové skripty, dáta a server sa nachádzajú v repozitári [DP_25_ml](https://github.com/MarekBs/DP_25_ml).

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
