# Technical Documentation: Vietnam Weather & Typhoon Forecasting System

## 1. System Architecture & Pipeline
Hệ thống được thiết kế theo kiến trúc **End-to-End Machine Learning Pipeline**, chia thành 4 tầng chính:
1. **Data Ingestion Layer:** Tự động trích xuất dữ liệu thô từ NASA POWER API (dữ liệu khí tượng điểm) và IBTrACS (quỹ đạo bão).
2. **Preprocessing & Feature Engineering Layer:** Làm sạch dữ liệu, xử lý giá trị khuyết thiếu, tạo biến thời gian, biến trễ (lag features) và nhãn mục tiêu (targets).
3. **Modeling Layer:** Sử dụng các mô hình Học máy tập hợp (Ensemble Learning) dựa trên **LightGBM** cho cả bài toán hồi quy (Regression) và phân loại (Classification).
4. **Inference & Alert Layer:** Tổng hợp kết quả dự báo thời tiết hằng ngày và phát cảnh báo thời tiết cực đoan/bão.

---

## 2. Data Specifications & Target Variables
### Tổ chức mã nguồn
- `src/data_audit.py`: ghi nhật ký từng lần chạy cho mọi bước tác động dữ liệu; lưu tại `outputs/logs/data/`. Thu thập và làm sạch đã tích hợp; bước tạo đặc trưng đã tích hợp. Quy tắc và cách đọc: [Nhật ký xử lý dữ liệu](data_logging.md).
- `src/data_collection/`: gọi API/tải dữ liệu nguồn và lưu vào `data/raw/`; `nasa_power.py` phụ trách khí tượng Hà Nội, `ibtracs.py` phụ trách dữ liệu bão.
- `src/preprocessing/cleaning.py`: đọc dữ liệu thô, xử lý giá trị lỗi/thiếu, trùng lặp và xuất thời gian GMT+7 vào `data/cleaned/`; không ghi đè dữ liệu thô.
- `src/preprocessing/features.py`: tạo đặc trưng thời gian, lag, rolling và nhãn tương lai từ dữ liệu đã làm sạch; lưu tập dữ liệu phục vụ mô hình vào `data/processed/`.
- `src/training/`: huấn luyện và đánh giá các mô hình nhiệt độ, mưa và bão; lưu mô hình vào `models/`, kết quả đánh giá vào `outputs/`.
- `src/main.py`: sẽ triển khai ở Sprint 5 để điều phối pipeline. Khi có điểm vào CLI, chạy module từ thư mục gốc bằng `python -m src.<package>.<module>`.

Luồng chuẩn là `data/raw/ → data/cleaned/ → data/processed/`. Dữ liệu gốc chỉ được tạo mới, không chỉnh sửa; chạy lại dùng cache đã có, `--refresh` tạo snapshot mới. Dữ liệu sạch phục vụ EDA; dữ liệu processed có đặc trưng/nhãn và các tập theo thời gian cho mô hình. Mỗi tầng giữ `record_id` để nối về quan trắc, kèm metadata/hash nguồn. Tầng processed sẽ ghi thêm cấu hình đặc trưng, horizon dự báo và mốc chia tập khi triển khai. Việc bảo vệ raw được thực thi trong pipeline, không thay đổi quyền hệ thống tệp.

`src/data_collection/nasa_power.py` đã triển khai thu thập dữ liệu Hà Nội: chia yêu cầu theo tháng, dùng UTC, thử lại lỗi mạng/HTTP tạm thời, lưu JSON gốc và tiếp tục từ cache hợp lệ. CSV tổng hợp được xuất cùng metadata chứa đơn vị từ API, URL nguồn, số dòng, giờ thiếu, bản ghi trùng và giá trị thiếu.

`src/preprocessing/cleaning.py` đã triển khai làm sạch, định danh ổn định và truy vết dữ liệu (xem [từ điển dữ liệu](data_dictionary.md)). Nội suy tuyến tính trong khoảng thiếu, bfill đầu chuỗi và ffill cuối chuỗi; riêng hướng gió nội suy góc ngắn nhất để không biến 350° → 10° thành 180°. Giữ các cực trị hợp lệ; chỉ đánh dấu giá trị ngoài miền vật lý, không tự loại outlier theo phân vị vì có thể là tín hiệu thời tiết cực đoan. Ngưỡng 10.000 dòng dựa trên số giờ quan trắc duy nhất trước bổ sung giờ thiếu. Khi triển khai đánh giá mô hình, phải xử lý thiếu theo thời điểm dự báo, không dùng tương lai hay nội suy xuyên ranh giới tập dữ liệu; không dùng giá trị điền làm nhãn kiểm thử. `src/preprocessing/features.py` đã tạo 21 đặc trưng và 3 nhãn dự báo trước 1 giờ, loại mẫu có cửa sổ đầu vào hoặc nhãn được điền. Module huấn luyện hiện vẫn là khung.


### A. NASA POWER LARC Data (Hourly)
- **Phạm vi giai đoạn đầu:** chỉ triển khai dự báo cho Hà Nội; Đà Nẵng và TP.HCM là phần mở rộng. Thu thập theo giờ cho năm 2023–2024, lưu dữ liệu thô UTC, chuyển timestamp dữ liệu sạch sang GMT+7 (`Asia/Ho_Chi_Minh`) và tạo đặc trưng theo giờ địa phương. Tập dữ liệu sau xử lý và tạo nhãn phải có ít nhất 10.000 dòng hợp lệ.
- **Tọa độ mẫu:** Hà Nội (`lat: 21.0285, lon: 105.8542`), Đà Nẵng, TP.HCM.
- **Features đầu vào:**
  - `T2M`: Nhiệt độ không khí ở độ cao 2m (°C).
  - `PRECTOTCORR`: Lượng mưa đã hiệu chỉnh (mm/h).
  - `ALLSKY_SFC_SW_DWN`: Bức xạ sóng ngắn mặt trời (Wh/m² với dữ liệu giờ, theo metadata API đã tải; không dùng đơn vị của dữ liệu ngày).
  - `PS`: Áp suất bề mặt (kPa).
  - `RH2M`: Độ ẩm tương đối thực tế (%).
  - `WS2M` / `WD2M`: Tốc độ và hướng gió (m/s, độ).
- **Targets cần dự báo:**
  1. **Nhiệt độ tương lai** (`T2M` tại $t+k$).
  2. **Lượng mưa tương lai** (`PRECTOTCORR` tại $t+k$).
  3. **Cờ có mưa hay không** (`rain_flag = 1` nếu `PRECTOTCORR > 0.1`, ngược lại `0`).

### B. IBTrACS Data (Typhoon Tracking)
- **Khu vực:** Biển Đông và Tây Bắc Thái Bình Dương.
- **Features:** Tọa độ (`LAT`, `LON`), áp suất trung tâm (`MSLP`), thời gian, tốc độ gió duy trì.
- **Target:** Dự báo tọa độ tâm bão ở các mốc thời gian tiếp theo (`LAT_t+6h`, `LON_t+6h`).

---

## 3. Evaluation Metrics (Chỉ số đánh giá)
- **Hồi quy (Dự báo nhiệt độ, lượng mưa):** MAE (Mean Absolute Error) và RMSE (Root Mean Squared Error).
- **Phân loại (Dự báo có mưa, cảnh báo bão):** F1-Score, Precision, Recall và ROC-AUC (đặc biệt chú ý xử lý mất cân bằng dữ liệu mưa/bão).
