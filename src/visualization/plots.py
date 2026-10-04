"""Step 3 - EDA and preprocessing figures for the report: python -m src.visualization.plots.

Every figure answers one question asked in README.md and is saved as PNG to
outputs/figures/ so the README renders it on GitHub.
"""

import argparse
import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from src.preprocessing.cleaning import load_cleaned
from src.preprocessing.config import CLEANED_DIR, FIGURE_DIR, HORIZONS, REPORT_DIR, SPLITS, STEM, TIMEZONE, UNITS
from src.preprocessing.features import SCALED_FEATURES, TABULAR_FEATURES, TARGETS, build

# Reference palette (light surface) - see README "Biểu đồ".
SURFACE, INK, INK_2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
SPLIT_COLORS = {"train": BLUE, "val": ORANGE, "test": AQUA}
SEQUENTIAL = LinearSegmentedColormap.from_list(
    "blue", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
DIVERGING = LinearSegmentedColormap.from_list(
    "blue_red", ["#104281", "#3987e5", "#9ec5f4", "#f0efec", "#f3a3a2", "#e34948", "#8f1f1f"])
VN_NAMES = {"T2M": "Nhiệt độ 2 m", "PRECTOTCORR": "Lượng mưa", "RH2M": "Độ ẩm tương đối",
            "PS": "Áp suất bề mặt", "WS2M": "Tốc độ gió 2 m", "WD2M": "Hướng gió 2 m",
            "ALLSKY_SFC_SW_DWN": "Bức xạ sóng ngắn"}
SEASONS = {"Đông (12–2)": [12, 1, 2], "Xuân (3–5)": [3, 4, 5], "Hạ (6–8)": [6, 7, 8], "Thu (9–11)": [9, 10, 11]}


def style():
    plt.rcParams.update({
        "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 10,
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
        "lines.linewidth": 1.6, "legend.frameon": False, "legend.labelcolor": INK_2,
        "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
    })


def save(fig, name, title, subtitle=None):
    """Lay out the panels first, then put title/subtitle above them at a fixed distance."""
    fig.tight_layout()
    height = fig.get_figheight()
    fig.text(0.01, 1 + (0.62 if subtitle else 0.3) / height, title, ha="left", va="bottom",
             fontsize=13, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.01, 1 + 0.22 / height, subtitle, ha="left", va="bottom", fontsize=9.5, color=INK_2)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURE_DIR / name)
    plt.close(fig)
    print("saved", name)


def fig_overview(clean):
    # Only complete local-time months: Jan 2001 starts at 07:00 and Jan 2026 has 7 hours.
    complete = clean["T2M"].resample("MS").count().eq(clean["T2M"].resample("MS").count().index.days_in_month * 24)
    monthly = clean.resample("MS").mean(numeric_only=True)[complete]
    rain = clean["PRECTOTCORR"].resample("MS").sum()[complete]
    panels = [("T2M", monthly["T2M"], "°C"), ("PRECTOTCORR", rain, "mm/tháng"),
              ("RH2M", monthly["RH2M"], "%"), ("PS", monthly["PS"], "kPa"),
              ("WS2M", monthly["WS2M"], "m/s"), ("ALLSKY_SFC_SW_DWN", monthly["ALLSKY_SFC_SW_DWN"], "Wh/m²")]
    fig, axes = plt.subplots(3, 2, figsize=(13, 8.5), sharex=True)
    for ax, (name, series, unit) in zip(axes.flat, panels):
        ax.plot(series.index, series, color=BLUE, linewidth=1.0)
        yearly = series.rolling(12, center=True).mean()
        ax.plot(yearly.index, yearly, color=INK, linewidth=1.6)
        ax.set_title(f"{VN_NAMES[name]} ({name})")
        ax.set_ylabel(unit)
    axes[0, 0].text(0.99, 0.04, "— trung bình trượt 12 tháng", transform=axes[0, 0].transAxes,
                    ha="right", color=INK, fontsize=9)
    save(fig, "01_tong_quan_25_nam.png", "Tổng quan 25 năm dữ liệu (2001–2025), trung bình theo tháng",
         "Chu kỳ năm rất rõ ở nhiệt độ, áp suất và bức xạ; không có đoạn đứt hay bước nhảy bất thường do lỗi dữ liệu.")


