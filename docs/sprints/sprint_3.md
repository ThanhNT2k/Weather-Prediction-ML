# Sprint 3: Weather Prediction Modeling

## Mục tiêu Sprint
Xây dựng và tối ưu hóa các mô hình Machine Learning dự báo Nhiệt độ, Lượng mưa và Khả năng có mưa.

## Công việc (Tasks)
- [ ] Viết script `src/training/train_temperature.py`:
  - Huấn luyện mô hình **LightGBM Regressor** dự báo nhiệt độ `T2M`.
  - Đánh giá mô hình bằng MAE và RMSE trên tập Test.
- [ ] Viết script `src/training/train_rain.py`:
  - Huấn luyện mô hình **LightGBM Regressor** dự báo lượng mưa thực tế (`PRECTOTCORR`).
  - Huấn luyện mô hình **LightGBM Binary Classifier** dự báo `rain_flag`.
  - Đánh giá bằng F1-Score và ROC-AUC.
- [ ] Lưu các file model đã train (`.lgb` hoặc `.pkl`) vào thư mục `models/`.

## Định nghĩa hoàn thành (Definition of Done)
- Các mô hình đạt độ chính xác ổn định trên tập kiểm thử.
- Các file mô hình được đóng gói gọn gàng trong thư mục `models/`.