#!/usr/bin/env python3
import subprocess
from flask import Flask, request, jsonify
import sys
import os
import socket

app = Flask(__name__)

# Biến toàn cục lưu FFmpeg process
ffmpeg_process = None

# Thông số mặc định (thay đổi theo nhu cầu)
DEFAULT_CDN_URL = "http://34.120.70.159/152407-802753527_small.mp4"  # URL video từ CDN
DEFAULT_MULTICAST_ADDR = "239.255.0.1"      # Địa chỉ multicast
DEFAULT_PORT = "1234"                          # Cổng phát
DEFAULT_TTL = "2"                             # TTL=2 để có thể đi qua router nội bộ

def configure_firewall():
    """Cấu hình tường lửa để cho phép multicast"""
    print("Configuring firewall for multicast traffic...", file=sys.stderr)
    
    # Kiểm tra quyền root (sudo)
    if os.geteuid() != 0:
        print("Warning: Not running as root, firewall configuration may fail", file=sys.stderr)
    
    try:
        # Mở cổng cho lưu lượng multicast
        if sys.platform == 'darwin':  # macOS
            subprocess.run(["sudo", "-n", "pfctl", "-t", "com.apple.pfctl.skipfw", "-T", "add", "239.0.0.0/8"], 
                          check=False, stderr=subprocess.PIPE)
        elif sys.platform.startswith('linux'):  # Linux
            subprocess.run(["sudo", "-n", "iptables", "-I", "INPUT", "-d", "239.0.0.0/8", "-j", "ACCEPT"], 
                          check=False, stderr=subprocess.PIPE)
            subprocess.run(["sudo", "-n", "iptables", "-I", "OUTPUT", "-d", "239.0.0.0/8", "-j", "ACCEPT"], 
                          check=False, stderr=subprocess.PIPE)
        
        print("Firewall configured for multicast (if you have sudo privileges)", file=sys.stderr)
    except Exception as e:
        print(f"Failed to configure firewall: {e}", file=sys.stderr)
        print("Continuing anyway...", file=sys.stderr)

