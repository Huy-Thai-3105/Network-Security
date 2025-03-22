# Video Streaming Server with Multicast and HLS

A video streaming server that supports both Multicast and HLS (HTTP Live Streaming), allowing viewing of the stream on various platforms.

## System Requirements

- Python 3.7 or later
- FFmpeg
- VLC Media Player (to view the stream)
- Modern web browser (to view HLS stream)

## Installation

1. Install FFmpeg:
   ```bash
   # macOS
   brew install ffmpeg

   # Ubuntu/Debian
   sudo apt-get install ffmpeg

   # Windows
   # Download from https://ffmpeg.org/download.html
   ```

2. Install Python libraries:
   ```bash
   pip3 install flask
   ```

3. Clone the source code:
   ```bash
   git clone <repository_url>
   cd <repository_directory>
   ```

## Usage

### 1. Start the Server

The server needs to be run with sudo to configure the firewall for multicast:

```bash
sudo python3 server.py
```

The server will run on port 3000. Access http://localhost:3000 to view the web interface.

### 2. Start the Multicast Client

In a new terminal:

```bash
python3 checkMulticast.py
```

### 3. Start Streaming

Streaming can be started using one of the following methods:

a. Through API:
```bash
curl "http://localhost:3000/start?cdn_url=http://34.120.70.159/152407-802753527_small.mp4&multicast_addr=239.255.0.1&port=1234&ttl=2"
```

b. Access http://localhost:3000 and use the web interface

### 4. View the Stream

There are three ways to view the stream:

1. **Multicast with VLC**:
   - Open VLC
   - Media -> Open Network Stream
   - Enter: `udp://@239.255.0.1:1234`
   - In Advanced Options, set Caching: 50ms
   - Click Play

2. **HLS on a web browser**:
   - Access: http://localhost:3000/hls/player.html

3. **HLS with VLC**:
   - Open VLC
   - Media -> Open Network Stream
   - Enter: `http://localhost:3000/hls/playlist.m3u8`

### 5. Configure VLC for smoother viewing

If the stream is choppy/lagging, follow these steps:

1. Open VLC -> Tools -> Preferences -> Input & Codecs:
   - Network caching: 50ms
   - Hardware decoding: Disable
   - Skip frames: Enable

2. Restart VLC after changing the settings

### 6. Stop Streaming

```bash
curl http://localhost:3000/stop
```

## API Endpoints

1. `GET /start`
   - Start streaming
   - Parameters:
     - `cdn_url`: Source video URL
     - `multicast_addr`: Multicast address
     - `port`: Port
     - `ttl`: Time to live

2. `GET /stop`
   - Stop streaming

3. `GET /status`
   - Check streaming status

4. `GET /hls/playlist.m3u8`
   - HLS playlist

5. `GET /hls/player.html`
   - HLS web player

## Troubleshooting

1. **Port 3000 is already in use**:
   ```bash
   sudo lsof -i :3000  # Check the process using port 3000
   sudo kill -9 <PID>  # Kill that process
   ```

2. **Not receiving multicast stream**:
   - Check firewall
   - Ensure the network supports multicast
   - Try adding a route for multicast:
     ```bash
     sudo route add -net 239.0.0.0/8 -interface en0  # Replace en0 with your interface
     ```

3. **Stream is choppy/lagging**:
   - Lower network caching in VLC to 50ms
   - Disable hardware decoding
   - Enable skip frames

## Security

- The server should be run in an internal network
- Configure firewall appropriately
- Do not expose ports to the internet

## License

MIT License