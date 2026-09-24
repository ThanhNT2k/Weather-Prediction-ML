# Sprint 4: Typhoon Track Prediction & Integration

## Mục tiêu Sprint
Xử lý dữ liệu quỹ đạo bão từ IBTrACS và tích hợp cảnh báo thời tiết cực đoan vào hệ thống chung.

## Công việc (Tasks)
- [ ] Xử lý dữ liệu IBTrACS, tính toán độ dịch chuyển tọa độ tâm bão qua các mốc thời gian (`delta_lat`, `delta_lon`).
- [ ] Viết script `src/training/train_storm.py` xây dựng mô hình dự đoán vị trí tâm bão tiếp theo.
- [ ] Xây dựng cơ chế tích hợp (Alert Integration): Kết hợp tín hiệu áp suất bề mặt (`PS`) giảm sâu từ NASA POWER với thông tin bão từ IBTrACS để kích hoạt cờ cảnh báo sớm (`storm_alert_flag`).

## Định nghĩa hoàn thành (Definition of Done)
- Hoàn thành script dự báo quỹ đạo bão.
- Hệ thống có khả năng đưa ra cảnh báo kết hợp giữa dữ liệu tại trạm và thông tin thiên tai diện rộng.