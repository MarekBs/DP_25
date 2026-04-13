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

LOCAL_DATA_DIR = "./data_walk"

WINDOW_SIZE = 256   # vzorky na okno
WINDOW_STEP = 128   # krok (50% overlap)

USE_FEATURE_SELECTION = False
TOP_N_FEATURES        = 40
N_FOLDS               = 5

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
    feats[f"{prefix}_velocity"]      = np.trapezoid(np.abs(v))
    feats[f"{prefix}_rms"]           = np.sqrt(np.mean(v**2))
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

def extract_sensor_features(df_xyz, prefix):
    feats = {}
    for axis in ["x", "y", "z"]:
        feats.update(axis_features(df_xyz[axis].values, f"{prefix}_{axis}"))
    x, y, z = df_xyz["x"].values, df_xyz["y"].values, df_xyz["z"].values
    mag = np.sqrt(x**2 + y**2 + z**2)
    feats[f"{prefix}_avg_magnitude"] = np.mean(mag)
    feats[f"{prefix}_cor_xy"]        = float(np.corrcoef(x, y)[0, 1])
    feats[f"{prefix}_cor_xz"]        = float(np.corrcoef(x, z)[0, 1])
    feats[f"{prefix}_cor_yz"]        = float(np.corrcoef(y, z)[0, 1])
    return feats

def cross_sensor_features(acc_df, gyr_df):
    feats = {}
    for axis in ["x", "y", "z"]:
        a = acc_df[axis].values
        g = gyr_df[axis].values
        n = min(len(a), len(g))
        feats[f"accel_gyro_cor_{axis}"] = float(np.corrcoef(a[:n], g[:n])[0, 1]) if n > 2 else 0.0
    return feats

def extract_window_features(window_df):
    acc_df = window_df[["userAcceleration.x", "userAcceleration.y", "userAcceleration.z"]]
    acc_df = acc_df.rename(columns=lambda c: c.split(".")[-1])
    gyr_df = window_df[["rotationRate.x", "rotationRate.y", "rotationRate.z"]]
    gyr_df = gyr_df.rename(columns=lambda c: c.split(".")[-1])

    feats = {}
    feats.update(extract_sensor_features(acc_df, "acc"))
    feats.update(extract_sensor_features(gyr_df, "gyr"))
    feats.update(cross_sensor_features(acc_df, gyr_df))
    for axis in ["x", "y", "z"]:
        feats[f"grav_{axis}_mean"] = window_df[f"gravity.{axis}"].mean()
    return feats

def load_dataset(local_dir, window_size=WINDOW_SIZE, window_step=WINDOW_STEP):
    data_path = Path(local_dir)
    csv_files = sorted(data_path.glob("sub_*.csv"))
    print(f"\nNajdených {len(csv_files)} subjektov")

    all_features, all_labels = [], []

    for csv_file in csv_files:
        subject_id = csv_file.stem
        try:
            df = pd.read_csv(csv_file, sep=None, engine="python")
            df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed") or c.startswith("index")], errors="ignore")
            df = df.apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)

            n_windows = 0
            for start in range(0, len(df) - window_size + 1, window_step):
                window = df.iloc[start : start + window_size]
                feats  = extract_window_features(window)
                all_features.append(feats)
                all_labels.append(subject_id)
                n_windows += 1

            print(f"  {subject_id}: {len(df)} vzoriek → {n_windows} okien")

        except Exception as e:
            print(f"  [CHYBA] {subject_id}: {e}")

    df_feats = pd.DataFrame(all_features).fillna(0)
    print(f"\nDataset: {len(df_feats)} vzoriek x {len(df_feats.columns)} príznakov")
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

        if len(pos_idx) < 5:
            print(f"  [SKIP] {target_user}: málo vzoriek")
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
    }, "walk_model.pkl")
    print(f"\nNajlepší model: {best_name} (avg acc={np.mean(results[best_name]['accs']):.4f}) -> walk_model.pkl")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir",    default=LOCAL_DATA_DIR)
    parser.add_argument("--window-size", type=int, default=WINDOW_SIZE)
    parser.add_argument("--window-step", type=int, default=WINDOW_STEP)
    args = parser.parse_args()

    X, y, feature_names = load_dataset(args.data_dir, args.window_size, args.window_step)
    train_and_evaluate(X, y, feature_names)

if __name__ == "__main__":
    main()
