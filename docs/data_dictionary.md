# Từ điển dữ liệu sạch — NASA POWER Hà Nội 2001–2025

File: `data/cleaned/nasa_power/hanoi_hourly_20010101_20251231_clean.csv` (tạo bởi `python -m src.preprocessing.cleaning`). Mỗi dòng là một giờ Việt Nam (GMT+7) tại điểm lưới 21.0285°N, 105.8542°E. Khóa là `timestamp`; trục thời gian liên tục, không trùng. Quy tắc làm sạch và lý do: [README mục 5](../README.md#5-bước-2--làm-sạch-dữ-liệu). Các cột của dữ liệu mô hình: [processed_data_dictionary.md](processed_data_dictionary.md).

| Trường | Đơn vị | Ý nghĩa |
|---|---|---|
| `timestamp` | — | Giờ Việt Nam, ISO 8601 có `+07:00`, ví dụ `2001-01-01T07:00:00+07:00` |
| `T2M` | °C | Nhiệt độ không khí ở 2 m |
| `PRECTOTCORR` | mm/giờ | Lượng mưa đã hiệu chỉnh |
| `RH2M` | % | Độ ẩm tương đối ở 2 m |
| `PS` | kPa | Áp suất bề mặt |
| `WS2M` | m/s | Tốc độ gió ở 2 m |
| `WD2M` | độ | Hướng gió thổi đến từ, [0, 360), 0 = Bắc; 360 đã đổi thành 0 |
| `ALLSKY_SFC_SW_DWN` | Wh/m² | Bức xạ sóng ngắn xuống bề mặt |
| `is_inserted_hour` | 0/1 | 1 nếu giờ này không có trong file nguồn và được chèn vào trục thời gian |
| `is_imputed` | 0/1 | 1 nếu ít nhất một biến của giờ này được nội suy (khoảng thiếu ≤ 3 giờ) |
| `imputed_columns` | — | Tên các biến được nội suy, ngăn bằng `\|`; `none` nếu không có |
| `outlier_flags` | — | Tên các biến bị gắn cờ ngoại lệ thống kê ở giờ này; `none` nếu không có. **Giá trị vẫn giữ nguyên** |

Giá trị trống trong các cột khí tượng chỉ xuất hiện khi khoảng thiếu dài hơn 3 giờ (hiện tại: không có).

`*_outlier_flags.csv`: một dòng cho mỗi ô bị gắn cờ — `timestamp`, `variable`, `value`, `robust_z` (trống với quy tắc không dùng z), `rule` (`seasonal_robust_z>5`, `wet_hour_q99.9>…`, `hourly_jump>8C`).

`*.metadata.json`: thống kê trước/sau làm sạch, số ô bị xử lý ở từng bước, hash SHA-256 của CSV và đường dẫn log (`outputs/logs/data/`). Bản sao: [outputs/reports/cleaning_report.json](../outputs/reports/cleaning_report.json).