def fig_distributions(clean):
    fig, axes = plt.subplots(2, 4, figsize=(14, 6))
    for ax, name in zip(axes.flat, list(UNITS)):
        values = clean[name]
        ax.hist(values, bins=60, color=BLUE, edgecolor=SURFACE, linewidth=0.4)
        ax.set_title(f"{VN_NAMES[name]}  ·  skew = {values.skew():.2f}")
        ax.set_xlabel(f"{name} ({UNITS[name]})")
        ax.grid(axis="x", visible=False)
    axes[0, 1].set_yscale("log")
    axes[0, 1].text(0.97, 0.93, "trục y log", transform=axes[0, 1].transAxes, ha="right", color=MUTED, fontsize=8.5)
    ax = axes.flat[-1]
    ax.axis("off")
    ax.text(0, 0.95, "Đọc nhanh", fontweight="bold", color=INK, va="top")
    ax.text(0, 0.80, "• Mưa lệch phải rất mạnh (skew ≈ 8):\n  46% số giờ = 0 → biến đổi log1p\n"
                     "• Bức xạ = 0 suốt đêm (19h–4h):\n  là vật lý thật, không phải thiếu\n"
                     "• RH bị chặn ở 100% (sương mù/mưa)\n"
                     "• Hướng gió: 0° và 359° là hai đầu\n  của trục → cần mã hóa vòng tròn",
            va="top", color=INK_2, fontsize=9.5, linespacing=1.5)
    save(fig, "02_phan_phoi_bien.png", "Phân phối 7 biến khí tượng gốc (219.144 giờ)",
         "Hình dạng phân phối quyết định phép biến đổi ở bước tạo đặc trưng.")


def fig_month_hour(clean):
    pivot = clean.groupby([clean.index.month, clean.index.hour])["T2M"].mean().unstack()
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 4.8), gridspec_kw={"width_ratios": [1.35, 1]})
    image = ax.imshow(pivot, aspect="auto", cmap=SEQUENTIAL, origin="upper")
    ax.set_xticks(range(0, 24, 2), labels=range(0, 24, 2))
    ax.set_yticks(range(12), labels=[f"T{m}" for m in range(1, 13)])
    ax.set_xlabel("Giờ địa phương (GMT+7)")
    ax.set_title("Nhiệt độ trung bình theo tháng × giờ")
    ax.grid(False)
    fig.colorbar(image, ax=ax, label="°C", pad=0.02)
    for (label, months), color in zip(SEASONS.items(), [BLUE, AQUA, ORANGE, "#4a3aa7"]):
        part = clean[clean.index.month.isin(months)]
        curve = part.groupby(part.index.hour)["T2M"].mean()
        ax2.plot(curve.index, curve, color=color, label=label)
    ax2.set_xlim(0, 23)
    ax2.set_xticks(range(0, 24, 3))
    ax2.set_xlabel("Giờ địa phương (GMT+7)")
    ax2.set_ylabel("°C")
    ax2.set_title("Chu kỳ ngày theo mùa")
    ax2.legend(loc="upper left", fontsize=9)
    save(fig, "03_nhiet_do_thang_gio.png", "Nhiệt độ có hai chu kỳ lồng nhau: theo ngày và theo năm",
         "Đỉnh nhiệt lúc 13–14h, đáy lúc 5–6h (giờ VN) → phải đổi UTC sang GMT+7 và mã hóa giờ/ngày-trong-năm bằng sin/cos.")


