#!/usr/bin/env python3
import re, argparse
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import skew, kurtosis as sp_kurtosis
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import KNeighborsClassifier
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, roc_curve
from sklearn.pipeline import Pipeline
import matplotlib.pyplot as plt
import joblib

FIREBASE_BUCKET       = "dpapp-18ab8.firebasestorage.app"
GESTURE_PATH          = "touch_zoom_behametrics"
LOCAL_DATA_DIR        = "./data_zoom"
SERVICE_ACCOUNT       = "serviceAccountKey.json"

USE_FEATURE_SELECTION = False
TOP_N_FEATURES        = 40

RE_TOUCH = re.compile(r"log(\d+)_touch\.csv", re.IGNORECASE)

TOUCH_COLS = ["type", "user_id", "timestamp_ns", "action", "action_detail",
              "pointer_id", "x", "y", "pressure", "size",
              "touch_major", "touch_minor", "raw_x", "raw_y"]

MIN_FRAMES      = 5
MIN_DIST_CHANGE = 50    # minimálna zmena vzdialenosti prstov (px)
GAP_NS          = 200_000_000  # 200ms = nový segment
MARGIN_NS       = 50_000_000   # 50ms kontext okolo segmentu


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
        if not RE_TOUCH.match(filename):
            continue
        safe_user_id = sanitize_path(user_id)
        dest = Path(local_dir) / safe_user_id / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            print(f"  Stahujem: {filename}")
            blob.download_to_filename(str(dest))

    print("Hotovo.")


