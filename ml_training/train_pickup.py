import re, argparse
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict
from scipy.stats import skew, kurtosis as sp_kurtosis
from scipy.signal import find_peaks
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.metrics import confusion_matrix, accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, roc_curve
from sklearn.pipeline import Pipeline
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

FIREBASE_BUCKET = "dpapp-18ab8.firebasestorage.app"
GESTURE_PATH    = "sensors_logs_behametrics/Zdvihnutie k uchu"
LOCAL_DATA_DIR  = "./data_zdvihnutie"
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
            print(f"  Stahujem: {user_id}/{filename}")
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


def axis_features(v, prefix):
    feats = {}
    feats[f"{prefix}_min"]      = np.min(v)
    feats[f"{prefix}_max"]      = np.max(v)
    feats[f"{prefix}_mean"]     = np.mean(v)
    feats[f"{prefix}_std"]      = np.std(v)
    feats[f"{prefix}_median"]   = np.median(v)
    feats[f"{prefix}_skewness"] = skew(v)
    feats[f"{prefix}_kurtosis"] = sp_kurtosis(v)
    feats[f"{prefix}_q1"]       = np.percentile(v, 25)
    feats[f"{prefix}_q3"]       = np.percentile(v, 75)
    feats[f"{prefix}_iqr"]      = np.percentile(v, 75) - np.percentile(v, 25)
    feats[f"{prefix}_velocity"]  = np.trapezoid(np.abs(v))
    feats[f"{prefix}_rms"]       = np.sqrt(np.mean(v**2))
    feats[f"{prefix}_zero_crossing"] = int(np.sum(np.diff(np.sign(v - np.mean(v))) != 0))
    peaks, _ = find_peaks(v)
    peak_vals = v[peaks] if len(peaks) > 0 else np.array([0.0])
    feats[f"{prefix}_peak_avg_distance"] = float(np.mean(np.diff(peaks))) if len(peaks) > 1 else 0.0
    feats[f"{prefix}_peak_min"]  = float(np.min(peak_vals))
    feats[f"{prefix}_peak_max"]  = float(np.max(peak_vals))
    feats[f"{prefix}_peak_mean"] = float(np.mean(peak_vals))
    feats[f"{prefix}_waveform_length"] = float(np.sum(np.abs(np.diff(v))))
    feats[f"{prefix}_autocorr_lag1"]   = float(np.corrcoef(v[:-1], v[1:])[0, 1]) if len(v) > 2 else 0.0
    fft = np.abs(np.fft.rfft(v))
    feats[f"{prefix}_energy"]          = float(np.sum(fft**2))
    feats[f"{prefix}_dominant_freq"]   = float(np.argmax(fft))
    p = fft / (np.sum(fft) + 1e-12)
    feats[f"{prefix}_spectral_entropy"] = float(-np.sum(p * np.log(p + 1e-12)))
    return feats


def extract_features(df, prefix):
    feats = {}
    for axis in ["x", "y", "z"]:
        feats.update(axis_features(df[axis].values, f"{prefix}_{axis}"))

    x, y, z = df["x"].values, df["y"].values, df["z"].values
    mag = np.sqrt(x**2 + y**2 + z**2)
    feats[f"{prefix}_avg_magnitude"] = np.mean(mag)
    feats[f"{prefix}_cor_xy"]        = float(np.corrcoef(x, y)[0, 1])
    feats[f"{prefix}_cor_xz"]        = float(np.corrcoef(x, z)[0, 1])
    feats[f"{prefix}_cor_yz"]        = float(np.corrcoef(y, z)[0, 1])
    return feats


def cross_sensor_features(accel, gyro):
    feats = {}
    for axis in ["x", "y", "z"]:
        a = accel[axis].values
        g = gyro[axis].values
        n = min(len(a), len(g))
        feats[f"accel_gyro_cor_{axis}"] = float(np.corrcoef(a[:n], g[:n])[0, 1]) if n > 2 else 0.0
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
                feats.update(cross_sensor_features(accel, gyro))
                all_features.append(feats)
                all_labels.append(user_dir.name)
                valid += 1
            except Exception as e:
                print(f"  [CHYBA] {user_dir.name} pokus {attempt_num}: {e}")

    df_feats = pd.DataFrame(all_features).fillna(0)
    print(f"Dataset: {len(df_feats)} vzoriek x {len(df_feats.columns)} priznakov")
    return df_feats.values.astype(np.float64), np.array(all_labels), df_feats.columns.tolist()


