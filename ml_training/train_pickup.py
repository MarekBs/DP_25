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
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
import joblib

FIREBASE_BUCKET       = "dpapp-18ab8.firebasestorage.app"
GESTURE_PATH          = "sensors_logs_behametrics/Zdvihnutie k uchu"
LOCAL_DATA_DIR        = "./data_zdvihnutie"
SERVICE_ACCOUNT       = "serviceAccountKey.json"

USE_FEATURE_SELECTION = False
TOP_N_FEATURES        = 80
N_FOLDS               = 5

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
    feats[f"{prefix}_var"]      = np.var(v)
    feats[f"{prefix}_std"]      = np.std(v)
    feats[f"{prefix}_median"]   = np.median(v)
    feats[f"{prefix}_skewness"] = skew(v)
    feats[f"{prefix}_kurtosis"] = sp_kurtosis(v)
    feats[f"{prefix}_q1"]       = np.percentile(v, 25)
    feats[f"{prefix}_q3"]       = np.percentile(v, 75)
    feats[f"{prefix}_iqr"]      = np.percentile(v, 75) - np.percentile(v, 25)
    feats[f"{prefix}_velocity"]   = np.trapezoid(np.abs(v))
    feats[f"{prefix}_rms"]       = np.sqrt(np.mean(v**2))
    feats[f"{prefix}_zero_crossing"] = int(np.sum(np.diff(np.sign(v - np.mean(v))) != 0))
    peaks, _ = find_peaks(v)
    peak_vals = v[peaks] if len(peaks) > 0 else np.array([0.0])
    feats[f"{prefix}_n_peaks"]   = len(peaks)
    feats[f"{prefix}_peak_min"]  = float(np.min(peak_vals))
    feats[f"{prefix}_peak_max"]  = float(np.max(peak_vals))
    feats[f"{prefix}_peak_mean"] = float(np.mean(peak_vals))
    fft = np.abs(np.fft.rfft(v))
    feats[f"{prefix}_fft_sum"] = float(np.sum(fft))
    feats[f"{prefix}_energy"]  = float(np.sum(fft**2))
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


def make_models():
    return {
        "SVM": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(kernel="rbf", C=1.0, gamma="scale", probability=True, random_state=42))
        ]),
        "Random Forest": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1))
        ]),
        "XGBoost": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", XGBClassifier(n_estimators=100, max_depth=6, learning_rate=0.3,
                                   eval_metric="logloss", random_state=42, n_jobs=-1))
        ]),
        "KNN": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", KNeighborsClassifier(n_neighbors=5))
        ]),
    }


def select_features(X, y, feature_names):
    rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
    rf.fit(X, y)
    top_idx = np.argsort(rf.feature_importances_)[::-1][:TOP_N_FEATURES]
    print(f"Feature selection: top {TOP_N_FEATURES} z {X.shape[1]} príznakov")
    return X[:, top_idx], [feature_names[i] for i in top_idx]