def parse_touch_file(filepath):
    df = pd.read_csv(filepath, header=None, names=TOUCH_COLS)
    for col in ["timestamp_ns", "pointer_id"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["x", "y", "pressure", "size", "touch_major", "touch_minor"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df.dropna(subset=["timestamp_ns", "pointer_id", "x", "y"], inplace=True)
    df["pointer_id"] = df["pointer_id"].astype(int)
    df.sort_values("timestamp_ns", inplace=True)
    return df.reset_index(drop=True)


def segment_gestures(df):
    p1 = df[df["pointer_id"] == 1].sort_values("timestamp_ns")
    if p1.empty:
        return []

    seg_ranges = []
    seg_start  = p1.iloc[0]["timestamp_ns"]
    seg_end    = p1.iloc[0]["timestamp_ns"]

    for _, row in p1.iterrows():
        if row["timestamp_ns"] - seg_end > GAP_NS:
            seg_ranges.append((seg_start, seg_end))
            seg_start = row["timestamp_ns"]
        seg_end = row["timestamp_ns"]
    seg_ranges.append((seg_start, seg_end))

    segments = []
    for start_ts, end_ts in seg_ranges:
        seg = df[(df["timestamp_ns"] >= start_ts - MARGIN_NS) &
                 (df["timestamp_ns"] <= end_ts   + MARGIN_NS)].copy()
        if 0 not in seg["pointer_id"].values or 1 not in seg["pointer_id"].values:
            continue
        if len(seg) < MIN_FRAMES:
            continue
        segments.append(seg.reset_index(drop=True))

    return segments


def build_distance_series(df):
    moves = df[df["action"].isin(["move", "down", "pointer_down"])].copy()
    moves["time_ms"] = (moves["timestamp_ns"] - moves["timestamp_ns"].min()) / 1e6

    p0 = moves[moves["pointer_id"] == 0][["time_ms", "x", "y"]].rename(columns={"x": "x0", "y": "y0"})
    p1 = moves[moves["pointer_id"] == 1][["time_ms", "x", "y"]].rename(columns={"x": "x1", "y": "y1"})

    if p0.empty or p1.empty:
        return None, None

    p0 = p0.sort_values("time_ms").reset_index(drop=True)
    p1 = p1.sort_values("time_ms").reset_index(drop=True)
    merged = pd.merge_asof(p0, p1, on="time_ms", direction="nearest", tolerance=20.0)
    merged.dropna(inplace=True)

    if len(merged) < MIN_FRAMES:
        return None, None

    dist = np.sqrt((merged["x1"] - merged["x0"])**2 + (merged["y1"] - merged["y0"])**2)
    return merged["time_ms"].values, dist.values


def is_valid_zoom(times, dists):
    if times is None or len(dists) < MIN_FRAMES:
        return False
    return abs(dists[-1] - dists[0]) >= MIN_DIST_CHANGE


def extract_features(times_ms, distances, seg_df=None):
    feats = {}
    d = distances
    t = times_ms
    duration = t[-1] - t[0] if len(t) > 1 else 0.0

    feats["dist_initial"]   = d[0]
    feats["dist_final"]     = d[-1]
    feats["dist_delta"]     = d[-1] - d[0]
    feats["zoom_factor"]    = d[-1] / d[0] if d[0] > 0 else 1.0
    feats["dist_min"]       = np.min(d)
    feats["dist_max"]       = np.max(d)
    feats["dist_mean"]      = np.mean(d)
    feats["dist_var"]       = np.var(d)
    feats["dist_std"]       = np.std(d)
    feats["dist_range"]     = np.max(d) - np.min(d)
    feats["dist_median"]    = np.median(d)
    feats["dist_q1"]        = np.percentile(d, 25)
    feats["dist_q3"]        = np.percentile(d, 75)
    feats["dist_iqr"]       = np.percentile(d, 75) - np.percentile(d, 25)
    feats["dist_skew"]      = float(skew(d))        if len(d) > 2 else 0.0
    feats["dist_kurt"]      = float(sp_kurtosis(d)) if len(d) > 3 else 0.0
    feats["duration_ms"]    = duration
    feats["zoom_direction"] = 1.0 if feats["dist_delta"] > 0 else -1.0

    if len(d) >= 4:
        feats["dist_at_25pct"] = d[len(d) // 4]
        feats["dist_at_50pct"] = d[len(d) // 2]
        feats["dist_at_75pct"] = d[3 * len(d) // 4]
    else:
        feats["dist_at_25pct"] = feats["dist_at_50pct"] = feats["dist_at_75pct"] = d[0]

    if len(d) > 1 and duration > 0:
        dt       = np.diff(t).clip(min=1e-3)
        velocity = np.diff(d) / dt
        feats["vel_mean"]            = np.mean(velocity)
        feats["vel_std"]             = np.std(velocity)
        feats["vel_max"]             = np.max(np.abs(velocity))
        mid = len(velocity) // 2
        feats["vel_first_half"]      = np.mean(velocity[:mid]) if mid > 0 else 0.0
        feats["vel_second_half"]     = np.mean(velocity[mid:]) if mid < len(velocity) else 0.0
        feats["n_direction_changes"] = float(np.sum(np.diff(np.sign(velocity)) != 0))
        if len(velocity) > 1:
            accel = np.diff(velocity)
            feats["accel_mean"] = np.mean(accel)
            feats["accel_std"]  = np.std(accel)
        else:
            feats["accel_mean"] = feats["accel_std"] = 0.0
    else:
        for k in ["vel_mean", "vel_std", "vel_max", "vel_first_half", "vel_second_half",
                  "n_direction_changes", "accel_mean", "accel_std"]:
            feats[k] = 0.0

    if seg_df is not None:
        moves = seg_df[seg_df["action"].isin(["move", "down", "pointer_down"])].copy()
        moves["time_ms"] = (moves["timestamp_ns"] - moves["timestamp_ns"].min()) / 1e6
        p0 = moves[moves["pointer_id"] == 0].sort_values("time_ms")
        p1 = moves[moves["pointer_id"] == 1].sort_values("time_ms")

        if not p0.empty and not p1.empty:
            cx_start = (p0["x"].iloc[0] + p1["x"].iloc[0]) / 2
            cy_start = (p0["y"].iloc[0] + p1["y"].iloc[0]) / 2
            cx_end   = (p0["x"].iloc[-1] + p1["x"].iloc[-1]) / 2
            cy_end   = (p0["y"].iloc[-1] + p1["y"].iloc[-1]) / 2
            feats["centroid_x_start"] = cx_start
            feats["centroid_y_start"] = cy_start
            feats["centroid_x_end"]   = cx_end
            feats["centroid_y_end"]   = cy_end
            feats["centroid_dx"]      = cx_end - cx_start
            feats["centroid_dy"]      = cy_end - cy_start
            feats["centroid_disp"]    = np.sqrt(feats["centroid_dx"]**2 + feats["centroid_dy"]**2)

            feats["angle_start"] = np.degrees(np.arctan2(
                p1["y"].iloc[0] - p0["y"].iloc[0], p1["x"].iloc[0] - p0["x"].iloc[0]))
            feats["angle_end"]   = np.degrees(np.arctan2(
                p1["y"].iloc[-1] - p0["y"].iloc[-1], p1["x"].iloc[-1] - p0["x"].iloc[-1]))
            feats["angle_delta"] = feats["angle_end"] - feats["angle_start"]

            def path_length(pts_x, pts_y):
                return float(np.sum(np.sqrt(np.diff(pts_x.values)**2 + np.diff(pts_y.values)**2)))

            feats["p0_path_length"] = path_length(p0["x"], p0["y"])
            feats["p1_path_length"] = path_length(p1["x"], p1["y"])
            feats["path_asymmetry"] = abs(feats["p0_path_length"] - feats["p1_path_length"])

            feats["p0_disp"] = np.sqrt((p0["x"].iloc[-1] - p0["x"].iloc[0])**2 +
                                       (p0["y"].iloc[-1] - p0["y"].iloc[0])**2)
            feats["p1_disp"] = np.sqrt((p1["x"].iloc[-1] - p1["x"].iloc[0])**2 +
                                       (p1["y"].iloc[-1] - p1["y"].iloc[0])**2)

            dur0 = p0["time_ms"].iloc[-1] - p0["time_ms"].iloc[0] + 1e-3
            dur1 = p1["time_ms"].iloc[-1] - p1["time_ms"].iloc[0] + 1e-3
            feats["p0_vel"]        = feats["p0_path_length"] / dur0
            feats["p1_vel"]        = feats["p1_path_length"] / dur1
            feats["vel_asymmetry"] = abs(feats["p0_vel"] - feats["p1_vel"])

            all_x = pd.concat([p0["x"], p1["x"]])
            all_y = pd.concat([p0["y"], p1["y"]])
            feats["bbox_width"]  = all_x.max() - all_x.min()
            feats["bbox_height"] = all_y.max() - all_y.min()

            feats["bbox_aspect"]   = feats["bbox_width"] / (feats["bbox_height"] + 1e-3)

            size = moves["size"].replace(0, np.nan).fillna(moves["size"].mean())
            feats["size_mean"] = float(size.mean())
            feats["size_std"]  = float(size.std()) if len(size) > 1 else 0.0

            major = moves["touch_major"].replace(0, np.nan).fillna(moves["touch_major"].mean())
            minor = moves["touch_minor"].replace(0, np.nan).fillna(moves["touch_minor"].mean())
            feats["touch_major_mean"] = float(major.mean())
            feats["touch_minor_mean"] = float(minor.mean())
            feats["aspect_ratio"]     = float(major.mean() / minor.mean()) if minor.mean() > 0 else 1.0
        else:
            for k in ["centroid_x_start", "centroid_y_start", "centroid_x_end", "centroid_y_end",
                      "centroid_dx", "centroid_dy", "centroid_disp",
                      "angle_start", "angle_end", "angle_delta",
                      "p0_path_length", "p1_path_length", "path_asymmetry",
                      "p0_disp", "p1_disp", "p0_vel", "p1_vel", "vel_asymmetry",
                      "bbox_width", "bbox_height", "bbox_aspect",
                      "size_mean", "size_std", "touch_major_mean", "touch_minor_mean",
                      "aspect_ratio"]:
                feats[k] = 0.0

    return feats


def load_dataset(local_dir):
    data_path = Path(local_dir)
    user_dirs = sorted([d for d in data_path.iterdir() if d.is_dir()])
    print(f"\nNajdených {len(user_dirs)} pouzivatelov")

    all_features, all_labels = [], []

    for user_dir in user_dirs:
        for f in sorted(user_dir.glob("*.csv")):
            if not RE_TOUCH.match(f.name):
                continue
            try:
                df       = parse_touch_file(f)
                segments = segment_gestures(df)
                for seg in segments:
                    times, dists = build_distance_series(seg)
                    if not is_valid_zoom(times, dists):
                        continue
                    all_features.append(extract_features(times, dists, seg_df=seg))
                    all_labels.append(user_dir.name)
                    break
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
                          "precs": [], "recs": [], "f1s": [], "hits": [], "misses": []}
                   for name in model_names}
    best_models = {name: {} for name in model_names}

    for target_user in users:
        y_bin = (y == target_user).astype(int)

        rng     = np.random.default_rng(42)
        pos_idx = np.where(y_bin == 1)[0]
        neg_idx = np.where(y_bin == 0)[0]
        rng.shuffle(pos_idx)
        rng.shuffle(neg_idx)
        neg_idx = neg_idx[:len(pos_idx)]  # vyváženie: rovnaký počet neg ako pos

        if len(pos_idx) < 2:
            print(f"  [SKIP] {target_user}: príliš málo pozitívnych vzoriek")
            continue

        n_pos_test = max(1, int(round(len(pos_idx) * 0.25)))
        n_neg_test = max(1, int(round(len(neg_idx) * 0.25)))

        test_idx  = np.concatenate([pos_idx[:n_pos_test], neg_idx[:n_neg_test]])
        train_idx = np.concatenate([pos_idx[n_pos_test:], neg_idx[n_neg_test:]])

        X_train, y_train = X[train_idx], y_bin[train_idx]
        X_test,  y_test  = X[test_idx],  y_bin[test_idx]

        if len(np.unique(y_train)) < 2:
            continue

        for name, model in make_models().items():
            model.fit(X_train, y_train)
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

    hdr = f"\n{'Model':<20} {'Acc':>6} {'FAR':>6} {'FRR':>6} {'EER':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'AUC':>6} {'Hits':>8} {'Miss':>8}"
    print(hdr)
    print("-" * len(hdr))
    for name in model_names:
        r = results[name]
        if not r["accs"]:
            continue
        print(f"{name:<20} {np.mean(r['accs']):>6.3f} {np.mean(r['fars']):>6.3f} "
              f"{np.mean(r['frrs']):>6.3f} {np.mean(r['eers']):>6.3f} {np.mean(r['precs']):>6.3f} "
              f"{np.mean(r['recs']):>6.3f} {np.mean(r['f1s']):>6.3f} {np.mean(r['aucs']):>6.3f} "
              f"{sum(r['hits']):>8} {sum(r['misses']):>8}")

    fig, axes = plt.subplots(1, len(model_names), figsize=(24, 5))
    for ax, name in zip(axes, model_names):
        r = results[name]
        if not r["eers"]:
            continue
        ax.bar(range(len(r["eers"])), r["eers"], color="steelblue")
        ax.axhline(np.mean(r["eers"]), color="red", linestyle="--",
                   label=f'Avg EER={np.mean(r["eers"]):.3f}')
        ax.set_title(f"{name}\nFAR={np.mean(r['fars']):.3f}  FRR={np.mean(r['frrs']):.3f}")
        ax.set_xlabel("Používateľ (index)")
        ax.set_ylabel("EER")
        ax.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig("binary_results_zoom.png", dpi=150, bbox_inches="tight")
    plt.close()

    best_name = max(model_names, key=lambda k: np.mean(results[k]["accs"]) if results[k]["accs"] else 0)
    joblib.dump({
        "models": best_models[best_name],
        "feature_names": feature_names,
        "model_type": best_name,
    }, "zoom_model.pkl")
    print(f"\nNajlepší model: {best_name} "
          f"(avg acc={np.mean(results[best_name]['accs']):.4f}) -> zoom_model.pkl")


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
