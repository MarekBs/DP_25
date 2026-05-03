 Systém autentifikácie používateľa na základe behaviorálnych biometrík – rozpoznávanie používateľa podľa spôsobu vykonávania dotykových gest a pohybov zariadenia. Projekt pozostáva z Android aplikácie na zber dát a Python      
  skriptov na tréning ML modelov.                                                                                                                                                                                                   
                                                                                                                                                                                                                                    
  ---             
  Štruktúra

  ├── app/             – Android aplikácia (Kotlin)
  ├── ml_training/     – skripty na tréning modelov
  │   └── multimodal/  – varianty kombinujúce dotyk + senzory
  └── data/            – tréningové dáta (swipe, zoom, walk, stol, zdvihnutie)

  ---
  Požiadavky

  Python 3.9+

  pip install numpy pandas scipy scikit-learn xgboost joblib optuna

  ---
  Dokumentácia

  Podrobný popis skriptov, spúšťacích príkazov a štruktúry modelov: Manual.txt