def fig_outlier_method(clean):
    t2m = clean["T2M"]
    q1, q3 = t2m.quantile([0.25, 0.75])
    iqr = q3 - q1
    global_hit = (t2m < q1 - 1.5 * iqr) | (t2m > q3 + 1.5 * iqr)
    flags = pd.read_csv(CLEANED_DIR / f"{STEM}_outlier_flags.csv")
    seasonal_hit = flags[(flags.variable == "T2M") & flags.rule.str.startswith("seasonal")]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw={"width_ratios": [1.6, 1]})
    data = [t2m[t2m.index.month == m].to_numpy() for m in range(1, 13)]
    boxes = ax.boxplot(data, positions=range(1, 13), widths=0.6, patch_artist=True, showfliers=False,
                       medianprops={"color": INK, "linewidth": 1.4},
                       whiskerprops={"color": MUTED}, capprops={"color": MUTED})
    for box in boxes["boxes"]:
        box.set(facecolor="#b7d3f6", edgecolor=BLUE, linewidth=1)
    ax.axhline(q1 - 1.5 * iqr, color=RED, linewidth=1.2)
    ax.text(12.4, q1 - 1.5 * iqr + 0.4, f"ngưỡng IQR toàn cục = {q1 - 1.5 * iqr:.1f}°C", color=RED, ha="right", fontsize=9)
    ax.set_xticks(range(1, 13), labels=[f"T{m}" for m in range(1, 13)])
    ax.set_ylabel("°C")
    ax.set_title("Phân phối nhiệt độ theo tháng")
    ax.grid(axis="x", visible=False)
    labels = ["IQR toàn cục", "Robust z theo\n(tháng, giờ), |z|>5"]
    counts = [int(global_hit.sum()), len(seasonal_hit)]
    bars = ax2.barh(labels, counts, color=[RED, BLUE], height=0.5)
    for bar, count in zip(bars, counts):
        ax2.text(bar.get_width() + 15, bar.get_y() + bar.get_height() / 2, f"{count:,} giờ".replace(",", "."),
                 va="center", color=INK, fontsize=10)
    winter = global_hit[global_hit].index.month.isin([12, 1, 2]).mean()
    ax2.set_xlim(0, max(counts) * 1.3)
    ax2.set_title("Số giờ T2M bị coi là ngoại lệ")
    ax2.set_xlabel("số giờ")
    ax2.grid(axis="y", visible=False)
    ax2.text(0, -0.75, f"{winter:.0%} giờ bị IQR toàn cục loại là giờ mùa đông bình thường.\n"
                       "→ Không dùng ngưỡng toàn cục; chỉ gắn cờ, không xóa.", color=INK_2, fontsize=9)
    save(fig, "04_ngoai_le_theo_mua.png", "Vì sao không xóa ngoại lệ bằng IQR toàn cục",
         "Mùa đông Hà Nội lạnh là bình thường; ngưỡng phải so trong cùng tháng và cùng giờ.")


def fig_extreme_events(clean):
    events = [("Đợt rét lịch sử 01/2016", "2016-01-20", "2016-01-29", ["T2M", "PS", "WS2M"]),
              ("Bão Yagi 09/2024", "2024-09-04", "2024-09-11", ["WS2M", "PS", "PRECTOTCORR"])]
    flags = pd.read_csv(CLEANED_DIR / f"{STEM}_outlier_flags.csv")
    flags["timestamp"] = pd.to_datetime(flags["timestamp"], utc=True).dt.tz_convert(TIMEZONE)
    fig, axes = plt.subplots(3, 2, figsize=(14, 7.5))
    for col, (title, start, end, names) in enumerate(events):
        part = clean.loc[start:end]
        for row, name in enumerate(names):
            ax = axes[row, col]
            ax.plot(part.index, part[name], color=BLUE, linewidth=1.3)
            hit = flags[(flags.variable == name) & flags.timestamp.between(part.index[0], part.index[-1])]
            if len(hit):
                ax.scatter(hit.timestamp, hit.value, s=22, color=ORANGE, edgecolor=SURFACE, linewidth=1, zorder=3,
                           label="bị gắn cờ (vẫn giữ)")
                ax.legend(loc="best", fontsize=8.5)
            ax.set_ylabel(UNITS[name])
            ax.set_title(f"{title} — {VN_NAMES[name]}" if row == 0 else VN_NAMES[name])
            ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m", tz=part.index.tz))
    save(fig, "05_su_kien_cuc_tri.png", "Ngoại lệ thống kê = sự kiện thời tiết có thật",
         "Rét 2016: nhiệt độ xuống ~2°C đúng lúc áp suất tăng vọt (không khí lạnh). Bão Yagi: gió cực đại khi áp suất thấp nhất và mưa lớn → các biến khớp nhau về vật lý, nên giữ lại.")


