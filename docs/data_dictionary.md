# Từ điển dữ liệu sạch NASA POWER — Hà Nội

Các trường đặc trưng và nhãn ở tầng processed được định nghĩa đầy đủ trong [từ điển dữ liệu mô hình](processed_data_dictionary.md) và [schema JSON](data_schema.json). `rain_flag` ở processed là nhãn tại giờ tương lai, không phải cờ mưa ở giờ đầu vào.

Mỗi dòng là một giờ Việt Nam GMT+7 tại điểm đại diện Hà Nội (`21.0285`, `105.8542`). Khóa nghiệp vụ là `station_id + timestamp`. Dữ liệu sạch lưu tại `data/cleaned/nasa_power/`, dữ liệu thô được giữ nguyên.

## Định danh và truy vết

| Trường | Ý nghĩa |
|---|---|
| `record_id` | UUID v5 từ nguồn NASA POWER, tần suất hourly, station_id và timestamp UTC chuẩn hóa. Không đổi khi sắp xếp lại hoặc sửa giá trị khí tượng. |
| `station_id` | `NASA_POWER_HANOI_21.0285_105.8542`; định danh điểm lấy dữ liệu, không phải mã trạm quan trắc vật lý. |
| `timestamp` | Giờ Việt Nam GMT+7, dạng `2023-01-01T07:00:00+07:00`. |
| `city` | `Hanoi`. |
| `latitude`, `longitude` | Tọa độ điểm yêu cầu dữ liệu, đơn vị độ. |
| `is_imputed` | 1 nếu có ít nhất một biến được điền; ngược lại 0. |
| `imputed_columns` | Tên các biến được điền, ngăn bằng `\|`; `none` nếu không có. |
| `is_inserted_hour` | 1 nếu bổ sung giờ thiếu vào trục thời gian; ngược lại 0. |
| `source_row_numbers` | Số thứ tự bản ghi CSV nguồn, bắt đầu từ 1, không tính header và dòng trắng. Khi gộp trùng, liệt kê các số bằng `\|`; giờ bổ sung dùng `none`. |

`record_id` là định danh, không phải feature đưa vào mô hình. Không dùng các cột truy vết làm đặc trưng mặc định.

Thời gian được chuyển múi giờ thật sự: `2023-01-01T00:00:00Z` thành `2023-01-01T07:00:00+07:00`. Cùng thời điểm vẫn có cùng `record_id` do mã định danh luôn chuẩn hóa về UTC trước khi tính. Dữ liệu thô giữ UTC để truy vết NASA và ghép nguồn khác.

Phạm vi dữ liệu sạch hiện tại là **01/01/2023 07:00 đến 01/01/2025 06:00 GMT+7**, đủ 17.544 giờ. Tên file vẫn dùng ngày nguồn UTC `20230101_20241231`; metadata ghi rõ `filename_date_basis`, `time_standard` và `timezone`. Đây là chuyển múi giờ của các quan trắc hiện có, không phải tải lại theo hai năm lịch địa phương.

## Biến khí tượng

| Trường | Đơn vị | Kiểm tra cơ bản |
|---|---|---|
| `T2M` | °C | Không dưới -273,15 °C. |
| `PRECTOTCORR` | mm/giờ | Không âm. |
| `RH2M` | % | Từ 0 đến 100. |
| `PS` | kPa | Lớn hơn 0. |
| `WS2M` | m/s | Không âm. |
| `WD2M` | độ | Đầu vào 0–360; chuẩn hóa 360 thành 0. |
| `ALLSKY_SFC_SW_DWN` | Wh/m² | Không âm. |

Chuỗi rỗng, số không đọc được, NaN/Infinity, `-999` và fill value trong metadata nguồn được coi là thiếu. Nội suy tuyến tính cho các biến thông thường; hướng gió nội suy theo cung ngắn nhất. Điền biên bằng giá trị hợp lệ gần nhất; báo lỗi nếu cả cột thiếu. Các giới hạn trên chỉ bắt lỗi vật lý cơ bản, không xác nhận toàn bộ độ chính xác khí tượng.

## Metadata của tập dữ liệu

- `dataset_id`: `sha256:<hash>` của nội dung CSV sạch; thay đổi khi nội dung file thay đổi.
- `source_file`, `source_sha256`, `source_metadata_sha256`: truy vết CSV và metadata nguồn.
- `cleaning_version`: phiên bản quy tắc làm sạch.
- Báo cáo số dòng đầu vào/đầu ra, dòng trùng đã loại, giờ bổ sung, ô được điền theo từng biến và ngưỡng số dòng quan trắc.
- `parameters`: metadata đơn vị từ nguồn NASA khi có file metadata đi kèm.

Dữ liệu sau điền là dữ liệu hồi cứu. Để đánh giá dự báo, chia theo thời gian trước và chỉ dùng thông tin sẵn có tại thời điểm dự báo; không dùng các ô được điền làm nhãn đánh giá. Bộ 2023–2024 hiện không có ô cần điền.
