# Định nghĩa các trường dữ liệu mô hình — Hà Nội

Định nghĩa máy đọc được: [data_schema.json](data_schema.json). Bảng dưới liệt kê đầy đủ 35 cột, gồm 17 cột giữ từ cleaned, 14 đặc trưng mới và 4 cột thời gian/nhãn tương lai. Không cột nào được để thiếu trong CSV processed.

| Trường | Kiểu | Vai trò | Đơn vị | Định nghĩa |
|---|---|---|---|---|
| `record_id` | string | identifier | - | UUID5 của điểm lấy dữ liệu và thời điểm UTC; giữ nguyên từ cleaned. |
| `station_id` | string | identifier | - | Định danh điểm NASA POWER Hà Nội. |
| `timestamp` | string | time | - | Thời điểm dự báo t, ISO 8601 với +07:00. |
| `city` | string | identifier | - | Tên thành phố: Hanoi. |
| `latitude` | float | location | degree | Tọa độ điểm lấy dữ liệu; không đưa vào feature mặc định vì chỉ có một điểm Hà Nội. |
| `longitude` | float | location | degree | Tọa độ điểm lấy dữ liệu; không đưa vào feature mặc định vì chỉ có một điểm Hà Nội. |
| `T2M` | float | feature | °C | Nhiệt độ tại t. |
| `PRECTOTCORR` | float | feature | mm/hour | Lượng mưa theo giờ tại t. |
| `RH2M` | float | feature | % | Độ ẩm tương đối tại t. |
| `PS` | float | feature | kPa | Áp suất bề mặt tại t. |
| `WS2M` | float | feature | m/s | Tốc độ gió 2 m tại t. |
| `WD2M` | float | feature | degree | Hướng gió 2 m tại t, [0,360). |
| `ALLSKY_SFC_SW_DWN` | float | feature | Wh/m² | Bức xạ sóng ngắn tại t. |
| `is_imputed` | int | provenance | - | 1 nếu dòng có ô được điền, ngược lại 0. |
| `imputed_columns` | string | provenance | - | Danh sách biến được điền, phân cách bằng dấu \|; none nếu không có. |
| `is_inserted_hour` | int | provenance | - | 1 nếu giờ được bổ sung, ngược lại 0. |
| `source_row_numbers` | string | provenance | - | Số thứ tự bản ghi nguồn, phân cách bằng dấu \|; không tính dòng trắng/header. |
| `hour` | int | feature | hour | Giờ GMT+7 tại t, 0–23. |
| `month` | int | feature | month | Tháng GMT+7 tại t, 1–12. |
| `dayofweek` | int | feature | - | Thứ theo giờ GMT+7: thứ Hai=0, Chủ nhật=6. |
| `season` | int | feature | - | Quy ước mùa cho Hà Nội: 0=đông (12–2), 1=xuân (3–5), 2=hạ (6–8), 3=thu (9–11); là quy ước lịch. |
| `T2M_lag_1h` | float | feature | °C | T2M(t−1 giờ). |
| `T2M_lag_24h` | float | feature | °C | T2M(t−24 giờ). |
| `PRECTOTCORR_lag_1h` | float | feature | mm/hour | PRECTOTCORR(t−1 giờ). |
| `PRECTOTCORR_lag_24h` | float | feature | mm/hour | PRECTOTCORR(t−24 giờ). |
| `PS_diff_3h` | float | feature | kPa | PS(t) − PS(t−3 giờ); âm khi áp suất giảm. |
| `T2M_rolling_mean_3h` | float | feature | °C | Trung bình T2M từ t−2 đến t, đủ 3 giờ, gồm giờ hiện tại. |
| `T2M_rolling_mean_24h` | float | feature | °C | Trung bình T2M từ t−23 đến t, đủ 24 giờ, gồm giờ hiện tại. |
| `PRECTOTCORR_rolling_sum_24h` | float | feature | mm | Tổng 24 giá trị mưa theo giờ từ t−23 đến t; mỗi khoảng kéo dài 1 giờ. |
| `WD2M_sin` | float | feature | - | sin(WD2M(t) × π/180). |
| `WD2M_cos` | float | feature | - | cos(WD2M(t) × π/180). |
| `target_timestamp` | string | target_time | - | Thời điểm nhãn t+h giờ, GMT+7; h lấy từ metadata horizon_hours, mặc định 1. |
| `target_temperature` | float | target | °C | T2M tại t+h, nhãn hồi quy nhiệt độ. |
| `target_rainfall` | float | target | mm/hour | PRECTOTCORR tại t+h, nhãn hồi quy lượng mưa theo giờ; không phải tổng mưa trong h giờ. |
| `rain_flag` | int | target | - | 1 nếu target_rainfall > 0.1 mm/hour, ngược lại 0. Là nhãn tương lai, không đưa vào X. |

## Quy tắc sử dụng

- Đặc trưng X chỉ gồm các trường có role=feature: 7 biến hiện tại và 14 đặc trưng mới (21 trường). Metadata lưu danh sách chính xác.
- Nhãn y là target_temperature, target_rainfall hoặc rain_flag tùy bài toán. Không đưa nhãn, target_timestamp, mã định danh hoặc thông tin truy vết vào X.
- Chỉ sử dụng dữ liệu tại hoặc trước t để tính X. Loại 24 dòng đầu vì thiếu lịch sử và h dòng cuối vì chưa có nhãn tương lai.
- Loại mẫu nếu bất kỳ giờ nào trong [t−24,t] hoặc giờ nhãn t+h đã được điền/bổ sung, để tránh nội suy dùng tương lai và nhãn không phải quan trắc thật.
- Giả định quan trắc giờ t đã có tại thời điểm phát dự báo. Đây là bộ đánh giá lịch sử; chưa mô phỏng độ trễ công bố thực tế của NASA.
- Chia train/validation/test theo thời gian ở bước huấn luyện; bỏ các mẫu có target_timestamp chạm hoặc vượt thời điểm bắt đầu tập tiếp theo. Không chia ngẫu nhiên. Chưa tạo các tập này trong bước tạo đặc trưng.
- Dữ liệu bão IBTrACS thuộc Sprint 4, chưa có nhãn hoặc đặc trưng bão trong bộ này.
