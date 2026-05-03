# Behaviorálna biometria – autentifikácia používateľa

Systém autentifikácie používateľa na základe behaviorálnych biometrík.  
Používateľ je rozpoznávaný podľa spôsobu vykonávania dotykových gest a pohybov zariadenia.

Projekt pozostáva z:
- Android aplikácie na zber dát
- Python skriptov na tréning modelov strojového učenia

---

## Štruktúra projektu

```
├── app/             # Android aplikácia (Kotlin)
├── ml_training/     # Skripty na tréning modelov
│   └── multimodal/  # Kombinácia dotykových dát a senzorov
└── data/            # Tréningové dáta
                    # (swipe, zoom, walk, stol, zdvihnutie)
```

---

## Požiadavky

- Python 3.9+

### Inštalácia závislostí

```bash
pip install numpy pandas scipy scikit-learn xgboost joblib optuna
```

---

## Použitie

1. Spusti Android aplikáciu na zber dát  
2. Ulož dáta do priečinka `data/`  
3. Spusti tréning modelov:

```bash
cd ml_training
python train.py
```

---

## Dáta

Projekt pracuje s viacerými typmi behaviorálnych dát:
- swipe (potiahnutie)
- zoom (priblíženie)
- walk (chôdza)
- stol (položené zariadenie)
- zdvihnutie (zdvihnutie zariadenia k uchu)

---

## Modely

Modely využívajú kombináciu:
- dotykových gest
- senzorických dát (akcelerometer, gyroskop)

Použité algoritmy:
- Random Forest
- SVM
- KNN
- XGBoost
- optimalizácia pomocou Optuna

---

## Dokumentácia

Podrobný popis skriptov, spúšťacích príkazov a štruktúry modelov sa nachádza v:

```
Manual.txt
```

