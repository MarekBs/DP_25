#!/usr/bin/env python3
import re, argparse
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, roc_curve
from sklearn.pipeline import Pipeline
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

FIREBASE_BUCKET = "dpapp-18ab8.firebasestorage.app"
GESTURE_PATH    = "sensors_logs_behametrics/Položenie na stôl"
LOCAL_DATA_DIR  = "./data_stol"
SERVICE_ACCOUNT = "serviceAccountKey.json"

RE_ACCEL = re.compile(r"log(\d+)_sensor_accelerometer\.csv", re.IGNORECASE)
RE_GYRO  = re.compile(r"log(\d+)_sensor_gyroscope\.csv",     re.IGNORECASE)


def sanitize_path(name):
    return re.sub(r'[<>:"/\\|?*()]', '_', name)


def download_from_firebase(local_dir):
    import firebase_admin
    from firebase_admin import credentials, storage as fb_storage

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.Certificate(SERVICE_ACCOUNT),
            {"storageBucket": FIREBASE_BUCKET}
        )

    bucket = fb_storage.bucket()
    blobs  = list(bucket.list_blobs(prefix=GESTURE_PATH + "/"))
    print(f"Firebase: najdených {len(blobs)} suborov")

    for blob in blobs:
        parts = blob.name[len(GESTURE_PATH) + 1:].split("/", 1)
        if len(parts) != 2 or not parts[1].endswith(".csv"):
            continue
        user_id, filename = parts
        safe_user_id = sanitize_path(user_id)
        dest = Path(local_dir) / safe_user_id / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            print(f"  Stahujem: {filename}")
            blob.download_to_filename(str(dest))

    print("Hotovo.")


def parse_file(filepath):
    df = pd.read_csv(filepath, header=None,
                     names=["sensor", "user_id", "timestamp_ns", "x", "y", "z"])
    df = df[["x", "y", "z"]].apply(pd.to_numeric, errors="coerce").dropna()
    return df.reset_index(drop=True)


def trim_gesture(df, smooth=5, padding=10):
    mag       = np.sqrt(df["x"]**2 + df["y"]**2 + df["z"]**2)
    mag       = mag.rolling(window=smooth, center=True, min_periods=1).mean()
    threshold = 0.15 * np.percentile(mag, 95)
    active    = np.where(mag > threshold)[0]
    if len(active) == 0:
        return df
    start = max(0, active[0] - padding)
    end   = min(len(df) - 1, active[-1] + padding)
    return df.iloc[start:end + 1].reset_index(drop=True)


def extract_features(df, prefix):
    feats = {}
    for axis in ["x", "y", "z"]:
        v = df[axis].values
        feats[f"{prefix}_{axis}_mean"]  = np.mean(v)
        feats[f"{prefix}_{axis}_std"]   = np.std(v)
        feats[f"{prefix}_{axis}_min"]   = np.min(v)
        feats[f"{prefix}_{axis}_max"]   = np.max(v)
        feats[f"{prefix}_{axis}_range"] = np.max(v) - np.min(v)
        feats[f"{prefix}_{axis}_rms"]   = np.sqrt(np.mean(v ** 2))
    mag = np.sqrt(df["x"]**2 + df["y"]**2 + df["z"]**2)
    feats[f"{prefix}_mag_mean"] = np.mean(mag)
    feats[f"{prefix}_mag_std"]  = np.std(mag)
    feats[f"{prefix}_mag_max"]  = np.max(mag)
    return feats


def load_dataset(local_dir):
    data_path = Path(local_dir)
    user_dirs = sorted([d for d in data_path.iterdir() if d.is_dir()])
    print(f"\nNajdených {len(user_dirs)} pouzivatelov")

    all_features, all_labels = [], []

    for user_dir in user_dirs:
        attempts = defaultdict(dict)
        for f in user_dir.glob("*.csv"):
            m = RE_ACCEL.match(f.name) or RE_GYRO.match(f.name)
            if m:
                key = "accel" if "accelerometer" in f.name.lower() else "gyro"
                attempts[int(m.group(1))][key] = f

        valid = 0
        for attempt_num, files in sorted(attempts.items()):
            if "accel" not in files or "gyro" not in files:
                continue
            try:
                gyro  = parse_file(files["gyro"])
                gyro  = trim_gesture(gyro)
                accel = parse_file(files["accel"])
                accel = accel.iloc[:len(gyro)].reset_index(drop=True)
                if len(accel) < 10 or len(gyro) < 10:
                    continue
                feats = {}
                feats.update(extract_features(accel, "acc"))
                feats.update(extract_features(gyro,  "gyr"))
                all_features.append(feats)
                all_labels.append(user_dir.name)
                valid += 1
            except Exception as e:
                print(f"  [CHYBA] {user_dir.name} pokus {attempt_num}: {e}")

    df_feats = pd.DataFrame(all_features).fillna(0)
    print(f"Dataset: {len(df_feats)} vzoriek x {len(df_feats.columns)} priznakov")
    return df_feats.values.astype(np.float64), np.array(all_labels), df_feats.columns.tolist()


