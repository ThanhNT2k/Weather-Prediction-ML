# 🇻🇳 Vietnam Weather & Typhoon Forecasting System

> Hệ thống học máy phục vụ dự báo thời tiết và nghiên cứu cảnh báo bão tại Việt Nam, sử dụng dữ liệu khí tượng NASA POWER và lịch sử quỹ đạo bão IBTrACS. Giai đoạn hiện tại tập trung vào Hà Nội.

**Repository không chứa dữ liệu:** `data/`, `models/` và `outputs/logs/` được bỏ qua trong `.gitignore`. Sau khi clone, các file CSV/JSON và log nêu dưới đây chưa có trên máy của bạn. Dùng hướng dẫn tái tạo ở mục 4 để tải dữ liệu từ nguồn chính thức và chạy pipeline; không cần xin bản dữ liệu riêng từ tác giả.

---

## 🚀 1. Tổng quan dự án (Project Overview)
Dự án này giải quyết các bài toán dự báo khí tượng từ cơ bản đến nâng cao bao gồm:
1. **Dự báo nhiệt độ** (`T2M`) liên tục theo giờ/ngày.
2. **Dự báo lượng mưa** (`PRECTOTCORR`) và xác định khả năng có mưa hay không (`rain_flag`).
3. **Dự đoán quỹ đạo bão** và phát cảnh báo thời tiết cực đoan (kết hợp biến động áp suất `PS` và dữ liệu bão).

Mô hình cốt lõi sử dụng các thuật toán Học máy tập hợp tối ưu cho dữ liệu dạng bảng (**LightGBM / XGBoost**).

---

## 📊 2. Nguồn dữ liệu (Data Sources)
### Phạm vi triển khai giai đoạn đầu: Hà Nội
- Điểm lấy dữ liệu đại diện: `latitude=21.0285`, `longitude=105.8542`.
- Triển khai trước dự báo nhiệt độ, lượng mưa và khả năng có mưa cho Hà Nội; Đà Nẵng và TP.HCM thuộc giai đoạn mở rộng.
- Thu thập dữ liệu NASA POWER theo giờ từ `2001-01-01` đến hết `2025-12-31`: dự kiến **219,144 dòng** trước xử lý nếu đủ mọi giờ.
- Mỗi dòng tương ứng một giờ tại điểm đại diện Hà Nội, không phải quan trắc cho toàn bộ thành phố. Dữ liệu thô lưu UTC; dữ liệu sạch chuyển sang giờ Việt Nam GMT+7 (`Asia/Ho_Chi_Minh`) ngay trong bước làm sạch.
- Yêu cầu môn Khoa học dữ liệu: còn ít nhất **10.000 dòng hợp lệ sau làm sạch và tạo đặc trưng/nhãn**; kiểm tra thiếu giờ và trùng `city + timestamp`.
- Tính năng bão vẫn theo Sprint 4: học quỹ đạo từ IBTrACS khu vực Biển Đông/Tây Bắc Thái Bình Dương và đánh giá ảnh hưởng tới Hà Nội; dữ liệu NASA tại Hà Nội không đủ để tự dự báo quỹ đạo bão.

### 2.1. NASA POWER — nguồn dữ liệu đã triển khai

