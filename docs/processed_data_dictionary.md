# Từ điển dữ liệu mô hình — dự báo T2M t+1h/6h/12h/24h

File: `data/processed/nasa_power/hanoi_t2m_model_ready.csv` (tạo bởi `python -m src.preprocessing.features`). Bảng liên tục theo giờ, 219.144 dòng × 32 cột. Danh sách cột máy đọc được nằm trong `hanoi_t2m_model_ready.metadata.json` (`sequence_features`, `tabular_features`, `targets`). Lý do của từng đặc trưng: [README mục 7](../README.md#7-bước-4--tạo-đặc-trưng-và-nhãn).

Cột ghi "z" đã được chuẩn hóa `(x − mean_train) / std_train`, tham số trong `scaler.json`. Đơn vị ở bảng dưới là đơn vị **trước** chuẩn hóa.

## Khóa và phân tập

| Trường | Ý nghĩa |
|---|---|
| `timestamp` | Thời điểm dự báo t, giờ Việt Nam `+07:00` |
| `split` | `train` / `val` / `test`: mẫu hợp lệ. `none`: 47 giờ khởi động, 24 giờ purge cuối train và cuối val, 24 giờ cuối không có nhãn — giữ lại chỉ để cửa sổ LSTM nhìn lùi |

## Đặc trưng theo giờ (LSTM/GRU và LR) — 13 cột

| Trường | Đơn vị | Chuẩn hóa | Định nghĩa |
|---|---|---|---|
| `T2M` | °C | z | Nhiệt độ tại t |
| `RH2M` | % | z | Độ ẩm tương đối tại t |
| `DEWPOINT` | °C | z | Điểm sương (Magnus, a = 17,625, b = 243,04) từ T2M và RH2M |
| `PS` | kPa | z | Áp suất bề mặt tại t |
| `WS2M` | m/s | z | Tốc độ gió tại t |
| `WIND_U` | m/s | z | −WS·sin(WD): thành phần gió hướng Đông (> 0 = đi về phía Đông) |
| `WIND_V` | m/s | z | −WS·cos(WD): thành phần gió hướng Bắc (> 0 = đi về phía Bắc) |
| `PRECTOTCORR_log1p` | log(mm/giờ) | z | log(1 + lượng mưa tại t) |
| `ALLSKY_SFC_SW_DWN` | Wh/m² | z | Bức xạ sóng ngắn tại t |
| `hour_sin`, `hour_cos` | — | không | sin/cos(2π·giờ/24), giờ GMT+7 |
| `doy_sin`, `doy_cos` | — | không | sin/cos(2π·(ngày-trong-năm − 1 + giờ/24)/365,25) |

## Đặc trưng lịch sử (chỉ cần cho LR) — 13 cột

| Trường | Đơn vị | Chuẩn hóa | Định nghĩa |
|---|---|---|---|
| `T2M_lag_{1,2,3,6,12,24}h` | °C | z | T2M(t − k giờ) |
| `T2M_roll_mean_24h` | °C | z | Trung bình T2M từ t−23 đến t |
| `T2M_roll_min_24h`, `T2M_roll_max_24h` | °C | z | Thấp nhất / cao nhất T2M từ t−23 đến t |
| `PS_diff_3h`, `PS_diff_24h` | kPa | z | PS(t) − PS(t−3h), PS(t) − PS(t−24h) |
| `PRECTOTCORR_sum_24h_log1p` | log(mm) | z | log(1 + tổng mưa từ t−23 đến t) |
| `ALLSKY_sum_24h` | Wh/m² | z | Tổng bức xạ từ t−23 đến t |

## Nhãn — 4 cột (°C, không chuẩn hóa)

| Trường | Định nghĩa |
|---|---|
| `T2M_t+1h` | T2M tại t + 1 giờ |
| `T2M_t+6h` | T2M tại t + 6 giờ |
| `T2M_t+12h` | T2M tại t + 12 giờ |
| `T2M_t+24h` | T2M tại t + 24 giờ |

## Quy tắc sử dụng

- Chỉ dùng dòng có `split` ∈ {train, val, test}. Không bao giờ đưa `split`, `timestamp` hay cột nhãn vào X.
- Không chia ngẫu nhiên; không fit lại scaler trên val/test.
- Dùng `src/preprocessing/sequences.py` để lấy X/y thay vì tự cắt, tránh lệch cửa sổ.
- `scaler.json → __target__` chứa mean/std của T2M trên train để chuẩn hóa/đảo chuẩn hóa nhãn cho LSTM/GRU.
