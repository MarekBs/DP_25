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
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import confusion_matrix, accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, roc_curve
from sklearn.pipeline import Pipeline
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

LOCAL_DATA_DIR = "./data_walk"

WINDOW_SIZE = 256   # vzorky na okno
WINDOW_STEP = 128   # krok (50% overlap)


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


def load_dataset(local_dir, window_size=WINDOW_SIZE, window_step=WINDOW_STEP, test_ratio=0.25):
    data_path = Path(local_dir)
    csv_files = sorted(data_path.glob("sub_*.csv"))
    print(f"\nNajdených {len(csv_files)} subjektov")

    all_features, all_labels, all_splits = [], [], []

    for csv_file in csv_files:
        subject_id = csv_file.stem
        try:
            df = pd.read_csv(csv_file, sep=None, engine="python")
            df = df.drop(columns=[c for c in df.columns if c.startswith("Unnamed") or c.startswith("index")], errors="ignore")
            df = df.apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)

            split_row = int(len(df) * (1 - test_ratio))
            n_train = n_test = 0
            for start in range(0, len(df) - window_size + 1, window_step):
                window = df.iloc[start : start + window_size]
                feats  = extract_window_features(window)
                all_features.append(feats)
                all_labels.append(subject_id)
                if start + window_size <= split_row:
                    all_splits.append("train")
                    n_train += 1
                else:
                    all_splits.append("test")
                    n_test += 1

            print(f"  {subject_id}: {len(df)} vzoriek → {n_train} train okien, {n_test} test okien")

        except Exception as e:
            print(f"  [CHYBA] {subject_id}: {e}")

    df_feats = pd.DataFrame(all_features).fillna(0)
    print(f"\nDataset: {len(df_feats)} vzoriek x {len(df_feats.columns)} príznakov")
    return df_feats.values.astype(np.float64), np.array(all_labels), np.array(all_splits), df_feats.columns.tolist()


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

    acc  = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, average="macro", zero_division=0)
    rec  = recall_score(y_test, y_pred, average="macro", zero_division=0)
    f1   = f1_score(y_test, y_pred, average="macro", zero_division=0)
    total_hits = int(np.sum(y_pred == y_test))
    total_miss = int(np.sum(y_pred != y_test))
    print(f"{name:<20} {acc:>6.3f} {np.mean(fars):>6.3f} {np.mean(frrs):>6.3f} {np.mean(eers):>6.3f} "
          f"{prec:>6.3f} {rec:>6.3f} {f1:>6.3f} {np.mean(aucs):>6.3f} {total_hits:>8} {total_miss:>8}")


def train_and_evaluate(X, y, splits, feature_names):
    le           = LabelEncoder()
    y_enc        = le.fit_transform(y)
    labels_clean = np.array([re.sub(r'[^\x00-\x7F]+', '', c) for c in le.classes_])

    counts = np.bincount(y_enc)
    valid_mask = np.isin(y_enc, np.where(counts >= 2)[0])
    if not valid_mask.all():
        removed = le.classes_[counts < 2]
        print(f"  [UPOZORNENIE] Vyhodení (málo vzoriek): {list(removed)}")
        X, y_enc, splits = X[valid_mask], y_enc[valid_mask], splits[valid_mask]

    train_mask = splits == "train"
    test_mask  = splits == "test"
    X_trainval, y_trainval = X[train_mask], y_enc[train_mask]
    X_test,     y_test     = X[test_mask],  y_enc[test_mask]

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
    plt.savefig("confusion_matrices_walk.png", dpi=150, bbox_inches="tight")
    plt.close()

    hdr = f"\n{'Model':<20} {'Acc':>6} {'FAR':>6} {'FRR':>6} {'EER':>6} {'Prec':>6} {'Rec':>6} {'F1':>6} {'AUC':>6} {'Hits':>8} {'Miss':>8}"
    print(hdr)
    print("-" * len(hdr))
    for name, res in results.items():
        biometric_report(name, res["model"], X_test, res["y_test"], le)

    best = max(results, key=lambda k: results[k]["acc"])
    joblib.dump({"model": results[best]["model"], "label_encoder": le,
                 "feature_names": feature_names}, "walk_model.pkl")
    print(f"\nNajlepší model ({best}, acc={results[best]['acc']:.4f}) -> walk_model.pkl")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir",    default=LOCAL_DATA_DIR)
    parser.add_argument("--window-size", type=int, default=WINDOW_SIZE)
    parser.add_argument("--window-step", type=int, default=WINDOW_STEP)
    args = parser.parse_args()

    X, y, splits, feature_names = load_dataset(args.data_dir, args.window_size, args.window_step)
    train_and_evaluate(X, y, splits, feature_names)


if __name__ == "__main__":
    main()
