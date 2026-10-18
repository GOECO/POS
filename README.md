# GOECO POS AI

MVP bán hàng tại quầy cho GOECO. Repository này đang được xây dựng trên nhánh tính năng, chưa được công bố là sẵn sàng production.

## Có trong MVP
- Giao diện thu ngân chạy trên web, lọc sản phẩm theo SKU/tên, giỏ hàng, nhập sản phẩm.
- FastAPI: sản phẩm, kiểm tra tồn kho và checkout giao dịch có idempotency key.
- Giá trị tiền dưới dạng số nguyên VND, giá bán được tính tại server; không tin giá từ trình duyệt.
- Thanh toán tiền mặt được **ghi nhận bởi thu ngân**; chuyển khoản mới tạo yêu cầu chờ đối soát, không tự báo đã trả.
- API key bắt buộc cho API nghiệp vụ, cơ sở dữ liệu SQLite cho MVP một cửa hàng.
- Unit/API tests và GitHub Actions CI.

## Chạy máy cá nhân
Yêu cầu Python 3.11+:

1. Tạo môi trường: python -m venv .venv
2. Cài thư viện: pip install -r backend/requirements.txt
3. Sao chép .env.example thành .env rồi cấu hình khóa POS_API_KEY bí mật. Không commit khóa.
4. Đặt biến POS_API_KEY trong môi trường, ví dụ (PowerShell): $env:POS_API_KEY="YOUR_LONG_RANDOM_SECRET"
5. Chạy: uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
6. Mở http://127.0.0.1:8000; nhập khóa vào giao diện trong phiên truy cập.

Không mở cổng ứng dụng trực tiếp ra Internet ở chế độ MVP. Khi triển khai phải dùng TLS, xác thực theo người dùng/nhân viên, phân quyền, rate limiting và database production.

## Kiểm thử
pip install -r backend/requirements-dev.txt
python -m pytest -q

## Giai đoạn sau (chưa triển khai)
Multi-tenant, RBAC theo chi nhánh, đồng bộ offline, hoàn/đổi hàng, thuế/hóa đơn điện tử, thiết bị in/mã vạch, cổng VNPay/MoMo/ZaloPay, đối soát webhook, AI Sales Agent qua VietCore AI API.

Kiến trúc và giới hạn: docs/ARCHITECTURE.md. Mã nguồn proprietary; chưa cấp quyền tái sử dụng cho bên ngoài.
