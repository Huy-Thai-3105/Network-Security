# Hệ thống phát video từ CDN cá nhân qua Multicast

## Tổng quan hệ thống
Hệ thống bao gồm hai thành phần chính: laptop cá nhân làm CDN nguồn và một máy chủ trung gian làm nhiệm vụ chuyển đổi và phát multicast đến các màn hình hiển thị trong mạng nội bộ.

## Kiến trúc hệ thống

### 1. Máy tính cá nhân (CDN nguồn)
- **Lưu trữ nội dung:** Chứa các video gốc
- **Web server:** Nginx hoặc Apache phục vụ nội dung qua HTTP
- **Giao diện quản lý:** Trang web đơn giản để quản lý nội dung
- **Truyền nội dung:** Gửi nội dung đến máy chủ multicast trung gian

### 2. Máy chủ Multicast (trung gian)
- **Cache Server:** Lưu trữ tạm thời nội dung từ CDN nguồn
- **Multicast Converter:** Chuyển đổi stream HTTP thành multicast
- **Quản lý kết nối:** Theo dõi các thiết bị nhận multicast

### 3. Các màn hình hiển thị
- **Client software:** VLC hoặc phần mềm tương tự nhận multicast stream
- **Báo cáo trạng thái:** Gửi thông tin về tình trạng hiển thị
- **Phần cứng:** Các thiết bị có khả năng kết nối mạng và hiển thị video

## Luồng làm việc

1. **Chuẩn bị nội dung trên máy cá nhân (CDN nguồn):**
   - Video được lưu trữ trên máy tính cá nhân
   - Web server phục vụ nội dung qua HTTP/HTTPS

2. **Truyền nội dung đến máy chủ Multicast:**
   - Máy chủ Multicast truy cập và lấy nội dung từ CDN nguồn
   - Nội dung được cache trên máy chủ Multicast để tối ưu hiệu suất

3. **Chuyển đổi và phát Multicast:**
   - Máy chủ Multicast chuyển đổi stream HTTP thành giao thức Multicast
   - Stream Multicast được phát đến địa chỉ multicast trong mạng nội bộ

4. **Nhận và hiển thị:**
   - Các màn hình tham gia nhóm multicast
   - Các màn hình nhận stream và hiển thị video
   - Gửi báo cáo trạng thái về máy chủ Multicast

## Công nghệ triển khai

### CDN nguồn (Máy tính cá nhân)
- **Nginx/Apache:** Web server để phân phối nội dung
- **HTML/JavaScript đơn giản:** Giao diện người dùng quản lý
- **HTTP Live Streaming (HLS) hoặc DASH:** Định dạng streaming tương thích

### Máy chủ Multicast
- **Nginx với module RTMP:** Nhận HTTP stream từ CDN nguồn
- **FFmpeg/VLC:** Chuyển đổi từ HTTP sang Multicast
- **Bash/Python scripts:** Quản lý và giám sát quá trình phát multicast

### Thiết bị hiển thị
- **VLC Media Player:** Phần mềm nhận multicast stream
- **Auto-start scripts:** Tự động kết nối đến stream khi khởi động
- **Báo cáo trạng thái:** Script gửi thông tin về máy chủ

## Cài đặt và cấu hình

### 1. Cài đặt trên CDN nguồn (máy tính cá nhân)