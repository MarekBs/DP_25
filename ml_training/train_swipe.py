#!/usr/bin/env python3
import re, argparse
import numpy as np
import pandas as pd
from pathlib import Path
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
GESTURE_PATH    = "touch_gallery_behametrics"
DIRECTIONS      = ["doprava", "dolava"]
LOCAL_DATA_DIR  = "./data_swipe"
SERVICE_ACCOUNT = "serviceAccountKey.json"

RE_TOUCH = re.compile(r"kolo(\d+)_(doprava|dolava)_touch\.csv", re.IGNORECASE)

TOUCH_COLS = ["type", "user_id", "timestamp_ns", "action", "action_detail",
              "pointer_id", "x", "y", "pressure", "size",
              "touch_major", "touch_minor", "raw_x", "raw_y"]


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
    total  = 0
    for direction in DIRECTIONS:
        prefix = f"{GESTURE_PATH}/{direction}/"
        blobs  = list(bucket.list_blobs(prefix=prefix))
        print(f"Firebase [{direction}]: najdených {len(blobs)} suborov")

        for blob in blobs:
            parts = blob.name[len(prefix):].split("/", 1)
            if len(parts) != 2 or not parts[1].endswith(".csv"):
                continue
            user_id, filename = parts
            if not RE_TOUCH.match(filename):
                continue
            safe_user_id = sanitize_path(user_id)
            dest = Path(local_dir) / safe_user_id / filename
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                print(f"  Stahujem: {user_id}/{filename}")
                blob.download_to_filename(str(dest))
                total += 1

    print(f"Hotovo. Stiahnutých {total} nových suborov.")