def fig_wind_encoding(clean):
    fig = plt.figure(figsize=(14, 4.4))
    ax = fig.add_subplot(1, 3, 1)
    ax.plot([0, 360], [0, 0], color=AXIS, linewidth=2)
    for deg, color in [(10, BLUE), (350, ORANGE)]:
        ax.scatter(deg, 0, s=80, color=color, zorder=3)
        ax.text(deg, 0.12, f"{deg}°", ha="center", color=INK)
    ax.annotate("", xy=(350, -0.12), xytext=(10, -0.12), arrowprops={"arrowstyle": "<->", "color": RED})
    ax.text(180, -0.27, "|350 − 10| = 340  (sai: tưởng gần ngược chiều)", ha="center", color=RED, fontsize=9.5)
    ax.set_ylim(-0.5, 0.5)
    ax.set_xlim(-15, 375)
    ax.set_yticks([])
    ax.set_xticks([0, 90, 180, 270, 360])
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    ax.set_title("Hướng gió dạng số (0–360°)")
    ax = fig.add_subplot(1, 3, 2)
    angle = np.linspace(0, 2 * np.pi, 300)
    ax.plot(np.sin(angle), np.cos(angle), color=AXIS, linewidth=1.5)
    for deg, color in [(10, BLUE), (350, ORANGE)]:
        r = np.deg2rad(deg)
        ax.scatter(np.sin(r), np.cos(r), s=80, color=color, zorder=3)
        ax.text(np.sin(r) * 1.18, np.cos(r) * 1.12, f"{deg}°", ha="center", color=INK)
    chord = 2 * np.sin(np.deg2rad(10))
    ax.text(0, 0.55, f"khoảng cách = {chord:.2f}\n(tối đa 2.0)", ha="center", color=BLUE, fontsize=9.5)
    for label, (x, y) in {"Bắc 0°": (0, 1.32), "Đông 90°": (1.3, 0), "Nam 180°": (0, -1.3), "Tây 270°": (-1.3, 0)}.items():
        ax.text(x, y, label, ha="center", va="center", color=MUTED, fontsize=8.5)
    ax.set_aspect("equal")
    ax.set_xlim(-1.6, 1.6)
    ax.set_ylim(-1.5, 1.5)
    ax.set_xlabel("sin(hướng)")
    ax.set_ylabel("cos(hướng)")
    ax.set_title("Sau mã hóa (sin, cos): 10° và 350° gần nhau")
    ax = fig.add_subplot(1, 3, 3)
    # Hour-to-hour change of direction measured along the circle (shortest arc).
    change = ((clean["WD2M"].diff() + 180) % 360 - 180).abs()
    speed_bin = pd.cut(clean["WS2M"], bins=[0, 0.5, 1, 1.5, 2, 3, 4, 6, 12], include_lowest=True)
    noise = change.groupby(speed_bin, observed=True).mean()
    ax.bar(range(len(noise)), noise.to_numpy(), color=BLUE, width=0.7)
    ax.bar(0, noise.iloc[0], color=ORANGE, width=0.7)
    ax.set_xticks(range(len(noise)), labels=[f"{max(i.left, 0):g}–{i.right:g}" for i in noise.index], fontsize=8.5)
    ax.text(0, noise.iloc[0] + 1, f"{noise.iloc[0]:.0f}°", ha="center", color=INK, fontsize=9)
    ax.text(len(noise) - 1, noise.iloc[-1] + 1, f"{noise.iloc[-1]:.0f}°", ha="center", color=INK, fontsize=9)
    ax.set_xlabel("tốc độ gió WS2M (m/s)")
    ax.set_ylabel("|Δ hướng| trung bình sau 1 giờ (độ)")
    ax.set_title("Gió càng yếu, hướng gió càng nhiễu")
    ax.grid(axis="x", visible=False)
    save(fig, "06_ma_hoa_huong_gio.png", "Hướng gió phải được mã hóa vòng tròn",
         "Dùng vector gió u = −WS·sin(WD), v = −WS·cos(WD): vừa giải quyết 0°≡360°, vừa tự động giảm trọng số hướng khi gió lặng.")


