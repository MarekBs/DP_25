# Behaviorálna biometria – Android aplikácia

Android aplikácia slúži na **zber behaviorálnych biometrických dát** a **autentifikáciu používateľa**.  
Používateľ je rozpoznávaný podľa spôsobu vykonávania dotykových gest a pohybov zariadenia.

Tréningové skripty, dáta a server sa nachádzajú v repozitári [DP_25_ml](https://github.com/MarekBs/DP_25_ml).


---

## Štruktúra repozitára

```
DP_25/
├── app/
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/example/dp_app/
│       │   ├── MainActivity.kt
│       │   ├── UserSession.kt
│       │   ├── fragments/          # UI fragmenty (login, survey, zber dát, overenie)
│       │   ├── adapters/           # adaptéry (ImageAdapter)
│       │   └── models/             # ViewModely (Behametrics, Sensor)
│       └── res/                    # layouty, ikony, navigácia, témy          
├── README.md
└── build.gradle.kts
```
---

# Manuál – Aplikácia behaviorálnej biometrie

## Inštalácia

APK súbor je dostupný na: [github.com/MarekBs/apk-release/releases](https://github.com/MarekBs/apk-release/releases)

Stiahnutý `.apk` súbor sa nainštaluje priamo na zariadení. Je potrebné povoliť inštaláciu z neznámych zdrojov v nastaveniach zariadenia.

**Požiadavky:**
- Android 8.0 (API 26) alebo novší
- Internetové pripojenie je vyžadované počas celého behu aplikácie (prihlásenie, registrácia, nahrávanie dát do Firebase Storage, overenie identity cez server)

---

## Prihlásenie

Po spustení aplikácie sa zadá používateľské ID.

- Ak ID **ešte neexistuje** → aplikácia zobrazí krátky dotazník (pohlavie a vek), ktorý sa vyplní raz pri prvom prihlásení.
- Ak ID **už existuje** → aplikácia priamo pokračuje na hlavné menu.

> **Pozor:** logovaním sa prepisujú dáta, ak už pre dané ID existujú.

---

## Logovanie dát

Hlavné menu zobrazuje dostupné aktivity. Po dokončení aktivity sa tlačidlo označí zelenou farbou.

**Dostupné aktivity:**
- zdvihnutie k uchu
- položenie na stôl
- swipe gesto (potiahnutím cez galériu obrázkov)
- chôdza
- zoom/pinch gesto

Zozbierané dáta sa automaticky nahrávajú do Firebase Storage.

---

## Overenie identity

Aplikácia umožňuje overiť identitu používateľa gestom zdvihnutia k uchu. Po 3 sekundách záznamu sa gesto odošle na server a aplikácia zobrazí výsledok – či bol používateľ rozpoznaný alebo odmietnutý.

Na fungovanie overenia je potrebné mať spustený Flask server dostupný v repozitári [DP_25_ml](https://github.com/MarekBs/DP_25_ml), kde sa nachádza aj postup.


---

## Poznámky

Prístupový kľúč k Firebase Storage (`serviceAccountKey.json`) je dostupný iba na vyžiadanie. Bez neho nie je možné nahrávať ani sťahovať dáta z úložiska – kľúč poskytuje plný prístup k všetkým zozbieraným dátam.

Všetky doteraz zozbierané dáta sú stiahnuté v [DP_25_ml](https://github.com/MarekBs/DP_25_ml) repozitári v priečinku `data/`.

Ak by niekto chcel pridať vlastné logy a pridať sa do modelov, je potrebné po zbere dát stiahnuť dáta z Firebase, pretrénovať modely a s novými modelmi spustiť server (viď `Manual_ML.txt`).


