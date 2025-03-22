import socket
import struct
import time
import os
import sys

# Cấu hình địa chỉ broadcast và cổng
BCAST_ADDR = '192.168.0.255'  # Địa chỉ broadcast
BCAST_PORT = 1234             # Cổng phát

# Tạo socket UDP
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# Cho phép nhận broadcast packet
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

# Đặt timeout để script không bị treo vô hạn
sock.settimeout(10)  # 10 giây timeout

# In thông tin giao diện mạng
print("\nInterface Information:")
print("----------------------")
host_name = socket.gethostname()
try:
    host_ip = socket.gethostbyname(host_name)
except:
    host_ip = "Unknown"

# Lấy địa chỉ IP thật của các interfaces
print(f"Hostname: {host_name}")
print(f"IP Address: {host_ip}")
print(f"Broadcast address: {BCAST_ADDR}:{BCAST_PORT}")
print("----------------------\n")

# Bind vào tất cả interfaces
try:
    sock.bind(('', BCAST_PORT))
    print(f"Successfully bound to port {BCAST_PORT}")
except socket.error as e:
    print(f"Error binding to port {BCAST_PORT}: {e}")
    exit(1)

# Thử hiển thị thêm thông tin gỡ lỗi
print(f"\nBroadcast Configuration Details:")
print(f"--------------------------------")
print(f"Broadcast Address: {BCAST_ADDR}")
print(f"Port: {BCAST_PORT}")
print(f"Platform: {sys.platform}")
print(f"--------------------------------\n")

print(f"Listening for broadcast data on port {BCAST_PORT}...")
print(f"Ctrl+C to stop")

# Tạo file để lưu dữ liệu nhận được
output_file = f"broadcast_data_{int(time.time())}.ts"
total_bytes = 0
packet_count = 0

try:
    with open(output_file, 'wb') as f:
        start_time = time.time()
        while True:
            try:
                data, addr = sock.recvfrom(65536)  # Tăng kích thước buffer
                packet_count += 1
                total_bytes += len(data)
                
                # Ghi dữ liệu vào file
                f.write(data)
                
                # Hiển thị thông tin
                elapsed = time.time() - start_time
                rate = total_bytes / (1024 * 1024 * elapsed) if elapsed > 0 else 0
                print(f"Received packet #{packet_count}: {len(data)} bytes from {addr} | Total: {total_bytes/1024/1024:.2f} MB | Rate: {rate:.2f} MB/s")
                
                # Flush để đảm bảo dữ liệu được ghi xuống ngay lập tức
                f.flush()
                
                # Nếu đây là gói đầu tiên, thêm thông tin
                if packet_count == 1:
                    print(f"\nFirst packet received from: {addr}")
                    print(f"Connection established successfully!")
                
            except socket.timeout:
                if packet_count == 0:
                    print("No data received in 10 seconds, still waiting...")
                else:
                    print(f"Timeout after receiving {packet_count} packets. Continuing to listen...")
except KeyboardInterrupt:
    print(f"\nReceived {packet_count} packets, total {total_bytes/1024/1024:.2f} MB")
    print(f"Data saved to {os.path.abspath(output_file)}")
except Exception as e:
    print(f"Error: {e}")
finally:
    sock.close()
    print("Socket closed")
