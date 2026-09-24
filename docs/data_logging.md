# Nhật ký xử lý dữ liệu

Mọi bước thu thập, làm sạch và tạo đặc trưng phải ghi log riêng cho mỗi lần chạy, kể cả chạy lại không làm thay đổi giá trị. Module dùng chung: `src/data_audit.py`. Thu thập NASA, làm sạch và feature engineering đã tích hợp; mỗi lần chạy có log riêng.

## Vị trí và cách đọc

Log nằm tại `outputs/logs/data/<thời-gian>_<mã-ngẫu-nhiên>_<bước>.log`, định dạng UTF-8 với mô tả tiếng Việt và chi tiết JSON. Thời gian log theo GMT+7. Có thể thay thư mục bằng `--log-dir` khi chạy lệnh thu thập hoặc làm sạch.

Mỗi file có:

1. `STARTED`: mã lần chạy, cấu hình, đường dẫn và hash mã nguồn của bước xử lý.
2. `INPUT` hoặc `SOURCE`: nguồn dữ liệu, hash file, URL NASA và việc dùng cache hay tải mới.
3. `VALIDATED` / `TRANSFORMED`: số dòng trước/sau, dòng trùng bị loại, giờ bổ sung, ô được điền theo từng biến, quy tắc nội suy/điền biên, đổi múi giờ và định danh. Số ô được điền bao gồm giá trị thiếu ban đầu, giá trị lỗi và giờ bổ sung.
4. `WRITE_PLANNED`: file dự kiến ghi, hash đầu ra trước đó và hash mới khi làm sạch. Hai hash giống nhau nghĩa là nội dung CSV không thay đổi.
5. `WRITTEN` / `OUTPUT`: file đã ghi hoặc được dùng lại, kèm hash để kiểm tra đúng phiên bản.
6. `SUCCEEDED` hoặc `FAILED`: kết thúc thành công hoặc loại lỗi và thông báo lỗi. Nếu không có dòng kết thúc, có thể tiến trình đã bị ngắt; không coi là thành công.

Metadata dữ liệu sạch có `audit_run_id` và `audit_log` liên kết tới log của lần tạo gần nhất. Log các lần trước vẫn giữ riêng; mã định danh bản ghi và hash CSV không thay đổi chỉ vì chạy lại. Các cột `imputed_columns` và `source_row_numbers` trong CSV hỗ trợ truy vết tới từng bản ghi.

## Quy tắc bảo toàn

- Tạo log trước khi xử lý. Nếu không tạo được log, dừng thao tác.
- Không ghi đè log cũ; lỗi giữa chừng vẫn để lại các bước đã thực hiện. File ghi thành công trước lỗi có thể vẫn tồn tại, nên đọc các sự kiện trước `FAILED`.
- Không đặt log trong `data/raw/` và không sửa dữ liệu gốc để thêm thông tin log.
- Các thao tác thủ công di chuyển/chỉnh sửa dữ liệu phải được ghi lại riêng bằng `DataAudit`, với lý do, đường dẫn và hash trước/sau. Cơ chế này không tự theo dõi chỉnh sửa bằng công cụ bên ngoài pipeline.
- Log bắt đầu từ khi tính năng này được triển khai; không dựng lại lịch sử chi tiết cho những lần chạy trước đó.
- `outputs/logs/` được bỏ qua bởi Git. Khi bàn giao dữ liệu, gửi kèm CSV, metadata và log liên quan; không chỉ gửi mã nguồn.

## Tích hợp bước xử lý mới

```python
from src.data_audit import DataAudit, file_info

with DataAudit("features", {"horizon_hours": 1}, __file__) as audit:
    audit.event("INPUT", "Đọc dữ liệu sạch", **file_info(input_path))
    # Tạo đặc trưng/nhãn; ghi số dòng bị loại do lag hoặc thiếu nhãn.
    # Ghi WRITE_PLANNED trước khi xuất và WRITTEN sau khi xuất thành công.
```

Chỉ ghi hành động đã thực hiện; phân biệt kế hoạch ghi với kết quả đã ghi. Dùng thống kê thực tế để mô tả dữ liệu bị tác động.
