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
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
import joblib

FIREBASE_BUCKET       = "dpapp-18ab8.firebasestorage.app"
GESTURE_PATH          = "touch_gallery_behametrics"
DIRECTIONS            = ["doprava", "dolava"]
LOCAL_DATA_DIR        = "./data_swipe"
SERVICE_ACCOUNT       = "serviceAccountKey.json"

USE_FEATURE_SELECTION = False
TOP_N_FEATURES        = 40
N_FOLDS               = 5

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
    feats[f"{prefix}_var"]      = np.var(v)
    feats[f"{prefix}_std"]      = np.std(v)
    feats[f"{prefix}_median"]   = np.median(v)
    feats[f"{prefix}_skewness"] = skew(v)
    feats[f"{prefix}_kurtosis"] = sp_kurtosis(v)
    feats[f"{prefix}_q1"]       = np.percentile(v, 25)
    feats[f"{prefix}_q3"]       = np.percentile(v, 75)
    feats[f"{prefix}_iqr"]      = np.percentile(v, 75) - np.percentile(v, 25)

    dt = np.diff(t).clip(min=1e-3)
    feats[f"{prefix}_velocity"]      = np.mean(np.abs(np.diff(v) / dt)) if len(v) > 1 else 0.0
    feats[f"{prefix}_rms"]           = np.sqrt(np.mean(v**2))
    feats[f"{prefix}_zero_crossing"] = int(np.sum(np.diff(np.sign(v - np.mean(v))) != 0))

    peaks, _ = find_peaks(v)
    pv = v[peaks] if len(peaks) > 0 else np.array([0.0])
    feats[f"{prefix}_peak_avg_distance"] = float(np.mean(np.diff(peaks))) if len(peaks) > 1 else 0.0
    feats[f"{prefix}_peak_min"]  = float(np.min(pv))
    feats[f"{prefix}_peak_max"]  = float(np.max(pv))
    feats[f"{prefix}_peak_mean"] = float(np.mean(pv))

    fft = np.abs(np.fft.rfft(v))
    feats[f"{prefix}_fft_sum"] = float(np.sum(fft))
    feats[f"{prefix}_energy"]  = float(np.sum(fft**2))

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
    }, "swipe_model.pkl")
    print(f"\nNajlepší model: {best_name} "
          f"(avg acc={np.mean(results[best_name]['accs']):.4f}) -> swipe_model.pkl")


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
