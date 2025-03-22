#!/usr/bin/env python3
import subprocess
from flask import Flask, request, jsonify, send_from_directory
import sys
import os
import socket
import shutil

app = Flask(__name__)

# Biến toàn cục lưu FFmpeg process
ffmpeg_process = None
hls_process = None

# Thông số mặc định (thay đổi theo nhu cầu)
DEFAULT_CDN_URL = "http://34.120.70.159/152407-802753527_small.mp4"  # URL video từ CDN
DEFAULT_MULTICAST_ADDR = "239.255.0.1"      # Địa chỉ multicast
DEFAULT_PORT = "1234"                          # Cổng phát
DEFAULT_TTL = "2"                             # TTL=2 để có thể đi qua router nội bộ
HLS_SEGMENT_TIME = "2"                         # Độ dài mỗi segment HLS (giây)
HLS_OUTPUT_DIR = "hls_output"                  # Thư mục chứa file HLS

def ensure_hls_dir():
    """Đảm bảo thư mục HLS tồn tại và trống"""
    if os.path.exists(HLS_OUTPUT_DIR):
        shutil.rmtree(HLS_OUTPUT_DIR)
    os.makedirs(HLS_OUTPUT_DIR)

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
    global ffmpeg_process, hls_process
    if ffmpeg_process is not None or hls_process is not None:
        return False, "Streaming is already running."

    # Kiểm tra xem địa chỉ có phải là multicast không
    is_multicast = multicast_addr.startswith('239.') or multicast_addr.startswith('224.')
    is_local = multicast_addr.startswith('127.')
    
    # In thông tin địa chỉ cho debug
    print(f"Stream address: {multicast_addr}", file=sys.stderr)
    print(f"Is multicast: {is_multicast}", file=sys.stderr)
    print(f"Is localhost: {is_local}", file=sys.stderr)
    
    # Lấy địa chỉ IP của máy local
    local_ip = "192.168.0.122"
    print(f"Local IP address: {local_ip}", file=sys.stderr)

    # Đảm bảo thư mục HLS tồn tại và trống
    ensure_hls_dir()
    
    # Cấu hình cho multicast stream
    multicast_command = [
        "ffmpeg",
        "-loglevel", "warning",                  # Giảm log
        "-re",                                   # Đọc với tốc độ thực 
        "-stream_loop", "-1",                    # Loop stream nếu cần thiết
        "-fflags", "+genpts+discardcorrupt+nobuffer+igndts",
        "-flags", "low_delay",
        "-avoid_negative_ts", "make_zero",
        "-analyzeduration", "500000",
        "-probesize", "1000000",
        "-i", cdn_url,
        
        # Video settings
        "-c:v", "libx264",
        "-vsync", "cfr",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-profile:v", "baseline",
        "-level", "3.0",
        "-b:v", "800k",
        "-maxrate", "1000k",
        "-bufsize", "1000k",
        "-r", "24",
        "-x264opts", "no-cabac:no-scenecut:partitions=none:ref=1:me=dia:subme=0:trellis=0:weightp=0:no-weightb:bframes=0:8x8dct=0",
        "-force_key_frames", "expr:gte(t,n_forced*0.5)",
        "-g", "12",
        "-keyint_min", "12",
        "-sc_threshold", "0",
        "-vf", "fps=fps=24",
        
        # Audio settings
        "-c:a", "aac",
        "-b:a", "96k",
        "-ar", "44100",
        "-ac", "2",
        
        # Output settings
        "-max_muxing_queue_size", "9999",
        "-muxdelay", "0",
        "-muxpreload", "0",
        "-f", "mpegts",
    ]

    # Thêm đầu ra cho multicast
    if is_multicast:
        multicast_output = f"udp://{multicast_addr}:{port}?pkt_size=1316&buffer_size=65536&ttl={ttl}"
    else:
        multicast_output = f"udp://{multicast_addr}:{port}?pkt_size=1316&buffer_size=65536"
    
    multicast_command.append(multicast_output)

    # Cấu hình cho HLS stream
    hls_command = [
        "ffmpeg",
        "-loglevel", "warning",
        "-re",
        "-i", cdn_url,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:v", "800k",
        "-b:a", "96k",
        "-ar", "44100",
        "-ac", "2",
        "-f", "hls",
        "-hls_time", HLS_SEGMENT_TIME,
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments",
        "-hls_segment_filename", f"{HLS_OUTPUT_DIR}/segment_%d.ts",
        f"{HLS_OUTPUT_DIR}/playlist.m3u8"
    ]
    
    try:
        # Khởi chạy FFmpeg cho multicast
        print(f"Starting multicast stream...", file=sys.stderr)
        ffmpeg_process = subprocess.Popen(multicast_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Khởi chạy FFmpeg cho HLS
        print(f"Starting HLS stream...", file=sys.stderr)
        hls_process = subprocess.Popen(hls_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Đợi một chút để xem có lỗi ngay không
        try:
            return_code = ffmpeg_process.wait(timeout=2)
            if return_code != 0:
                error = ffmpeg_process.stderr.read().decode('utf-8')
                ffmpeg_process = None
                return False, f"Multicast FFmpeg failed: {error}"
        except subprocess.TimeoutExpired:
            pass

        try:
            return_code = hls_process.wait(timeout=2)
            if return_code != 0:
                error = hls_process.stderr.read().decode('utf-8')
                hls_process = None
                return False, f"HLS FFmpeg failed: {error}"
        except subprocess.TimeoutExpired:
            pass
            
        print(f"\n----- HƯỚNG DẪN KẾT NỐI -----", file=sys.stderr)
        print(f"1. Xem qua Multicast:", file=sys.stderr)
        print(f"   - VLC -> Media -> Open Network Stream -> Nhập: udp://@{multicast_addr}:{port}", file=sys.stderr)
        print(f"   - Hoặc: vlc udp://@{multicast_addr}:{port} --network-caching=50", file=sys.stderr)
        print(f"2. Xem qua HLS:", file=sys.stderr)
        print(f"   - VLC -> Media -> Open Network Stream -> Nhập: http://localhost:3000/hls/playlist.m3u8", file=sys.stderr)
        print(f"   - Hoặc trình duyệt web: http://localhost:3000/hls/player.html", file=sys.stderr)
        print(f"--------------------------------\n", file=sys.stderr)
        
        return True, "Streaming started successfully (both Multicast and HLS)."
    except Exception as e:
        if ffmpeg_process:
            ffmpeg_process.terminate()
            ffmpeg_process = None
        if hls_process:
            hls_process.terminate()
            hls_process = None
        return False, f"Error starting stream: {e}"

def stop_ffmpeg():
    global ffmpeg_process, hls_process
    success = True
    message = []
    
    # Dừng multicast process
    if ffmpeg_process:
        try:
            ffmpeg_process.terminate()
            try:
                ffmpeg_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                ffmpeg_process.kill()
            message.append("Multicast stream stopped")
        except Exception as e:
            success = False
            message.append(f"Error stopping multicast: {e}")
        finally:
            ffmpeg_process = None
    
    # Dừng HLS process
    if hls_process:
        try:
            hls_process.terminate()
            try:
                hls_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                hls_process.kill()
            message.append("HLS stream stopped")
        except Exception as e:
            success = False
            message.append(f"Error stopping HLS: {e}")
        finally:
            hls_process = None
    
    # Dọn dẹp thư mục HLS
    try:
        if os.path.exists(HLS_OUTPUT_DIR):
            shutil.rmtree(HLS_OUTPUT_DIR)
    except Exception as e:
        print(f"Error cleaning HLS directory: {e}", file=sys.stderr)
    
    return success, ". ".join(message)

@app.route("/")
def index():
    return """
    <html>
    <head>
        <title>Video Streaming Server</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            h1 { color: #333; }
            .endpoint { background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; }
            .player { margin-top: 20px; }
        </style>
    </head>
    <body>
        <h1>Video Streaming Server</h1>
        <p>Available endpoints:</p>
        <div class="endpoint">
            <h3>Start Streaming</h3>
            <p>GET /start</p>
            <p>Parameters:</p>
            <ul>
                <li>cdn_url (optional): Source video URL</li>
                <li>multicast_addr (optional): Multicast address</li>
                <li>port (optional): Port number</li>
                <li>ttl (optional): Time to live</li>
            </ul>
        </div>
        <div class="endpoint">
            <h3>Stop Streaming</h3>
            <p>GET /stop</p>
        </div>
        <div class="endpoint">
            <h3>Check Status</h3>
            <p>GET /status</p>
        </div>
        <div class="endpoint">
            <h3>HLS Stream</h3>
            <p>Access the HLS stream at: /hls/playlist.m3u8</p>
            <p>Web player available at: /hls/player.html</p>
        </div>
        <div class="player">
            <h2>Live Stream Player</h2>
            <video id="video" controls style="max-width: 100%;">
                <source src="/hls/playlist.m3u8" type="application/x-mpegURL">
                Your browser does not support HTML5 video.
            </video>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <script>
            if (Hls.isSupported()) {
                var video = document.getElementById('video');
                var hls = new Hls();
                hls.loadSource('/hls/playlist.m3u8');
                hls.attachMedia(video);
                hls.on(Hls.Events.MANIFEST_PARSED, function() {
                    video.play();
                });
            }
        </script>
    </body>
    </html>
    """

@app.route("/start")
def start_stream():
    cdn_url = request.args.get("cdn_url", DEFAULT_CDN_URL)
    multicast_addr = request.args.get("multicast_addr", DEFAULT_MULTICAST_ADDR)
    port = request.args.get("port", DEFAULT_PORT)
    ttl = request.args.get("ttl", DEFAULT_TTL)
    
    success, message = start_ffmpeg(cdn_url, multicast_addr, port, ttl)
    return jsonify({"success": success, "message": message})

@app.route("/stop")
def stop_stream():
    success, message = stop_ffmpeg()
    return jsonify({"success": success, "message": message})

@app.route("/status")
def status():
    return jsonify({
        "multicast_running": ffmpeg_process is not None,
        "hls_running": hls_process is not None
    })

@app.route('/hls/<path:filename>')
def serve_hls(filename):
    return send_from_directory(HLS_OUTPUT_DIR, filename)

@app.route('/hls/player.html')
def hls_player():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>HLS Player</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f0f0f0; }
            .container { max-width: 800px; margin: 0 auto; }
            video { width: 100%; background: #000; }
            .controls { margin-top: 20px; }
            button { padding: 10px 20px; margin: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Live Stream</h1>
            <video id="video" controls></video>
            <div class="controls">
                <button onclick="reloadPlayer()">Reload Player</button>
            </div>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <script>
            function initPlayer() {
                if (Hls.isSupported()) {
                    var video = document.getElementById('video');
                    var hls = new Hls({
                        debug: false,
                        enableWorker: true,
                        lowLatencyMode: true,
                        backBufferLength: 90
                    });
                    hls.loadSource('/hls/playlist.m3u8');
                    hls.attachMedia(video);
                    hls.on(Hls.Events.MANIFEST_PARSED, function() {
                        video.play();
                    });
                }
            }
            
            function reloadPlayer() {
                location.reload();
            }
            
            initPlayer();
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    # Kiểm tra xem ffmpeg có được cài đặt không
    if subprocess.call(["which", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE) != 0:
        print("ffmpeg is not installed. Please install ffmpeg before running this script.")
        exit(1)
    
    print("\nVideo Streaming Server", file=sys.stderr)
    print("==========================", file=sys.stderr)
    print(f"Default CDN URL: {DEFAULT_CDN_URL}", file=sys.stderr)
    print(f"Default address: {DEFAULT_MULTICAST_ADDR}:{DEFAULT_PORT}", file=sys.stderr)
    print(f"HLS output directory: {HLS_OUTPUT_DIR}", file=sys.stderr)
    print(f"HLS segment time: {HLS_SEGMENT_TIME} seconds", file=sys.stderr)
    print("==========================\n", file=sys.stderr)
    
    # Chạy server Flask trên cổng 3000
    app.run(host="0.0.0.0", port=3000, debug=True)