def fig_wind_rose(clean):
    fig, axes = plt.subplots(1, 4, figsize=(14, 4), subplot_kw={"projection": "polar"})
    bins = np.deg2rad(np.arange(0, 361, 22.5))
    for ax, (label, months) in zip(axes, SEASONS.items()):
        part = clean[clean.index.month.isin(months) & (clean["WS2M"] >= 0.5)]
        shifted = (part["WD2M"] + 11.25) % 360  # centre the N sector on 0°
        counts, _ = np.histogram(np.deg2rad(shifted), bins=bins)
        share = counts / counts.sum() * 100
        ax.bar(bins[:-1], share, width=np.deg2rad(22.5) * 0.9, color=BLUE, edgecolor=SURFACE, linewidth=0.8)
        ax.set_theta_zero_location("N")
        ax.set_theta_direction(-1)
        ax.set_xticks(np.deg2rad([0, 90, 180, 270]), labels=["B", "Đ", "N", "T"])
        ax.set_yticklabels([])
        ax.grid(color=GRID)
        ax.set_title(label, pad=12, loc="center")
        top = int(np.argmax(share))
        ax.text(0.5, -0.17, f"hướng chính: {top * 22.5:.0f}° ({share[top]:.0f}%)", transform=ax.transAxes,
                ha="center", color=INK_2, fontsize=9)
    save(fig, "07_hoa_gio_theo_mua.png", "Hoa gió theo mùa (tỷ lệ % số giờ, bỏ gió lặng)",
         "Gió mùa Đông Bắc vào mùa đông, gió Đông Nam vào mùa hạ: hướng gió mang thông tin về khối khí → giữ lại dưới dạng vector u, v.")


def fig_rain_transform(clean):
    rain = clean["PRECTOTCORR"]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 4))
    ax.hist(rain, bins=80, color=BLUE, edgecolor=SURFACE, linewidth=0.3)
    ax.set_yscale("log")
    ax.set_title(f"Trước: mm/giờ (skew = {rain.skew():.1f})")
    ax.set_xlabel("PRECTOTCORR (mm/giờ)")
    ax.set_ylabel("số giờ (thang log)")
    transformed = np.log1p(rain)
    ax2.hist(transformed, bins=80, color=BLUE, edgecolor=SURFACE, linewidth=0.3)
    ax2.set_yscale("log")
    ax2.set_title(f"Sau: log(1 + mưa) (skew = {transformed.skew():.1f})")
    ax2.set_xlabel("PRECTOTCORR_log1p")
    for a in (ax, ax2):
        a.grid(axis="x", visible=False)
    save(fig, "08_bien_doi_luong_mua.png", "Biến đổi log1p cho lượng mưa",
         "log1p giữ nguyên 0 → 0, nén các trận mưa cực lớn (30 mm/giờ) để không chi phối hệ số hồi quy và gradient của LSTM/GRU.")


