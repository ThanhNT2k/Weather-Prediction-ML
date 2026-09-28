import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path


def ensure_dir(p: Path) -> None:
    """Create parent directories for *p* if they do not exist."""
    p.parent.mkdir(parents=True, exist_ok=True)


def generate_histograms(csv_path: Path, img_dir: Path, md_path: Path) -> None:
    """Create a histogram for every numeric column in *csv_path*.

    * Each PNG is saved as ``hist_<column>.png`` inside *img_dir*.
    * A Markdown report that embeds all images is written to *md_path*.
    """
    df = pd.read_csv(csv_path)
    numeric_cols = df.select_dtypes(include="number").columns

    lines = ["# Variable‑by‑Variable Histograms",
             "",
             f"Source CSV: `{csv_path.name}`",
             ""]

    for col in numeric_cols:
        # ---- save figure ----
        plt.figure(figsize=(6, 4))
        sns.histplot(df[col].dropna(), bins=30, kde=False, color="steelblue")
        plt.title(f"Histogram of {col}")
        plt.xlabel(col)
        plt.ylabel("Count")
        plt.tight_layout()
        img_path = img_dir / f"hist_{col}.png"
        ensure_dir(img_path)
        plt.savefig(img_path, dpi=200)
        plt.close()

        # ---- markdown entry ----
        lines.append(f"## {col}")
        # Use a relative path from the markdown file (docs/) to assets directory
        rel_path = Path("assets") / img_path.name
        lines.append(f"![]({rel_path})")
        lines.append("")

    # Write the markdown report
    ensure_dir(md_path)
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Histogram report written to {md_path}")


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parents[2]
    # Choose the cleaned CSV (adjust if you want the raw one)
    CSV = ROOT / "data" / "processed" / "nasa_power" / "hanoi_hourly_20230101_20241231_features_1h.csv"
    IMG_DIR = ROOT / "docs" / "assets"
    MD_FILE = ROOT / "docs" / "histograms_report.md"

    generate_histograms(CSV, IMG_DIR, MD_FILE)