def compute_eer(y_test, y_proba, classes):
    eer_list = []
    for i, user in enumerate(classes):
        if i >= y_proba.shape[1]:
            continue
        y_binary = (y_test == i).astype(int)
        if len(np.unique(y_binary)) < 2:
            continue
        fpr, tpr, _ = roc_curve(y_binary, y_proba[:, i])
        fnr = 1 - tpr
        idx = np.argmin(np.abs(fpr - fnr))
        eer_list.append((user, (fpr[idx] + fnr[idx]) / 2))
    return eer_list


def train_and_evaluate(X, y, feature_names):
    le           = LabelEncoder()
    y_enc        = le.fit_transform(y)
    labels_clean = np.array([re.sub(r'[^\x00-\x7F]+', '', c) for c in le.classes_])

    counts = np.bincount(y_enc)
    valid_mask = np.isin(y_enc, np.where(counts >= 2)[0])
    if not valid_mask.all():
        removed = le.classes_[counts < 2]
        print(f"  [UPOZORNENIE] Vyhodeni (malo vzoriek): {list(removed)}")
        X, y_enc = X[valid_mask], y_enc[valid_mask]

    cv = StratifiedKFold(n_splits=max(2, min(5, min(np.bincount(y_enc)))),
                         shuffle=True, random_state=42)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.25, random_state=42, stratify=y_enc
    )

    models = {
        "SVM": Pipeline([("scaler", StandardScaler()),
                         ("clf", SVC(kernel="rbf", C=10, gamma="scale", probability=True, random_state=42))]),
        "Random Forest": Pipeline([("scaler", StandardScaler()),
                                   ("clf", RandomForestClassifier(n_estimators=300, random_state=42, n_jobs=-1))]),
    }

    results = {}
    for name, model in models.items():
        cv_scores = cross_val_score(model, X, y_enc, cv=cv, scoring="accuracy")
        model.fit(X_train, y_train)
        y_pred  = model.predict(X_test)
        y_proba = model.predict_proba(X_test)
        acc     = accuracy_score(y_test, y_pred)
        eer_list = compute_eer(y_test, y_proba, le.classes_)
        mean_eer = np.mean([e for _, e in eer_list])
        results[name] = {"model": model, "cv": cv_scores, "acc": acc,
                         "y_test": y_test, "y_pred": y_pred, "eer": mean_eer}

    print(f"\n{'Model':<20} {'CV acc':>10} {'Test acc':>10} {'EER':>8}")
    print("-" * 52)
    for name, res in results.items():
        print(f"{name:<20} {res['cv'].mean():.4f}+-{res['cv'].std():.3f}  {res['acc']:.4f}  {res['eer']*100:.2f}%")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, (name, res) in zip(axes, results.items()):
        sns.heatmap(confusion_matrix(res["y_test"], res["y_pred"]),
                    annot=True, fmt="d", ax=ax, cmap="Blues",
                    xticklabels=labels_clean, yticklabels=labels_clean)
        ax.set_title(f"{name}  (acc={res['acc']:.3f})")
        ax.set_xlabel("Predikované"); ax.set_ylabel("Skutočné")
        ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.savefig("confusion_matrices_stol.png", dpi=150, bbox_inches="tight")
    plt.close()

    importances = results["Random Forest"]["model"].named_steps["clf"].feature_importances_
    top_n   = min(20, len(feature_names))
    top_idx = np.argsort(importances)[::-1][:top_n]
    fig2, ax2 = plt.subplots(figsize=(9, 6))
    ax2.barh(range(top_n), importances[top_idx[::-1]], color="steelblue")
    ax2.set_yticks(range(top_n))
    ax2.set_yticklabels([feature_names[i] for i in top_idx[::-1]], fontsize=8)
    ax2.set_title("Feature importance — Random Forest (Stol)")
    plt.tight_layout()
    plt.savefig("feature_importance_stol.png", dpi=150, bbox_inches="tight")
    plt.close()

    best = max(results, key=lambda k: results[k]["acc"])
    joblib.dump({"model": results[best]["model"], "label_encoder": le,
                 "feature_names": feature_names}, "gesture_model_stol.pkl")
    print(f"Najlepsi model ({best}, acc={results[best]['acc']:.4f}) -> gesture_model_stol.pkl")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--data-dir", default=LOCAL_DATA_DIR)
    args = parser.parse_args()

    if args.download:
        download_from_firebase(args.data_dir)

    X, y, feature_names = load_dataset(args.data_dir)
    train_and_evaluate(X, y, feature_names)


if __name__ == "__main__":
    main()
