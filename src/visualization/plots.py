import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path

# ---------------------------------------------------------------------------
# Helper: ensure output directory exists
# ---------------------------------------------------------------------------
def ensure_dir(path: Path) -> None:
    """Create parent directories for *path* if they do not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Plot 1 – Correlation matrix (heat‑map)
# ---------------------------------------------------------------------------
def correlation_plot(csv_path: Path, out_path: Path) -> None:
    """Save a Pearson correlation heat‑map for all numeric columns.

    Parameters
    ----------
    csv_path: Path
        Path to a CSV file (raw or cleaned).
    out_path: Path
        Destination PNG file.
    """
    df = pd.read_csv(csv_path)
    # Keep only numeric columns – this mirrors the logic used elsewhere.
    numeric_df = df.select_dtypes(include="number")
    if numeric_df.empty:
        raise ValueError("No numeric columns found in the CSV.")
    corr = numeric_df.corr()

    plt.figure(figsize=(12, 10))
    sns.heatmap(
        corr,
        cmap="coolwarm",
        annot=False,
        fmt=".2f",
        linewidths=0.5,
        cbar_kws={"shrink": 0.5},
    )
    plt.title(f"Correlation matrix – {csv_path.name}")
    plt.tight_layout()
    ensure_dir(out_path)
    plt.savefig(out_path, dpi=300)
    plt.close()

# ---------------------------------------------------------------------------
# Plot 2 – Simple time‑series line plot (example: temperature)
# ---------------------------------------------------------------------------
def time_series_plot(csv_path: Path, column: str, out_path: Path) -> None:
    """Plot a time‑series of *column* against the ``timestamp`` column.

    The function expects a ``timestamp`` column that can be parsed by ``pd.to_datetime``.
    """
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    if "timestamp" not in df.columns:
        raise KeyError("CSV must contain a 'timestamp' column for time‑series plotting.")
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found in CSV.")

    plt.figure(figsize=(12, 4))
    plt.plot(df["timestamp"], df[column], linewidth=1)
    plt.xlabel("Timestamp")
    plt.ylabel(column.replace("_", " ").title())
    plt.title(f"{column.replace('_', ' ').title()} over time")
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.tight_layout()
    ensure_dir(out_path)
    plt.savefig(out_path, dpi=300)
    plt.close()

# ---------------------------------------------------------------------------
# Main entry point – generate a small report of images
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parents[2]
    # Paths to the raw and cleaned CSVs used throughout the project
    RAW_CSV = ROOT / "data" / "raw" / "nasa_power" / "hanoi_hourly_20230101_20241231.csv"
    CLEAN_CSV = (
        ROOT
        / "data"
        / "processed"
        / "nasa_power"
        / "hanoi_hourly_20230101_20241231_features_1h.csv"
    )

    # Destination folder for the generated figures (inside docs/assets)
    FIG_DIR = ROOT / "docs" / "assets"

    # 1️⃣ Correlation heat‑maps for raw and cleaned data
    correlation_plot(RAW_CSV, FIG_DIR / "corr_raw.png")
    correlation_plot(CLEAN_CSV, FIG_DIR / "corr_clean.png")

    # 2️⃣ Example time‑series plot – temperature (T2M) from the cleaned dataset
    # Adjust the column name if the dataset uses a slightly different name.
    temp_column = "T2M"  # air temperature at 2 m (°C)
    try:
        time_series_plot(CLEAN_CSV, temp_column, FIG_DIR / "temp_series.png")
    except Exception as e:
        # If the expected column does not exist, fall back to the first numeric column.
        df_clean = pd.read_csv(CLEAN_CSV)
        numeric_cols = df_clean.select_dtypes(include="number").columns.tolist()
        if numeric_cols:
            fallback = numeric_cols[0]
            time_series_plot(CLEAN_CSV, fallback, FIG_DIR / "temp_series.png")
        else:
            raise RuntimeError("No numeric columns available for a time‑series plot.")

    print(f"Plots generated in {FIG_DIR}")
