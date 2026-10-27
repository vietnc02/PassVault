# PassVault

Trình quản lý mật khẩu chạy trên máy, dữ liệu mã hóa và không gửi đi đâu.

## Tải về (không cần Python)

Vào [Releases](../../releases), tải `PassVault-x.y.z-windows.zip`, giải nén rồi chạy `install.bat`.
Hướng dẫn chi tiết nằm trong file `HUONG-DAN.txt` trong file zip.

Tự build bản đóng gói: `powershell -ExecutionPolicy Bypass -File packaging\build.ps1`

## Cài đặt từ mã nguồn (Windows, Python 3.10+)

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Chạy

Nhấp đúp `PassVault.bat`, hoặc tạo shortcut có icon ra Desktop:

```
powershell -ExecutionPolicy Bypass -File tools\create_shortcut.ps1
```

Lần đầu chạy, app hỏi tạo **mật khẩu chính**. Không có cách khôi phục nếu quên.

## Dữ liệu

- Kho lưu tại `%APPDATA%\PassVault\vault.pvault`. Đổi chỗ lưu bằng biến môi trường `PASSVAULT_PATH`.
- Khóa được tạo từ mật khẩu chính bằng Argon2id. Dữ liệu được mã hóa bằng AES-256-GCM.
- Nên sao lưu file `vault.pvault` (ra USB, Drive...). File đã được mã hóa nên sao lưu an toàn.

## Tính năng

- Thêm / sửa / xóa / tìm tài khoản, tạo mật khẩu ngẫu nhiên
- Copy tài khoản (Ctrl+B) hoặc mật khẩu (Ctrl+C). Clipboard tự xóa sau 15 giây.
- Mở website của mục đang chọn
- Tự khóa sau 5 phút không dùng
- Đổi mật khẩu chính

## Tự điền trên Chrome / Edge

1. Chạy `install_autofill.bat` (chỉ cần làm một lần; gỡ bằng `install_autofill.bat --uninstall`).
2. Mở `chrome://extensions`, bật **Developer mode**, bấm **Load unpacked** và chọn thư mục `extension`.
3. Trong PassVault, điền ô **Website / App** là tên miền, ví dụ `lms.vnu.edu.vn`.
4. Mở trang đăng nhập:
   - Nếu trang chỉ có **1 tài khoản** khớp (và là HTTPS), PassVault **tự điền ngay**.
   - Nếu có nhiều tài khoản, biểu tượng hiện số lượng; bấm biểu tượng hoặc **Ctrl+Shift+L** để chọn.
   - Dấu **!** trên biểu tượng nghĩa là app chưa chạy hoặc đang khóa.
   - Tắt tự điền khi mở trang bằng ô ở cuối popup.

Extension chỉ nhận mật khẩu của mục có tên miền khớp với trang đang mở, và chỉ khi app đang mở khóa.
Khi tự điền, extension không ghi đè ô bạn đã gõ và không điền vào ô bị ẩn.
App không tự bấm nút đăng nhập; bạn tự bấm.

## Phát triển

```
.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

Cài lại môi trường: `python -m venv .venv` rồi chạy `.venv\Scripts\pip install -r requirements.txt`.