def start_ffmpeg(cdn_url, multicast_addr, port, ttl):
    global ffmpeg_process
    if ffmpeg_process is not None:
        return False, "Streaming is already running."

    # Kiểm tra xem địa chỉ có phải là broadcast/multicast không
    is_broadcast = multicast_addr.endswith('.255')
    is_multicast = multicast_addr.startswith('239.') or multicast_addr.startswith('224.')
    is_local = multicast_addr.startswith('127.')
    
    # In thông tin địa chỉ cho debug
    print(f"Stream address: {multicast_addr}", file=sys.stderr)
    print(f"Is broadcast: {is_broadcast}", file=sys.stderr)
    print(f"Is multicast: {is_multicast}", file=sys.stderr)
    print(f"Is localhost: {is_local}", file=sys.stderr)
    
    # Lấy địa chỉ IP của máy local
    local_ip = "192.168.0.122"
    print(f"Local IP address: {local_ip}", file=sys.stderr)
    
    # Cấu hình tối ưu đặc biệt để khắc phục vấn đề hình ảnh bị đứng
    command = [
        "ffmpeg",
        "-loglevel", "warning",                  # Giảm log
        "-re",                                   # Đọc với tốc độ thực 
        "-stream_loop", "-1",                    # Loop stream nếu cần thiết để tránh dừng đột ngột
        "-fflags", "+genpts+discardcorrupt+nobuffer+igndts", # Bỏ qua DTS, tạo PTS mới cho mượt
        "-flags", "low_delay",                   # Flag low delay cho streaming
        "-avoid_negative_ts", "make_zero",       # Tránh timestamp âm
        "-analyzeduration", "500000",            # Giảm thời gian phân tích
        "-probesize", "1000000",                 # Giảm probe size phù hợp
        "-i", cdn_url,                           # Input URL
        
        # Video codec settings - cấu hình đặc biệt cho độ mượt cao
        "-c:v", "libx264",                       # Codec H.264
        "-vsync", "cfr",                         # CFR cho video sync ổn định hơn
        "-preset", "ultrafast",                  # Preset siêu nhanh cho độ trễ thấp
        "-tune", "zerolatency",                  # Tune cho độ trễ gần như không có
        "-profile:v", "baseline",                # Profile baseline (đơn giản nhất, ít lỗi nhất)
        "-level", "3.0",                         # Level H.264 tương thích rộng nhưng nhẹ
        
        # Cấu hình bit rate và buffer tốt nhất cho streaming broadcast
        "-b:v", "800k",                          # Bitrate vừa phải 
        "-maxrate", "1000k",                     # Maxrate phù hợp
        "-bufsize", "1000k",                     # Buffer nhỏ để tránh delay
        "-r", "24",                              # Frame rate ổn định 24fps (tiêu chuẩn phim)
        
        # Tùy chọn x264 siêu tối ưu cho streaming
        "-x264opts", "no-cabac:no-scenecut:partitions=none:ref=1:me=dia:subme=0:trellis=0:weightp=0:no-weightb:bframes=0:8x8dct=0", # Options x264 cực nhẹ
        
        # Cấu hình keyframe chặt chẽ để tránh hiện tượng hình ảnh bị đứng
        "-force_key_frames", "expr:gte(t,n_forced*0.5)", # Force keyframe mỗi 0.5 giây rất quan trọng
        "-g", "12",                              # GOP size ngắn (12 frames cho 24fps = 0.5 giây)
        "-keyint_min", "12",                     # Khoảng cách tối thiểu giữa các keyframe
        "-sc_threshold", "0",                    # Tắt scene change detection
        
        # Video filtering
        "-vf", "fps=fps=24",                     # Ổn định framerate
        
        # Audio settings
        "-c:a", "aac",                           # Audio codec AAC
        "-b:a", "96k",                           # Bitrate audio vừa đủ
        "-ar", "44100",                          # Sample rate tiêu chuẩn
        "-ac", "2",                              # 2 kênh stereo
        
        # Cấu hình muxing
        "-max_muxing_queue_size", "9999",
        "-muxdelay", "0",                        # Không delay khi muxing
        "-muxpreload", "0",                      # Preload 0s
        
        # Output format
        "-f", "mpegts",
    ]
    
    # Thêm đối số đầu ra và thông báo cho người dùng cách kết nối
    if is_broadcast:
        # Broadcast với UDP
        command.append(f"udp://{multicast_addr}:{port}?broadcast=1&pkt_size=1316&buffer_size=65536&ttl={ttl}")
        url_for_vlc = f"udp://@{multicast_addr}:{port}"
    else:
        # Unicast với UDP
        command.append(f"udp://{multicast_addr}:{port}?pkt_size=1316&buffer_size=65536")
        url_for_vlc = f"udp://@{multicast_addr}:{port}"
    
    print(f"Executing command: {' '.join(command)}", file=sys.stderr)
    print(f"1. Mở VLC -> Media -> Open Network Stream -> Nhập: {url_for_vlc}", file=sys.stderr)
    print(f"2. Trong VLC -> Media -> Open Network Stream -> Show more options và Caching: 50 ms", file=sys.stderr)
    print(f"3. Hoặc: vlc {url_for_vlc} --network-caching=50 --no-video-title-show", file=sys.stderr)
    print(f"4. Nếu vẫn bị đứng hình, mở VLC -> Tools -> Preferences -> Input & Codecs:", file=sys.stderr)
    print(f"   - Network caching: 50ms", file=sys.stderr) 
    print(f"   - Hardware decoding: Disable", file=sys.stderr)
    print(f"   - Skip frames: Enabled", file=sys.stderr)
    print(f"5. Phải restart VLC sau khi thay đổi cài đặt", file=sys.stderr)
    print(f"--------------------------------\n", file=sys.stderr)
    
    # Cập nhật giá trị mặc định cho CDN URL
    global DEFAULT_CDN_URL
    DEFAULT_CDN_URL = cdn_url
    
    try:
        # Khởi chạy FFmpeg
        ffmpeg_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Đợi một chút để xem có lỗi ngay không
        try:
            return_code = ffmpeg_process.wait(timeout=2)
            if return_code != 0:
                error = ffmpeg_process.stderr.read().decode('utf-8')
                ffmpeg_process = None
                return False, f"FFmpeg failed: {error}"
        except subprocess.TimeoutExpired:
            # Timeout nghĩa là ffmpeg đang chạy, đây là điều tốt
            pass
            
        return True, "Streaming started successfully."
    except Exception as e:
        if ffmpeg_process:
            try:
                ffmpeg_process.terminate()
            except:
                pass
            ffmpeg_process = None
        return False, f"Error starting FFmpeg: {e}"

