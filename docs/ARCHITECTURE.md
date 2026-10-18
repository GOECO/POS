# Kiến trúc và biên giới an toàn

## Phạm vi MVP 0.1
Một điểm bán, một khóa API, SQLite một tiến trình, web thu ngân và checkout giao dịch. Backend FastAPI tính tiền từ bảng sản phẩm. Tồn kho và đơn hàng được commit atomically bằng BEGIN IMMEDIATE. Idempotency key chống trừ kho hai lần khi gửi lại cùng nội dung.

## Chưa production ready
- Khóa API chung chưa phải phân quyền nhân viên hay tenant isolation; không phát hành công khai.
- Chưa có số hóa đơn, ký số, tích hợp hóa đơn điện tử và xử lý thuế tuân thủ pháp luật.
- Chưa có thanh toán điện tử đã xác minh, webhook signed, hoàn tiền và đối soát.
- SQLite không phù hợp đa cửa hàng đồng thời; chuyển PostgreSQL với transaction/row locking.
- Chưa có audit trail, rate limit, chống brute force, SSO/MFA, backup tự động, metrics.
- Chưa có POS offline queue/dedup, máy in và quét barcode.
- Nếu mạng mất sau khi gửi đơn và trước khi nhận phản hồi, UI hiện yêu cầu kiểm tra lịch sử; UI chưa lưu idempotency key để tự retry.

## Lộ trình
P0: Auth tài khoản + RBAC, tenant/store model, PostgreSQL migrations, logging và audit.
P1: In hóa đơn/mã vạch, đổi trả, quản lý kho theo ledger, báo cáo, thuế/hóa đơn.
P2: Payment gateway adapters chỉ ghi paid khi webhook đã xác minh và đối soát.
P3: AI adapter qua VietCore AI HTTPS API; không chuyển thông tin nhạy cảm khi chưa có consent và cơ chế bảo vệ.
P4: SaaS đa chi nhánh, giới hạn gói, tính phí thuê bao, worker/queue, sync offline.

## Kiến trúc mục tiêu
Web / Android / POS tablet -> POS API -> PostgreSQL & outbox -> worker/payment integration
                                              |
                                              -> VietCore AI API (separate service)

Luôn tách GOECO POS (nghiệp vụ) khỏi VietCore AI (AI technology). Không thêm API key, mật khẩu, token hoặc dữ liệu khách hàng thật vào git.