def train_and_evaluate(X, y, feature_names):
    if USE_FEATURE_SELECTION:
        X, feature_names = select_features(X, y, feature_names)

    users       = np.unique(y)
    model_names = list(make_models().keys())
    results     = {name: {"fars": [], "frrs": [], "eers": [], "aucs": [], "accs": [],
                          "precs": [], "recs": [], "f1s": [], "hits": [], "misses": [],
                          "cv_aucs": []}
                   for name in model_names}
    best_models = {name: {} for name in model_names}

    for target_user in users:
        y_bin = (y == target_user).astype(int)

        rng     = np.random.default_rng(42)
        pos_idx = np.where(y_bin == 1)[0]
        neg_idx = np.where(y_bin == 0)[0]
        rng.shuffle(pos_idx)
        rng.shuffle(neg_idx)
        neg_idx = neg_idx[:len(pos_idx)]

        if len(pos_idx) < 2:
            print(f"  [SKIP] {target_user}: príliš málo pozitívnych vzoriek")
            continue

        n_pos_test = max(1, int(round(len(pos_idx) * 0.30)))
        n_neg_test = max(1, int(round(len(neg_idx) * 0.30)))

        test_idx     = np.concatenate([pos_idx[:n_pos_test], neg_idx[:n_neg_test]])
        trainval_idx = np.concatenate([pos_idx[n_pos_test:], neg_idx[n_neg_test:]])

        X_trainval, y_trainval = X[trainval_idx], y_bin[trainval_idx]
        X_test,     y_test     = X[test_idx],     y_bin[test_idx]

        if len(np.unique(y_trainval)) < 2:
            continue

        n_splits = min(N_FOLDS, int(np.min(np.bincount(y_trainval))))
        if n_splits < 2:
            continue
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)

        for name, model in make_models().items():
            cv_auc = cross_val_score(model, X_trainval, y_trainval,
                                     cv=cv, scoring="roc_auc").mean()
            model.fit(X_trainval, y_trainval)
            y_pred  = model.predict(X_test)
            y_proba = model.predict_proba(X_test)[:, 1]

            TP = int(((y_pred == 1) & (y_test == 1)).sum())
            FP = int(((y_pred == 1) & (y_test == 0)).sum())
            TN = int(((y_pred == 0) & (y_test == 0)).sum())
            FN = int(((y_pred == 0) & (y_test == 1)).sum())

            FAR = FP / (FP + TN) if (FP + TN) > 0 else 0.0
            FRR = FN / (FN + TP) if (FN + TP) > 0 else 0.0

            if len(np.unique(y_test)) > 1:
                fpr_c, tpr_c, _ = roc_curve(y_test, y_proba)
                fnr_c = 1 - tpr_c
                eer = float((fpr_c + fnr_c)[np.argmin(np.abs(fpr_c - fnr_c))]) / 2
                auc = roc_auc_score(y_test, y_proba)
            else:
                eer = auc = 0.0

            results[name]["cv_aucs"].append(cv_auc)
            results[name]["fars"].append(FAR)
            results[name]["frrs"].append(FRR)
            results[name]["eers"].append(eer)
            results[name]["aucs"].append(auc)
            results[name]["accs"].append(accuracy_score(y_test, y_pred))
            results[name]["precs"].append(precision_score(y_test, y_pred, zero_division=0))
            results[name]["recs"].append(recall_score(y_test, y_pred, zero_division=0))
            results[name]["f1s"].append(f1_score(y_test, y_pred, zero_division=0))
            results[name]["hits"].append(int((y_pred == y_test).sum()))
            results[name]["misses"].append(int((y_pred != y_test).sum()))
            best_models[name][target_user] = model

    hdr = f"\n{'Model':<20} {'Acc':>6} {'FAR':>6} {'FRR':>6} {'EER':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'AUC':>6} {'CV-AUC':>8} {'Hits':>8} {'Miss':>8}"
    print(hdr)
    print("-" * len(hdr))
    for name in model_names:
        r = results[name]
        if not r["accs"]:
            continue
        print(f"{name:<20} {np.mean(r['accs']):>6.3f} {np.mean(r['fars']):>6.3f} "
              f"{np.mean(r['frrs']):>6.3f} {np.mean(r['eers']):>6.3f} {np.mean(r['precs']):>6.3f} "
              f"{np.mean(r['recs']):>6.3f} {np.mean(r['f1s']):>6.3f} {np.mean(r['aucs']):>6.3f} "
              f"{np.mean(r['cv_aucs']):>8.3f} {sum(r['hits']):>8} {sum(r['misses']):>8}")

    best_name = max(model_names, key=lambda k: np.mean(results[k]["accs"]) if results[k]["accs"] else 0)
    joblib.dump({
        "models": best_models[best_name],
        "feature_names": feature_names,
        "model_type": best_name,
    }, "gesture_model_zdvihnutie.pkl")
    print(f"\nNajlepší model: {best_name} "
          f"(avg acc={np.mean(results[best_name]['accs']):.4f}) -> gesture_model_zdvihnutie.pkl")


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