def stop_ffmpeg():
    global ffmpeg_process
    if ffmpeg_process is None:
        return False, "No streaming process is running."
    try:
        # Lưu PID trước để có thể kiểm tra sau
        ffmpeg_pid = ffmpeg_process.pid
        print(f"Attempting to terminate FFmpeg process (PID: {ffmpeg_pid})", file=sys.stderr)
        
        # Thử terminate (SIGTERM) trước
        ffmpeg_process.terminate()
        
        # Đợi tối đa 3 giây
        try:
            ffmpeg_process.wait(timeout=3)
            print(f"FFmpeg process terminated gracefully", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print(f"FFmpeg process did not terminate gracefully, sending SIGKILL", file=sys.stderr)
            # Nếu quá thời gian, dùng kill (SIGKILL)
            ffmpeg_process.kill()
            ffmpeg_process.wait(timeout=2)
            print(f"FFmpeg process killed with SIGKILL", file=sys.stderr)
        
        # Kiểm tra thêm bằng ps để đảm bảo
        try:
            # Sử dụng ps để kiểm tra xem tiến trình còn tồn tại không
            ps_check = subprocess.run(["ps", "-p", str(ffmpeg_pid)], 
                                     stdout=subprocess.PIPE, 
                                     stderr=subprocess.PIPE)
            
            # Nếu tiến trình vẫn còn (ps trả về 0)
            if ps_check.returncode == 0:
                print(f"FFmpeg process still exists after SIGKILL, using system kill", file=sys.stderr)
                # Dùng kill của hệ thống
                os.system(f"kill -9 {ffmpeg_pid}")
        except Exception as e:
            print(f"Error checking process status: {e}", file=sys.stderr)
        
        # Kiểm tra lại PID của FFmpeg
        try:
            check_cmd = f"ps aux | grep {ffmpeg_pid} | grep -v grep"
            check_result = os.popen(check_cmd).read()
            if check_result.strip():
                print(f"WARNING: Process {ffmpeg_pid} may still be running after kill attempts", file=sys.stderr)
                print(f"Running processes: {check_result}", file=sys.stderr)
            else:
                print(f"Confirmed: Process {ffmpeg_pid} is stopped", file=sys.stderr)
        except Exception as e:
            print(f"Error during final check: {e}", file=sys.stderr)
        
        # Đặt process về None
        ffmpeg_process = None
        return True, "Streaming stopped successfully."
    except Exception as e:
        # Trong trường hợp có lỗi, thử kill -9 trực tiếp
        try:
            if ffmpeg_process and ffmpeg_process.pid:
                os.system(f"kill -9 {ffmpeg_process.pid}")
                print(f"Emergency kill -9 sent to PID {ffmpeg_process.pid}", file=sys.stderr)
                ffmpeg_process = None
                return True, "Streaming forcibly terminated after error."
        except:
            pass
        
        return False, f"Error stopping FFmpeg: {e}"

@app.route("/")
def index():
    return """
    <html>
    <head><title>Video Streaming Server</title></head>
    <body>
        <h1>Video Streaming Server</h1>
        <p>Use the following endpoints:</p>
        <ul>
            <li><a href="/start">Start streaming</a> (can add parameters: cdn_url, multicast_addr, port, ttl)</li>
            <li><a href="/stop">Stop streaming</a></li>
            <li><a href="/status">Check status</a></li>
        </ul>
    </body>
    </html>
    """

@app.route("/start", methods=["GET"])
def start_stream():
    # Cho phép truyền tham số qua query string (nếu không có sẽ dùng giá trị mặc định)
    cdn_url = request.args.get("cdn_url", DEFAULT_CDN_URL)
    multicast_addr = request.args.get("multicast_addr", DEFAULT_MULTICAST_ADDR)
    port = request.args.get("port", DEFAULT_PORT)
    ttl = request.args.get("ttl", DEFAULT_TTL)
    
    # Xác định loại streaming
    stream_type = "unicast" if multicast_addr.startswith('127.') else "multicast"
    print(f"Starting {stream_type} stream from {cdn_url} to {multicast_addr}:{port} with TTL {ttl}", file=sys.stderr)
    
    # Thử cấu hình tường lửa nếu sử dụng multicast
    if stream_type == "multicast":
        configure_firewall()
    
    success, message = start_ffmpeg(cdn_url, multicast_addr, port, ttl)
    return jsonify({"success": success, "message": message, "stream_type": stream_type})

@app.route("/stop", methods=["GET"])
def stop_stream():
    success, message = stop_ffmpeg()
    return jsonify({"success": success, "message": message})

@app.route("/status", methods=["GET"])
def status():
    if ffmpeg_process is None:
        return jsonify({"status": "stopped"})
    
    # Kiểm tra xem ffmpeg còn chạy không
    try:
        returncode = ffmpeg_process.poll()
        if returncode is not None:
            # Process đã kết thúc
            error = ffmpeg_process.stderr.read().decode('utf-8')
            return jsonify({
                "status": "stopped", 
                "exit_code": returncode,
                "error": error
            })
        else:
            return jsonify({"status": "running"})
    except:
        return jsonify({"status": "unknown"})

if __name__ == "__main__":
    # Kiểm tra xem ffmpeg có được cài đặt không
    if subprocess.call(["which", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE) != 0:
        print("ffmpeg is not installed. Please install ffmpeg before running this script.")
        exit(1)
    
    print("\nVideo Streaming Server", file=sys.stderr)
    print("==========================", file=sys.stderr)
    print(f"Default CDN URL: {DEFAULT_CDN_URL}", file=sys.stderr)
    print(f"Default address: {DEFAULT_MULTICAST_ADDR}:{DEFAULT_PORT}", file=sys.stderr)
    addr_type = "unicast (localhost)" if DEFAULT_MULTICAST_ADDR.startswith('127.') else "multicast"
    print(f"Address type: {addr_type}", file=sys.stderr)
    print(f"Default TTL: {DEFAULT_TTL}", file=sys.stderr)
    print("==========================\n", file=sys.stderr)
    
    # Chạy server Flask trên cổng 3000
    app.run(host="0.0.0.0", port=3000, debug=True)