def fig_autocorrelation(clean):
    t2m = clean["T2M"]
    lags = np.arange(0, 169)
    acf = np.array([t2m.autocorr(int(k)) if k else 1.0 for k in lags])
    fig, ax = plt.subplots(figsize=(13, 4))
    ax.vlines(lags, 0, acf, color=BLUE, linewidth=1.2)
    for k in [1, 12, 24, 48]:
        ax.scatter(k, acf[k], color=ORANGE, s=36, zorder=3, edgecolor=SURFACE)
        ax.annotate(f"lag {k}h: {acf[k]:.2f}", (k, acf[k]), xytext=(6, 8) if k != 12 else (10, -4),
                    textcoords="offset points", color=INK, fontsize=9)
    ax.set_xticks(range(0, 169, 24))
    ax.set_xlabel("độ trễ (giờ)")
    ax.set_ylabel("tự tương quan")
    ax.set_ylim(0, 1.08)
    ax.grid(axis="x", visible=False)
    save(fig, "09_tu_tuong_quan_nhiet_do.png", "Tự tương quan của nhiệt độ (ACF, 0–168 giờ)",
         "Đỉnh lặp lại mỗi 24h → chọn lag 1, 2, 3, 6, 12, 24h cho hồi quy tuyến tính và cửa sổ 48h (2 chu kỳ ngày) cho LSTM/GRU.")


def fig_horizons(features):
    fig, axes = plt.subplots(1, 4, figsize=(15, 4), sharex=True, sharey=True)
    now = features["T2M"]
    for ax, h, target in zip(axes, HORIZONS, TARGETS):
        valid = features[target].notna()
        ax.hexbin(now[valid], features.loc[valid, target], gridsize=45, cmap=SEQUENTIAL, mincnt=1, bins="log",
                  linewidths=0)
        ax.plot([0, 42], [0, 42], color=INK, linewidth=0.8)
        r = np.corrcoef(now[valid], features.loc[valid, target])[0, 1]
        mad = (features.loc[valid, target] - now[valid]).abs().mean()
        ax.set_title(f"t + {h}h")
        ax.text(0.04, 0.95, f"r = {r:.3f}\n|ΔT| TB = {mad:.2f}°C", transform=ax.transAxes, va="top",
                color=INK, fontsize=9.5)
        ax.set_xlabel("T2M tại t (°C)")
        ax.grid(False)
    axes[0].set_ylabel("T2M tại t + h (°C)")
    save(fig, "10_do_kho_theo_horizon.png", "Độ khó của 4 bài toán dự báo: nhiệt độ hiện tại so với tương lai",
         "Xa hơn → phân tán hơn. 24h lại dễ hơn 12h vì cùng giờ trong ngày; đây là lý do mỗi horizon cần nhãn và đánh giá riêng.")


def fig_correlation(features, split):
    train = features.loc[split.eq("train")]
    corr = train[[*TABULAR_FEATURES, *TARGETS]].corr().loc[TABULAR_FEATURES, TARGETS]
    fig, ax = plt.subplots(figsize=(8, 10))
    image = ax.imshow(corr, cmap=DIVERGING, vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(TARGETS)), labels=TARGETS)
    ax.set_yticks(range(len(TABULAR_FEATURES)), labels=TABULAR_FEATURES)
    ax.xaxis.tick_top()
    for i in range(corr.shape[0]):
        for j in range(corr.shape[1]):
            value = corr.iat[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=8,
                    color="#ffffff" if abs(value) > 0.6 else INK)
    ax.grid(False)
    fig.colorbar(image, ax=ax, fraction=0.04, pad=0.02, label="Pearson r")
    save(fig, "11_tuong_quan_dac_trung_nhan.png", "Tương quan đặc trưng ↔ nhãn (chỉ tập train)",
         "Mỗi horizon có đặc trưng mạnh nhất khác nhau: t+1h/t+24h ← T2M hiện tại (cùng giờ); t+12h ← T2M_lag_12h (cách đích đúng 24h). Các lag tương quan cao với nhau → nên dùng Ridge khi hồi quy.")


