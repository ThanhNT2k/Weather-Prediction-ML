# Sprint 2: Preprocessing & Feature Engineering

## Mục tiêu Sprint
Làm sạch dữ liệu triệt để và trích xuất các đặc trưng (features) tối ưu cung cấp cho mô hình Machine Learning.

## Công việc (Tasks)
- [x] Ghi log riêng mỗi lần làm sạch: nguồn/hash, cấu hình, quy tắc, số dòng/ô tác động, đầu ra và lỗi; liên kết log trong metadata.
- [x] Viết script `src/preprocessing/cleaning.py`:
  - Lọc và thay thế giá trị lỗi `-999.0` bằng phương pháp nội suy tuyến tính (`linear interpolation`).
  - Xử lý biên bằng `ffill()` và `bfill()`.
- [x] Định danh điểm dữ liệu (`station_id`), bản ghi theo giờ (`record_id`) và phiên bản dữ liệu (`dataset_id`); lưu nguồn và cờ điền giá trị.
- [x] Chuyển `timestamp` dữ liệu sạch sang GMT+7, ISO 8601 có `+07:00`; giữ `record_id` ổn định theo cùng thời điểm UTC.
- [x] Xây dựng Feature Engineering Pipeline trong `src/preprocessing/features.py`:
  - **Temporal Features:** `hour`, `month`, `dayofweek`, `season`.
  - **Lag & Rolling Features:** `T2M_lag_1h`, `T2M_lag_24h`, `PS_diff_3h` (để bắt áp thấp/bão).
  - **Binary Target:** Tạo cột `rain_flag` dựa trên ngưỡng lượng mưa.
- [x] Lưu tập dữ liệu đã làm sạch vào `data/cleaned/nasa_power/`, kèm báo cáo chất lượng.
- [x] Lưu bộ đặc trưng/nhãn vào `data/processed/`, giữ `record_id` và thông tin nguồn từ cleaned.

## Định nghĩa hoàn thành (Definition of Done)
- File dữ liệu sạch không còn giá trị NaN hoặc lỗi.
- Đầy đủ các cột lag features và nhãn mục tiêu, sẵn sàng cho bước huấn luyện mô hình.

## Kết quả bước làm sạch
- File `hanoi_hourly_20230101_20241231_clean.csv`: 17.544 bản ghi quan trắc, 17.544 `record_id` duy nhất; đủ ngưỡng 10.000 dòng ở bước làm sạch.
- Không có giờ thiếu, trùng lặp hoặc ô cần điền trong bộ dữ liệu hiện tại. Các giá trị khí tượng được giữ nguyên.
- Đã kiểm thử nội suy/điền biên, hướng gió qua 0°, giá trị lỗi, định danh ổn định, truy vết, trùng mâu thuẫn và ngưỡng số dòng quan trắc.
- Đã hoàn thành feature engineering và nhãn dự báo trước 1 giờ: 17.519 dòng, 35 cột, 21 đặc trưng và 3 nhãn. Loại 24 dòng đầu thiếu lịch sử và 1 dòng cuối thiếu nhãn; không có mẫu bị loại do nội suy. Đủ ngưỡng 10.000 dòng sau tạo đặc trưng/nhãn.
- Đã đạt Definition of Done của Sprint 2 cho phạm vi Hà Nội: không thiếu giá trị, đủ lag/rolling và nhãn; 24 kiểm thử đạt. Bước tiếp theo là chia tập theo thời gian và huấn luyện trong Sprint 3.
- Từ điển từng trường: `docs/processed_data_dictionary.md`; schema máy đọc được: `docs/data_schema.json`.
- Nội suy tuyến tính và bfill phục vụ dữ liệu hồi cứu. Khi đánh giá dự báo phải ngăn sử dụng quan trắc tương lai, không nội suy xuyên ranh giới train/test và không chấm điểm trên nhãn được điền.
