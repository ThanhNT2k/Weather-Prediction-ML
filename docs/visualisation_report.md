# Data Visualisation Report

This report presents a quick visual overview of the **NASA POWER** weather data for Hanoi, both **raw** and **cleaned** versions.

---
## 1️⃣ Correlation Matrices

### Raw data correlation matrix

![Raw correlation matrix](assets/corr_raw.png)

The heat‑map shows the Pearson correlation between all numeric columns in the raw CSV. Strong positive relationships (e.g., between temperature and humidity) can be observed, as well as weaker or negative correlations.

---
### Cleaned data correlation matrix

![Cleaned correlation matrix](assets/corr_clean.png)

After cleaning, some metadata columns have been removed and missing values imputed. The overall correlation pattern remains similar, but a few spurious correlations disappear.

---
## 2️⃣ Temperature Time‑Series (Cleaned Data)

![Temperature over time](assets/temp_series.png)

A line plot of the air temperature at 2 m (`T2M`) across the whole time span. This visual helps spot seasonal trends, outliers, and any gaps remaining after cleaning.

---
### How to regenerate the figures

The figures are produced by the script **`src/visualization/plots.py`**. Run it from the project root:

```bash
python src/visualization/plots.py
```

The script writes the PNG files to `docs/assets/`. The markdown file references them via the relative `assets/` path, so they render correctly on GitHub, in the Antigravity UI, or any Markdown viewer that respects relative links.