def fig_split(features, split):
    daily = features["T2M"].resample("D").mean()
    day_split = split.resample("D").agg(lambda s: s.mode().iat[0] if len(s) else "none")
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(14, 5.2), gridspec_kw={"height_ratios": [3, 1]})
    for name, color in SPLIT_COLORS.items():
        part = daily.where(day_split.eq(name))
        ax.plot(part.index, part, color=color, linewidth=0.7, label=name)
    ax.set_ylabel("T2M trung bình ngày (°C)")
    ax.legend(loc="lower left", ncol=3)
    ax.set_title("Chia theo thời gian (không xáo trộn)")
    counts = split.value_counts()
    left = 0
    for name, color in SPLIT_COLORS.items():
        ax2.barh(0, counts[name], left=left, color=color, height=0.6, edgecolor=SURFACE, linewidth=2)
        start, end = SPLITS[name]
        ax2.text(left + counts[name] / 2, 0, f"{name}: {start[:4]}–{end[:4] if name != 'test' else '2025'}\n"
                 f"{counts[name]:,} mẫu ({counts[name] / counts.drop('none').sum():.0%})".replace(",", "."),
                 ha="center", va="center", color="#ffffff", fontsize=9.5, fontweight="bold")
        left += counts[name]
    ax2.set_xlim(0, left)
    ax2.axis("off")
    save(fig, "12_chia_train_val_test.png", "Train / Validation / Test theo trục thời gian",
         "Mô hình chỉ học quá khứ, đánh giá trên tương lai; 24 giờ cuối mỗi tập bị bỏ để nhãn t+24h không rơi sang tập sau.")


def fig_scaling(features, model_ready, split):
    train = split.eq("train")
    before = features.loc[train, SCALED_FEATURES]
    after = model_ready.loc[train, SCALED_FEATURES]
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(14, 7.5), sharey=True)
    for a, frame, title in [(ax, before, "Trước: đơn vị gốc"), (ax2, after, "Sau: z-score (fit trên train)")]:
        boxes = a.boxplot([frame[c].to_numpy() for c in SCALED_FEATURES], orientation="horizontal", widths=0.6, patch_artist=True,
                          showfliers=False, medianprops={"color": INK}, whiskerprops={"color": MUTED},
                          capprops={"color": MUTED})
        for box in boxes["boxes"]:
            box.set(facecolor="#b7d3f6", edgecolor=BLUE)
        a.set_title(title)
        a.grid(axis="y", visible=False)
    ax.set_xscale("symlog", linthresh=1)
    ax.set_xlabel("giá trị (thang symlog)")
    ax2.set_xlabel("độ lệch chuẩn so với trung bình train")
    ax2.axvline(0, color=AXIS, linewidth=1)
    ax.set_yticks(range(1, len(SCALED_FEATURES) + 1), labels=SCALED_FEATURES)
    save(fig, "13_chuan_hoa_truoc_sau.png", "Chuẩn hóa z-score: đưa mọi đặc trưng về cùng thang đo",
         "Trước chuẩn hóa: áp suất ~100, bức xạ tích lũy ~4.000, mưa log ~0,1. Sau: tất cả quanh 0 với độ lệch chuẩn 1.")


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    style()
    clean = load_cleaned()
    model_ready, _, features = build(clean)
    split = model_ready["split"]
    fig_overview(clean)
    fig_distributions(clean)
    fig_month_hour(clean)
    fig_outlier_method(clean)
    fig_extreme_events(clean)
    fig_wind_encoding(clean)
    fig_wind_rose(clean)
    fig_rain_transform(clean)
    fig_autocorrelation(clean)
    fig_horizons(features)
    fig_correlation(features, split)
    fig_split(features, split)
    fig_scaling(features, model_ready, split)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary = clean[list(UNITS)].describe().round(3)
    summary.to_csv(REPORT_DIR / "descriptive_statistics.csv", encoding="utf-8-sig")
    print(json.dumps({"figures": str(FIGURE_DIR)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
