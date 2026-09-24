# Sprint 1: Data Acquisition & Exploratory Data Analysis (EDA)

## Mục tiêu Sprint
Hoàn thành việc xây dựng cơ sở dữ liệu thô từ NASA POWER API và IBTrACS, đồng thời thực hiện phân tích khám phá dữ liệu (EDA) để hiểu rõ phân phối dữ liệu tại Việt Nam.

## Công việc (Tasks)
- [x] Viết script `src/data_collection/nasa_power.py` gọi NASA POWER API lấy dữ liệu theo giờ trước cho Hà Nội (`21.0285`, `105.8542`), từ `2023-01-01` đến hết `2024-12-31`. Đà Nẵng và TP.HCM triển khai sau.
- [x] Xử lý lưu trữ dữ liệu NASA POWER thô vào thư mục `data/raw/nasa_power/`; lưu trữ IBTrACS thuộc công việc tiếp theo.
- [ ] Viết `src/data_collection/ibtracs.py` tải và lọc bộ dữ liệu quỹ đạo bão từ IBTrACS cho khu vực Biển Đông.
- [ ] Tạo file Jupyter Notebook `notebooks/01_explore_nasa.ipynb` để trực quan hóa:
  - Phân phối nhiệt độ theo mùa tại Việt Nam.
  - Tỷ lệ giờ có mưa vs không mưa (phát hiện mất cân bằng dữ liệu).
  - Tần suất biến động áp suất (`PS`).

## Định nghĩa hoàn thành (Definition of Done)
- File CSV dữ liệu thô nằm đúng thư mục `data/raw/` với số lượng dòng >= 17.500 dòng/thành phố.
- Giai đoạn đầu nghiệm thu cho Hà Nội: dự kiến 17.544 giờ trong năm 2023–2024; kiểm tra thiếu giờ và trùng `city + timestamp`, lưu thời gian UTC.
- Yêu cầu xuyên suốt cho môn Khoa học dữ liệu: sau Sprint 2, tập dữ liệu dùng cho mô hình phải còn ít nhất 10.000 dòng hợp lệ sau làm sạch và tạo đặc trưng/nhãn.
- Báo cáo EDA trực quan hoàn thiện bằng biểu đồ trong Notebook.

## Kết quả kiểm chứng thu thập NASA POWER
- Đã tải thực tế 24 tháng của năm 2023–2024 vào `data/raw/nasa_power/hanoi_hourly_20230101_20241231.csv`.
- Có 17.544 dòng, 7 biến khí tượng, không thiếu giờ, không trùng bản ghi và không có giá trị thiếu theo fill value của NASA trong lần tải này.
- Lưu JSON gốc từng tháng trong `responses/` và báo cáo đơn vị/nguồn/chất lượng trong file `.metadata.json` đi kèm CSV.
- 6 kiểm thử tự động đạt: biên tháng/năm nhuận, phản hồi không đầy đủ, giá trị thiếu và cache, không xuất dữ liệu lỗi, khoảng ngày không hợp lệ, retry HTTP.
- Sprint 1 chưa hoàn thành: còn IBTrACS và EDA. Chưa nghiệm thu yêu cầu 10.000 dòng sau xử lý của Sprint 2.