def biometric_report(name, model, X_test, y_test, le):
    y_pred  = model.predict(X_test)
    y_proba = model.predict_proba(X_test)
    fars, frrs, eers, aucs = [], [], [], []
    for i in range(len(le.classes_)):
        y_bin      = (y_test == i).astype(int)
        y_pred_bin = (y_pred  == i).astype(int)
        if y_bin.sum() == 0:
            continue
        TP = int(((y_pred_bin == 1) & (y_bin == 1)).sum())
        FP = int(((y_pred_bin == 1) & (y_bin == 0)).sum())
        TN = int(((y_pred_bin == 0) & (y_bin == 0)).sum())
        FN = int(((y_pred_bin == 0) & (y_bin == 1)).sum())
        fars.append(FP / (FP + TN) if (FP + TN) > 0 else 0.0)
        frrs.append(FN / (FN + TP) if (FN + TP) > 0 else 0.0)
        if len(np.unique(y_bin)) > 1:
            fpr_c, tpr_c, _ = roc_curve(y_bin, y_proba[:, i])
            fnr_c = 1 - tpr_c
            eers.append(float((fpr_c + fnr_c)[np.argmin(np.abs(fpr_c - fnr_c))]) / 2)
            aucs.append(roc_auc_score(y_bin, y_proba[:, i]))

    total_hits = int(np.sum(y_pred == y_test))
    total_miss = int(np.sum(y_pred != y_test))
    acc  = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, average="macro", zero_division=0)
    rec  = recall_score(y_test, y_pred, average="macro", zero_division=0)
    f1   = f1_score(y_test, y_pred, average="macro", zero_division=0)
    print(f"{name:<20} {acc:>6.3f} {np.mean(fars):>6.3f} {np.mean(frrs):>6.3f} {np.mean(eers):>6.3f} "
          f"{prec:>6.3f} {rec:>6.3f} {f1:>6.3f} {np.mean(aucs):>6.3f} {total_hits:>8} {total_miss:>8}")


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

    rng = np.random.default_rng(42)
    train_idx, test_idx = [], []
    for uid in np.unique(y_enc):
        idx = np.where(y_enc == uid)[0]
        rng.shuffle(idx)
        n_test = max(1, int(round(len(idx) * 0.25)))
        test_idx.extend(idx[:n_test])
        train_idx.extend(idx[n_test:])

    X_trainval, y_trainval = X[train_idx], y_enc[train_idx]
    X_test,     y_test     = X[test_idx],  y_enc[test_idx]

    cv = StratifiedKFold(n_splits=max(2, min(5, int(np.min(np.bincount(y_trainval))))),
                         shuffle=True, random_state=42)

    models = {
        "SVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(
                kernel="rbf",
                C=1.0,
                gamma="scale",
                probability=True,
                random_state=42
            ))
        ]),
        "Random Forest": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(
                n_estimators=100,
                max_depth=None,
                min_samples_split=2,
                min_samples_leaf=1,
                random_state=42,
                n_jobs=-1
            ))
        ]),
        "XGBoost": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.3,
                subsample=1.0,
                eval_metric="mlogloss",
                random_state=42,
                n_jobs=-1
            ))
        ]),
        "KNN": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", KNeighborsClassifier(
                n_neighbors=5,
                weights="uniform",
                metric="minkowski",
                p=2
            ))
        ]),
    }

    results = {}
    for name, model in models.items():
        cv_scores = cross_val_score(model, X_trainval, y_trainval, cv=cv, scoring="accuracy")
        model.fit(X_trainval, y_trainval)
        y_pred = model.predict(X_test)
        acc    = accuracy_score(y_test, y_pred)
        results[name] = {"model": model, "cv": cv_scores, "acc": acc,
                         "y_test": y_test, "y_pred": y_pred}

    print(f"\n{'Model':<20} {'CV acc':>10} {'Test acc':>10}")
    print("-" * 42)
    for name, res in results.items():
        print(f"{name:<20} {res['cv'].mean():.4f}+-{res['cv'].std():.3f}  {res['acc']:.4f}")

    fig, axes = plt.subplots(1, 4, figsize=(28, 6))
    for ax, (name, res) in zip(axes, results.items()):
        sns.heatmap(confusion_matrix(res["y_test"], res["y_pred"]),
                    annot=True, fmt="d", ax=ax, cmap="Blues",
                    xticklabels=labels_clean, yticklabels=labels_clean)
        ax.set_title(f"{name}  (acc={res['acc']:.3f})")
        ax.set_xlabel("Predikované"); ax.set_ylabel("Skutočné")
        ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()
    plt.savefig("confusion_matrices_zdvihnutie.png", dpi=150, bbox_inches="tight")
    plt.close()

    hdr = f"\n{'Model':<20} {'Acc':>6} {'FAR':>6} {'FRR':>6} {'EER':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'AUC':>6} {'Hits':>8} {'Miss':>8}"
    print(hdr)
    print("-" * len(hdr))
    for name, res in results.items():
        biometric_report(name, res["model"], X_test, res["y_test"], le)

    best = max(results, key=lambda k: results[k]["acc"])
    joblib.dump({"model": results[best]["model"], "label_encoder": le,
                 "feature_names": feature_names}, "gesture_model_zdvihnutie.pkl")
    print(f"\nNajlepsi model ({best}, acc={results[best]['acc']:.4f}) -> gesture_model_zdvihnutie.pkl")


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