def parse_touch_file(filepath):
    df = pd.read_csv(filepath, header=None, names=TOUCH_COLS)
    for col in ["timestamp_ns", "pointer_id"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["x", "y", "pressure", "size", "touch_major", "touch_minor"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["timestamp_ns", "x", "y"], inplace=True)
    df = df[df["pointer_id"] == 0].copy()
    df.sort_values("timestamp_ns", inplace=True)
    return df.reset_index(drop=True)


MIN_POINTS   = 5
MIN_DISTANCE = 150

def segment_gestures(df, expected_direction):
    segments  = []
    start_idx = None
    for i, row in df.iterrows():
        if row["action"] == "down":
            start_idx = i
        elif row["action"] == "up" and start_idx is not None:
            seg = df.loc[start_idx:i].copy()
            if seg.iloc[-1]["x"] == 0:
                seg = seg.iloc[:-1]
            seg = seg.reset_index(drop=True)
            if len(seg) >= MIN_POINTS:
                delta_x = seg["x"].iloc[-1] - seg["x"].iloc[0]
                dist    = np.sqrt(delta_x**2 + (seg["y"].iloc[-1] - seg["y"].iloc[0])**2)
                correct_dir = (expected_direction == "doprava" and delta_x < 0) or \
                              (expected_direction == "dolava"  and delta_x > 0)
                if dist >= MIN_DISTANCE and correct_dir:
                    segments.append(seg)
            start_idx = None
    return segments


def axis_features(v, t, prefix):
    feats = {}
    feats[f"{prefix}_min"]      = np.min(v)
    feats[f"{prefix}_max"]      = np.max(v)
    feats[f"{prefix}_mean"]     = np.mean(v)
    feats[f"{prefix}_std"]      = np.std(v)
    feats[f"{prefix}_median"]   = np.median(v)
    feats[f"{prefix}_skewness"] = skew(v)
    feats[f"{prefix}_kurtosis"] = sp_kurtosis(v)
    feats[f"{prefix}_iqr"]      = np.percentile(v, 75) - np.percentile(v, 25)

    dt = np.diff(t).clip(min=1e-3)
    feats[f"{prefix}_velocity"]      = np.mean(np.abs(np.diff(v) / dt)) if len(v) > 1 else 0.0
    feats[f"{prefix}_rms"]           = np.sqrt(np.mean(v**2))
    feats[f"{prefix}_zero_crossing"] = int(np.sum(np.diff(np.sign(v - np.mean(v))) != 0))

    peaks, _ = find_peaks(v)
    pv = v[peaks] if len(peaks) > 0 else np.array([0.0])
    feats[f"{prefix}_peak_max"]  = float(np.max(pv))
    feats[f"{prefix}_peak_mean"] = float(np.mean(pv))

    fft = np.abs(np.fft.rfft(v))
    feats[f"{prefix}_energy"] = float(np.sum(fft**2))

    return feats


def extract_features(df, direction_label, screen_w=1080.0, screen_h=2340.0):
    feats = {}
    x = df["x"].values / screen_w
    y = df["y"].values / screen_h
    t = (df["timestamp_ns"].values - df["timestamp_ns"].values[0]) / 1e6

    feats.update(axis_features(x, t, "x"))
    feats.update(axis_features(y, t, "y"))

    feats["cor_xy"] = float(np.corrcoef(x, y)[0, 1]) if len(x) > 1 else 0.0

    dx          = np.diff(x)
    dy          = np.diff(y)
    steps       = np.sqrt(dx**2 + dy**2)
    total_path  = np.sum(steps)
    direct_dist = np.sqrt((x[-1] - x[0])**2 + (y[-1] - y[0])**2)

    feats["duration_ms"]  = t[-1] - t[0] if len(t) > 1 else 0.0
    feats["total_path"]   = total_path
    feats["straightness"] = direct_dist / total_path if total_path > 0 else 1.0
    feats["direct_dist"]  = direct_dist
    feats["start_x"]      = x[0]
    feats["start_y"]      = y[0]
    feats["end_x"]        = x[-1]
    feats["end_y"]        = y[-1]

    pressure = df["pressure"].values
    feats["pressure_mean"] = float(np.mean(pressure))
    feats["pressure_std"]  = float(np.std(pressure))
    feats["pressure_max"]  = float(np.max(pressure))
    feats["pressure_min"]  = float(np.min(pressure))

    size = df["size"].replace(0, np.nan).fillna(df["size"].mean()).values
    feats["size_mean"] = float(np.mean(size))
    feats["size_std"]  = float(np.std(size))

    major = df["touch_major"].replace(0, np.nan).fillna(df["touch_major"].mean()).values
    minor = df["touch_minor"].replace(0, np.nan).fillna(df["touch_minor"].mean()).values
    feats["touch_major_mean"] = float(np.mean(major))
    feats["touch_minor_mean"] = float(np.mean(minor))
    feats["aspect_ratio"]     = float(np.mean(major) / np.mean(minor)) if np.mean(minor) > 0 else 1.0

    feats["swipe_direction"] = 1.0 if direction_label == "doprava" else -1.0

    return feats


def estimate_screen_size(user_dir):
    all_x, all_y = [], []
    for f in user_dir.glob("*.csv"):
        if not RE_TOUCH.match(f.name):
            continue
        try:
            df = parse_touch_file(f)
            df = df[df["action"] != "up"]
            all_x.extend(df["x"].dropna().tolist())
            all_y.extend(df["y"].dropna().tolist())
        except:
            pass
    if not all_x:
        return 1080.0, 2340.0
    return max(all_x), max(all_y)


def load_dataset(local_dir):
    data_path = Path(local_dir)
    user_dirs = sorted([d for d in data_path.iterdir() if d.is_dir()])
    print(f"\nNajdených {len(user_dirs)} pouzivatelov")

    all_features, all_labels = [], []

    for user_dir in user_dirs:
        screen_w, screen_h = estimate_screen_size(user_dir)
        for f in sorted(user_dir.glob("*.csv")):
            m = RE_TOUCH.match(f.name)
            if not m:
                continue
            direction = m.group(2).lower()
            try:
                df       = parse_touch_file(f)
                segments = segment_gestures(df, direction)
                for seg in segments:
                    all_features.append(extract_features(seg, direction, screen_w, screen_h))
                    all_labels.append(user_dir.name)
            except Exception as e:
                print(f"  [CHYBA] {user_dir.name} / {f.name}: {e}")

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

    cv = StratifiedKFold(n_splits=max(2, min(5, min(np.bincount(y_trainval)))),
                         shuffle=True, random_state=42)

    models = {
        "SVM": Pipeline([("scaler", StandardScaler()),
                         ("clf", SVC(kernel="rbf", C=10, gamma="scale", probability=True, random_state=42))]),
        "Random Forest": Pipeline([("scaler", StandardScaler()),
                                   ("clf", RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, n_jobs=-1))]),
        "XGBoost": Pipeline([("scaler", StandardScaler()),
                             ("clf", XGBClassifier(eval_metric="mlogloss", random_state=42, n_jobs=-1))]),
        "KNN": Pipeline([("scaler", StandardScaler()),
                         ("clf", KNeighborsClassifier(n_neighbors=5, metric="euclidean"))]),
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
    plt.savefig("confusion_matrices_swipe.png", dpi=150, bbox_inches="tight")
    plt.close()

    hdr = f"\n{'Model':<20} {'Acc':>6} {'FAR':>6} {'FRR':>6} {'EER':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'AUC':>6} {'Hits':>8} {'Miss':>8}"
    print(hdr)
    print("-" * len(hdr))
    for name, res in results.items():
        biometric_report(name, res["model"], X_test, res["y_test"], le)

    best = max(results, key=lambda k: results[k]["acc"])
    joblib.dump({"model": results[best]["model"], "label_encoder": le,
                 "feature_names": feature_names}, "swipe_model.pkl")
    print(f"Najlepsi model ({best}, acc={results[best]['acc']:.4f}) -> swipe_model.pkl")


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