- Nhà cung cấp: **NASA Langley Research Center**, dự án **POWER (Prediction Of Worldwide Energy Resources)**.
- Trang nguồn: [NASA POWER](https://power.larc.nasa.gov/).
- Tài liệu truy cập: [Hourly API](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/).
- Endpoint: `https://power.larc.nasa.gov/api/temporal/hourly/point` (HTTP GET).
- Script sử dụng: [src/data_collection/nasa_power.py](src/data_collection/nasa_power.py).
- Script gọi API công khai trực tiếp, không cấu hình tài khoản hoặc API key; cần kết nối Internet khi tải lần đầu.
- Đây là dữ liệu khí tượng/bức xạ dạng lưới được cung cấp cho điểm tọa độ yêu cầu, không phải dữ liệu do project tự đo tại trạm Hà Nội.

| Cấu hình | Giá trị trong project |
|---|---|
| Điểm đại diện | Hà Nội: `latitude=21.0285`, `longitude=105.8542` |
| Tần suất | `hourly`, một dòng mỗi giờ |
| Khoảng thời gian nguồn | `2001-01-01 00:00 UTC` đến `2025-12-31 23:00 UTC`, bao gồm hai đầu |
| Múi giờ yêu cầu | `time-standard=UTC`; không dùng LST mặc định của API |
| Nhóm tham số | `community=RE` |
| Định dạng tải | `format=JSON`; lưu phản hồi từng tháng rồi tổng hợp CSV |
| Chia yêu cầu | 24 yêu cầu theo tháng cho cấu hình hai năm mặc định |
| Số bản ghi dự kiến | 17.544 = (365 + 366) × 24 |

Các biến tải trực tiếp từ NASA (đơn vị theo metadata của phản hồi giờ đã kiểm chứng):

| Mã API | Ý nghĩa | Đơn vị |
|---|---|---|
| `T2M` | Nhiệt độ không khí ở độ cao 2 m | °C |
| `PRECTOTCORR` | Lượng mưa đã hiệu chỉnh theo giờ | mm/giờ |
| `RH2M` | Độ ẩm tương đối ở độ cao 2 m | % |
| `PS` | Áp suất bề mặt | kPa |
| `WS2M` | Tốc độ gió ở độ cao 2 m | m/s |
| `WD2M` | Hướng gió ở độ cao 2 m | độ |
| `ALLSKY_SFC_SW_DWN` | Bức xạ sóng ngắn mặt trời đi xuống bề mặt | Wh/m² |

Ví dụ [yêu cầu API cho ngày 01/01/2023](https://power.larc.nasa.gov/api/temporal/hourly/point?parameters=T2M%2CPRECTOTCORR%2CRH2M%2CPS%2CWS2M%2CWD2M%2CALLSKY_SFC_SW_DWN&community=RE&latitude=21.0285&longitude=105.8542&start=20230101&end=20230101&format=JSON&time-standard=UTC). Đây là mẫu xem cấu trúc phản hồi; dùng script để tải đủ hai năm.

`record_id`, đặc trưng lag/rolling và các nhãn dự báo được tạo trong project, không phải trường tải trực tiếp từ NASA. `rain_flag` bằng 1 khi lượng mưa tại giờ tương lai lớn hơn 0,1 mm/giờ.

### 2.2. IBTrACS — nguồn dự kiến cho tính năng bão

- Nhà cung cấp: **NOAA National Centers for Environmental Information (NCEI)**.
- Trang dữ liệu chính thức: [International Best Track Archive for Climate Stewardship](https://www.ncei.noaa.gov/products/international-best-track-archive).
- Dữ liệu cần thu thập: mã cơn bão, thời gian, tọa độ tâm bão, áp suất trung tâm và gió duy trì; phạm vi Biển Đông/Tây Bắc Thái Bình Dương.
- **Chưa triển khai tải IBTrACS**: [src/data_collection/ibtracs.py](src/data_collection/ibtracs.py) hiện là khung. Các lệnh tái tạo bên dưới chỉ tải NASA POWER; bộ 17.519 mẫu hiện tại chưa có nhãn bão.
- Phiên bản IBTrACS, URL file tải cụ thể và ánh xạ cột áp suất/gió sẽ được ghi khi triển khai. `MSLP` trong thiết kế là khái niệm áp suất trung tâm, không mặc định là tên cột trong mọi bản IBTrACS.

---

## 📁 3. Cấu trúc thư mục (Folder Structure)
```text
weather_vietnam_project/
│
├── data/                    # Thứa chứa dữ liệu (được tự động tạo hoặc tải)
│   ├── raw/                 # Dữ liệu gốc, chỉ tạo mới; không sửa/ghi đè
│   ├── cleaned/             # Dữ liệu sạch, định danh ổn định, giờ GMT+7
│   ├── processed/           # Features, nhãn dự báo và tập train/validation/test
│   └── external/            # Dữ liệu phụ trợ ngoài
│
├── notebooks/               # Jupyter Notebooks khám phá dữ liệu (EDA)
│   ├── 01_explore_nasa.ipynb
│   └── 02_model_training.ipynb
│
├── src/                     # Mã nguồn chính của dự án (Python scripts)
│   ├── __init__.py
│   ├── data_collection/     # Thu thập dữ liệu → data/raw/
│   │   ├── __init__.py
│   │   ├── nasa_power.py    # Dữ liệu khí tượng theo giờ cho Hà Nội
│   │   └── ibtracs.py       # Dữ liệu quỹ đạo bão
│   ├── preprocessing/      # raw → cleaned → processed
│   │   ├── __init__.py
│   │   ├── cleaning.py      # Giá trị thiếu/lỗi, trùng lặp, chuẩn hóa thời gian
│   │   └── features.py      # Biến thời gian, lag, rolling và nhãn tương lai
│   └── training/           # Huấn luyện và đánh giá → models/, outputs/
│       ├── __init__.py
│       ├── train_temperature.py
│       ├── train_rain.py
│       └── train_storm.py
│
├── models/                  # Lưu trữ các file model đã train (.pkl, .lgb)
├── outputs/                 # Lưu biểu đồ, logs, kết quả dự báo
│
├── docs/                    # Tài liệu kỹ thuật và kế hoạch Sprint
│   ├── technicals_docs.md
│   └── sprints/             # Sprint 1 đến Sprint 5
│
├── .gitignore               # Cấu hình bỏ qua data/, models/, cache
├── requirements.txt         # Thư viện Python cần thiết
└── README.md                # Tài liệu dự án
```

## 4. Thu thập dữ liệu NASA POWER cho Hà Nội

### Tái tạo dữ liệu sau khi clone từ GitHub

Mở terminal tại thư mục gốc repository (nơi có `README.md` và `src/`). Cần **Python 3.11 trở lên** và Internet cho bước tải NASA. Ba bước xử lý dữ liệu hiện chỉ dùng thư viện chuẩn Python; chưa cần cài `requirements.txt` để tái tạo dữ liệu. Không cần tạo thủ công các thư mục đầu ra.

```powershell
python --version
python -m src.data_collection.nasa_power --start 2001-01-01 --end 2025-12-31
python -m src.preprocessing.cleaning
python -m src.preprocessing.features --horizon 1
```

Chạy lần lượt; chỉ chuyển sang lệnh tiếp theo khi lệnh trước thành công. Chạy lại lệnh thu thập sau khi mạng gián đoạn sẽ dùng các tháng đã lưu hợp lệ. Dữ liệu gốc không bị ghi đè; `--refresh` tải phiên bản mới vào snapshot riêng.

| Bước | File CSV đầu ra | Kết quả đã kiểm chứng với dữ liệu hiện tại |
|---|---|---|
| Tải nguồn | `data/raw/nasa_power/hanoi_hourly_20010101_20251231.csv` | 219,144 dòng, 11 cột, UTC |
| Làm sạch | `data/cleaned/nasa_power/hanoi_hourly_20010101_20251231_clean.csv` | 219,144 dòng, 17 cột, GMT+7 |
| Tạo đặc trưng/nhãn | `data/processed/nasa_power/hanoi_hourly_20010101_20251231_features_1h.csv` | 219,119 dòng, 35 cột; 21 đặc trưng và 3 nhãn |

Mỗi CSV có file `.metadata.json` cùng tên. JSON gốc từng tháng nằm trong `data/raw/nasa_power/responses/`; log từng lần chạy nằm trong `outputs/logs/data/`. Metadata và log lưu URL nguồn, cấu hình, số dòng và thông tin truy vết; các tầng xử lý bổ sung hash nguồn/đầu ra.

Sau đổi múi giờ, dữ liệu sạch bao phủ **01/01/2023 07:00 đến 01/01/2025 06:00 GMT+7**. Tên file vẫn lấy ngày của nguồn UTC. Bộ processed loại 24 dòng đầu thiếu lịch sử và 1 dòng cuối thiếu nhãn tương lai. Nếu NASA điều chỉnh dữ liệu hoặc có giá trị thiếu, số mẫu cuối có thể khác; pipeline yêu cầu tối thiểu 10.000 mẫu hợp lệ. Các con số trên là kết quả kiểm chứng, không bảo đảm hash giống nhau giữa mọi lần tải.

### Tùy chọn thu thập

Chạy từ thư mục gốc project. Lệnh dùng toàn bộ cấu hình mặc định:

```powershell
python -m src.data_collection.nasa_power
```

Mặc định tải 7 biến theo giờ UTC trong năm 2023–2024. Có thể chạy thử phạm vi nhỏ:

```powershell
python -m src.data_collection.nasa_power --start 2023-01-01 --end 2023-01-02
```

- `--start`, `--end`: ngày dạng `YYYY-MM-DD`, bao gồm cả ngày kết thúc.
- `--output-dir`: thư mục đầu ra; mặc định `data/raw/nasa_power/` tính từ gốc project.
- `--timeout`: thời gian chờ mỗi yêu cầu, mặc định 90 giây; `--retries`: số lần thử lại, mặc định 3.
- `--refresh`: tải vào snapshot mới trong `snapshots/<mã-lần-tải>/`, không ghi đè dữ liệu gốc đã có. Mặc định dùng lại JSON hợp lệ để tiếp tục sau khi gián đoạn.

Đầu ra mặc định:

```text
data/raw/nasa_power/
├── responses/                                 # Phản hồi JSON gốc theo tháng
├── hanoi_hourly_20230101_20241231.csv           # Bảng dữ liệu theo giờ
└── hanoi_hourly_20230101_20241231.metadata.json # Đơn vị, nguồn, thống kê chất lượng
```

CSV gồm `timestamp`, `city`, `latitude`, `longitude` và 7 biến khí tượng. Giá trị thiếu/lỗi từ NASA được giữ nguyên cho Sprint 2; metadata thống kê riêng số giá trị thiếu cho từng biến. Script kiểm tra đủ giờ, đủ biến, UTC, tọa độ và không trùng bản ghi trước khi xuất CSV. Đạt 10.000 dòng thô chưa đồng nghĩa đạt yêu cầu sau làm sạch và tạo nhãn.

Nếu Python MSYS2 báo `CERTIFICATE_VERIFY_FAILED` do thiếu CA mặc định, xác nhận tệp `C:/msys64/usr/ssl/cert.pem` tồn tại rồi chạy trong PowerShell:

```powershell
$env:SSL_CERT_FILE = 'C:/msys64/usr/ssl/cert.pem'
python -m src.data_collection.nasa_power
```

Không tắt xác minh TLS. Kiểm thử logic thu thập không cần mạng:

```powershell
python -m unittest discover -s tests -v
```

Tham khảo: [NASA POWER Hourly API](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/).

## 5. Làm sạch và định danh dữ liệu

Tài liệu trường dữ liệu: [dữ liệu sạch](docs/data_dictionary.md), [toàn bộ 35 trường dữ liệu mô hình](docs/processed_data_dictionary.md), [schema JSON](docs/data_schema.json).

Mỗi lần thu thập hoặc làm sạch tự tạo log riêng tại `outputs/logs/data/`, ghi cấu hình, nguồn, hash, các bước xử lý, thống kê ảnh hưởng và kết quả/lỗi. Metadata sạch chứa đường dẫn log. Có thể đổi vị trí bằng `--log-dir`; xem [hướng dẫn đọc log](docs/data_logging.md). Khi bàn giao dữ liệu cần gửi kèm metadata và log, vì các file phát sinh này không được lưu vào Git.

Luồng dữ liệu: **`raw → cleaned → processed`**. `cleaned` phục vụ EDA và làm đầu vào tạo đặc trưng; `processed` dành cho dữ liệu sẵn sàng huấn luyện (lag, rolling, nhãn tương lai, phân chia theo thời gian). `processed` hiện có bộ đặc trưng và nhãn dự báo trước 1 giờ; việc chia train/validation/test sẽ thực hiện ở bước huấn luyện. `external` chỉ dành cho dữ liệu phụ trợ như ranh giới địa lý; NASA POWER và IBTrACS vẫn thuộc `raw`.

Các lệnh thu thập của project không sửa file đã tồn tại trong `raw`: dữ liệu giống nhau được dùng lại, nội dung khác bị từ chối. Tải phiên bản mới bằng `--refresh`; sau đó truyền đường dẫn CSV snapshot mới cho lệnh làm sạch qua `--input`. Đây là bảo vệ ở mức pipeline, không phải khóa quyền ghi của hệ điều hành.

```powershell
python -m src.preprocessing.cleaning
```

Mặc định đọc CSV Hà Nội 2023–2024, yêu cầu ít nhất 10.000 bản ghi quan trắc duy nhất và lưu riêng vào `data/cleaned/nasa_power/hanoi_hourly_20230101_20241231_clean.csv`. Có thể đổi đường dẫn bằng `--input` và `--output-dir`; `--min-rows` dành cho chạy thử trên mẫu nhỏ.

Pipeline chuẩn hóa thời điểm và xuất `timestamp` theo GMT+7 (ISO 8601 có hậu tố `+07:00`), sắp xếp theo giờ, loại bản ghi trùng giống nhau và báo lỗi nếu trùng giờ nhưng khác giá trị. Giá trị thiếu, `-999`, số không hữu hạn hoặc ngoài miền vật lý được nội suy tuyến tính, sau đó điền biên bằng giá trị hợp lệ gần nhất. Hướng gió nội suy theo góc ngắn nhất qua 0°. Nếu cả cột không có quan trắc hợp lệ, pipeline dừng thay vì tự tạo dữ liệu.

CSV có `station_id`, `record_id` ổn định và các cột truy vết thao tác làm sạch. File `.metadata.json` đi kèm chứa `dataset_id` (SHA-256 của CSV sạch), hash nguồn và báo cáo chất lượng. Xem [từ điển dữ liệu](docs/data_dictionary.md).

Nội suy dùng quan trắc hai phía nên dữ liệu này phục vụ phân tích hồi cứu. Khi đánh giá dự báo, cần chia dữ liệu thô theo thời gian trước, xử lý thiếu theo dữ liệu sẵn có tại thời điểm dự báo, không nội suy xuyên tập train/test và không dùng nhãn được điền làm giá trị thật. Bộ Hà Nội hiện tại không cần điền giá trị nào.


## 6. Tạo đặc trưng và nhãn dự báo

```powershell
python -m src.preprocessing.cleaning
python -m src.preprocessing.features
```

Mặc định dự báo trước 1 giờ, tạo file `data/processed/nasa_power/hanoi_hourly_20230101_20241231_features_1h.csv` và metadata đi kèm. Kết quả hiện tại: **17.519 dòng, 35 cột**, gồm **21 đặc trưng đầu vào và 3 nhãn**. Mỗi lần chạy có log riêng trong `outputs/logs/data/`.

- `--horizon`: số giờ dự báo trước, mặc định 1. Nhãn lượng mưa là lượng mưa tại giờ t+h, không phải tổng từ t đến t+h.
- `--input`, `--output-dir`, `--log-dir`: thay đường dẫn nguồn, đầu ra và log.
- `--min-rows`: mặc định 10.000; pipeline báo lỗi nếu ít hơn.
- Loại 24 dòng đầu chưa đủ lịch sử, h dòng cuối thiếu nhãn và mẫu có ô được điền trong cửa sổ đầu vào/giờ nhãn. Không dùng nội suy hồi cứu để tạo đầu vào hoặc nhãn kiểm thử.
- Các biến giờ/tháng/thứ/mùa dùng GMT+7; rolling chỉ dùng đến giờ t. `rain_flag = 1` khi lượng mưa ở giờ t+h lớn hơn 0,1 mm/giờ.
- Đọc danh sách `feature_columns` và `target_columns` trong metadata để chọn X/y, tránh đưa nhãn tương lai hoặc định danh vào đầu vào.
- Chưa chia train/validation/test hoặc huấn luyện. Sprint 3 phải chia theo thời gian và loại mẫu có nhãn vượt ranh giới tập tiếp theo.
