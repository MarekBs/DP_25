# Behaviorálna biometria – Android aplikácia

Android aplikácia slúži na **zber behaviorálnych biometrických dát** a **autentifikáciu používateľa**.  
Používateľ je rozpoznávaný podľa spôsobu vykonávania dotykových gest a pohybov zariadenia.

Tréningové skripty, dáta a server sa nachádzajú v repozitári [DP_25_ml](https://github.com/MarekBs/DP_25_ml).


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

Aplikácia umožňuje overiť identitu používateľa gestom zdvihnutia k uchu. Výsledok overenia (autentifikovaný / odmietnutý) sa zobrazí po 3 sekundách záznamu gesta.

Na fungovanie overenia je potrebné mať spustený Flask server. Postup:

**1. Natrénovať model pre gesto zdvihnutia k uchu:**
```bash
cd ml_training
python train_pickup.py --fs full --model SVM
```
Výstup: `gesture_model_zdvihnutie.pkl`

**2. Nájsť optimálny prah rozhodovania:**
```bash
python find_optimal_threshold.py
```
Výstup: `optimal_thresholds.json`

**3. Spustiť server** (`gesture_model_zdvihnutie.pkl` a `optimal_thresholds.json` musia byť v rovnakom priečinku ako `server.py`):
```bash
python server.py
```

Server beží na adrese `http://0.0.0.0:5000`. Server a zariadenie s aplikáciou musia byť na **rovnakej sieti**. IP adresu zariadenia so serverom je potrebné nastaviť v zdrojovom kóde aplikácie (`VerifyPickupFragment.kt` – konštanta `SERVER_URL`).

Podrobnosti o tréningu modelov sú v `Manual_ML.txt`.

---

## Poznámky

Prístupový kľúč k Firebase Storage (`serviceAccountKey.json`) je dostupný iba na vyžiadanie. Bez neho nie je možné nahrávať ani sťahovať dáta z úložiska – kľúč poskytuje plný prístup k všetkým zozbieraným dátam.

Všetky doteraz zozbierané dáta sú stiahnuté v [DP_25_ml](https://github.com/MarekBs/DP_25_ml) repozitári v priečinku `data/`.

Ak by niekto chcel pridať vlastné logy a pridať sa do modelov, je potrebné po zbere dát stiahnuť dáta z Firebase, pretrénovať modely a s novými modelmi spustiť server (viď `Manual_ML.txt`).


