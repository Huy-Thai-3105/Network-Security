#!/usr/bin/env python3
import requests
import time
import psutil
import os
from datetime import datetime
import json
import subprocess
import threading
from urllib.parse import urlparse
import numpy as np

class NetworkStats:
    def __init__(self):
        self.download_speed = 0
        self.upload_speed = 0
        self.latency = 0
        self.bytes_sent = 0
        self.bytes_recv = 0
        self.last_bytes_sent = 0
        self.last_bytes_recv = 0
        self.bandwidth_usage = 0
        self.cdn_bytes = 0
        self.multicast_bytes = 0
        self.hls_bytes = 0
        self.previous_total_sent = 0
        self.previous_total_recv = 0
        
        # Reset counters to start measuring from zero
        net_io = psutil.net_io_counters()
        self.previous_total_sent = net_io.bytes_sent
        self.previous_total_recv = net_io.bytes_recv

    def update(self):
        net_io = psutil.net_io_counters()
        current_bytes_sent = net_io.bytes_sent - self.previous_total_sent
        current_bytes_recv = net_io.bytes_recv - self.previous_total_recv
        
        # Calculate bandwidth usage (bytes per second)
        if self.last_bytes_sent > 0 and self.last_bytes_recv > 0:
            send_rate = (current_bytes_sent - self.last_bytes_sent) / 5  # 5 seconds interval
            recv_rate = (current_bytes_recv - self.last_bytes_recv) / 5
            self.bandwidth_usage = send_rate + recv_rate
        
        self.last_bytes_sent = current_bytes_sent
        self.last_bytes_recv = current_bytes_recv
        self.bytes_sent = current_bytes_sent
        self.bytes_recv = current_bytes_recv

def get_hls_stats():
    """Get HLS streaming statistics"""
    try:
        response = requests.get('http://localhost:3000/status')
        return response.json()
    except Exception as e:
        print(f"Error getting HLS stats: {e}")
        return {"multicast_running": False, "hls_running": False}

def get_system_stats():
    """Get system resource usage"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return {
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "disk_percent": disk.percent
    }

def measure_latency(host="localhost", port=3000):
    """Measure latency to the streaming server"""
    try:
        start_time = time.time()
        requests.get(f"http://{host}:{port}/status")
        end_time = time.time()
        return (end_time - start_time) * 1000  # Convert to milliseconds
    except Exception as e:
        print(f"Error measuring latency: {e}")
        return -1

def get_segment_download_time():
    """Measure HLS segment download time"""
    try:
        start_time = time.time()
        response = requests.get('http://localhost:3000/hls/playlist.m3u8')
        if response.status_code == 200:
            # Get the latest segment from playlist
            segments = [line for line in response.text.split('\n') if line.endswith('.ts')]
            if segments:
                latest_segment = segments[-1]
                response = requests.get(f'http://localhost:3000/hls/{latest_segment}')
                if response.status_code == 200:
                    duration = (time.time() - start_time) * 1000  # Convert to milliseconds
                    # Estimate CDN bytes based on segment size
                    return duration, len(response.content)
        return -1, 0
    except Exception as e:
        print(f"Error getting segment download time: {e}")
        return -1, 0

def get_cdn_stats(cdn_url="http://34.120.70.159/13129933_3840_2160_30fps.mp4"):
    """Get CDN connection stats"""
    try:
        start_time = time.time()
        response = requests.head(cdn_url, timeout=5)
        latency = (time.time() - start_time) * 1000
        
        # Get content length if available
        content_length = 0
        if 'Content-Length' in response.headers:
            content_length = int(response.headers['Content-Length'])
            
        return {
            "cdn_latency": latency,
            "cdn_status": response.status_code,
            "content_length": content_length
        }
    except Exception as e:
        print(f"Error getting CDN stats: {e}")
        return {
            "cdn_latency": -1,
            "cdn_status": -1,
            "content_length": 0
        }

def format_bytes(bytes):
    """Format bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024
    return f"{bytes:.2f} TB"

def save_performance_report(stats, duration, summary):
    """Save performance report to a text file"""
    with open('performance.txt', 'w') as f:
        f.write("=== VIDEO STREAMING PERFORMANCE REPORT ===\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Duration: {duration} seconds\n\n")
        
        f.write("=== SYSTEM PERFORMANCE ===\n")
        f.write(f"Average CPU Usage: {summary['avg_cpu']:.2f}%\n")
        f.write(f"Average Memory Usage: {summary['avg_memory']:.2f}%\n")
        f.write(f"Disk Usage: {summary['avg_disk']:.2f}%\n\n")
        
        f.write("=== NETWORK PERFORMANCE ===\n")
        f.write(f"Average Bandwidth Usage: {format_bytes(summary['avg_bandwidth'])}/s\n")
        f.write(f"Total Data Sent: {format_bytes(summary['last_bytes_sent'])}\n")
        f.write(f"Total Data Received: {format_bytes(summary['last_bytes_recv'])}\n")
        f.write(f"Estimated CDN Data: {format_bytes(summary['total_cdn_bytes'])}\n\n")
        
        f.write("=== LATENCY STATISTICS ===\n")
        f.write(f"Server Latency (ms):\n")
        f.write(f"  Average: {summary['avg_latency']:.2f}\n")
        f.write(f"  Minimum: {summary['min_latency']:.2f}\n")
        f.write(f"  Maximum: {summary['max_latency']:.2f}\n")
        f.write(f"  Standard Deviation: {summary['std_latency']:.2f}\n\n")
        
        f.write("=== HLS SEGMENT STATISTICS ===\n")
        f.write(f"Segment Download Time (ms):\n")
        f.write(f"  Average: {summary['avg_segment_time']:.2f}\n")
        f.write(f"  Minimum: {summary['min_segment_time']:.2f}\n")
        f.write(f"  Maximum: {summary['max_segment_time']:.2f}\n")
        f.write(f"  Standard Deviation: {summary['std_segment_time']:.2f}\n\n")
        
        f.write("=== ANALYSIS AND RECOMMENDATIONS ===\n")
        
        # Stream quality analysis
        if summary['avg_latency'] < 10:
            f.write("Stream Latency: Excellent (< 10ms)\n")
        elif summary['avg_latency'] < 50:
            f.write("Stream Latency: Good (< 50ms)\n")
        else:
            f.write("Stream Latency: Poor (> 50ms) - Consider network optimization\n")
            
        # Bandwidth analysis
        avg_bandwidth_mb = summary['avg_bandwidth'] / 1024 / 1024
        if avg_bandwidth_mb < 1:
            f.write(f"Bandwidth Usage: Low ({avg_bandwidth_mb:.2f} MB/s)\n")
        elif avg_bandwidth_mb < 5:
            f.write(f"Bandwidth Usage: Moderate ({avg_bandwidth_mb:.2f} MB/s)\n")
        else:
            f.write(f"Bandwidth Usage: High ({avg_bandwidth_mb:.2f} MB/s) - Consider compression\n")
            
        # System load analysis
        if summary['avg_cpu'] > 80:
            f.write("CPU Usage: High (> 80%) - Consider scaling resources\n")
        else:
            f.write(f"CPU Usage: Normal ({summary['avg_cpu']:.2f}%)\n")
            
        if summary['avg_memory'] > 80:
            f.write("Memory Usage: High (> 80%) - Consider memory optimization\n")
        else:
            f.write(f"Memory Usage: Normal ({summary['avg_memory']:.2f}%)\n")
            
        # Final assessment
        f.write("\nFINAL ASSESSMENT:\n")
        issues = []
        
        if summary['avg_latency'] > 50:
            issues.append("high latency")
        if avg_bandwidth_mb > 5:
            issues.append("high bandwidth usage")
        if summary['avg_cpu'] > 80:
            issues.append("high CPU usage")
        if summary['avg_memory'] > 80:
            issues.append("high memory usage")
            
        if issues:
            f.write(f"The streaming system is experiencing {', '.join(issues)}.\n")
            f.write("Recommendations: Review network configuration, optimize video encoding settings, and consider resource scaling.\n")
        else:
            f.write("The streaming system is performing well. Current configuration appears optimal for the video being streamed.\n")
            
        f.write("\n=== END OF REPORT ===\n")
    
    print(f"Performance report saved to performance.txt")

def monitor_hls_performance(duration=120, cdn_url="http://34.120.70.159/13129933_3840_2160_30fps.mp4"):  # Monitor for 2 minutes by default
    print(f"Starting enhanced HLS performance monitoring for {duration} seconds...")
    print("=" * 70)
    
    start_time = time.time()
    stats = []
    network_stats = NetworkStats()
    
    # Initialize lists for calculating statistics
    latencies = []
    segment_times = []
    bandwidths = []
    segment_sizes = []
    cpu_usages = []
    memory_usages = []
    disk_usages = []
    total_cdn_bytes = 0
    
    # Get initial CDN stats
    cdn_stats = get_cdn_stats(cdn_url)
    print(f"CDN Content Length: {format_bytes(cdn_stats['content_length'])}")
    
    while time.time() - start_time < duration:
        current_time = datetime.now().strftime("%H:%M:%S")
        
        # Update network stats
        network_stats.update()
        
        # Get various stats
        hls_stats = get_hls_stats()
        system_stats = get_system_stats()
        cpu_usages.append(system_stats['cpu_percent'])
        memory_usages.append(system_stats['memory_percent'])
        disk_usages.append(system_stats['disk_percent'])
        
        latency = measure_latency()
        segment_download_time, segment_size = get_segment_download_time()
        
        # Add segment size to total CDN bytes estimation
        if segment_size > 0:
            total_cdn_bytes += segment_size
            segment_sizes.append(segment_size)
        
        if latency > 0:
            latencies.append(latency)
        if segment_download_time > 0:
            segment_times.append(segment_download_time)
        if network_stats.bandwidth_usage > 0:
            bandwidths.append(network_stats.bandwidth_usage)
        
        # Combine stats
        current_stats = {
            "timestamp": current_time,
            "hls_status": hls_stats,
            "system_stats": system_stats,
            "network_stats": {
                "latency_ms": latency,
                "segment_download_time_ms": segment_download_time,
                "segment_size_bytes": segment_size,
                "bandwidth_usage_bps": network_stats.bandwidth_usage,
                "bytes_sent": network_stats.bytes_sent,
                "bytes_recv": network_stats.bytes_recv
            }
        }
        
        stats.append(current_stats)
        
        # Print current stats
        print(f"\nTime: {current_time}")
        print(f"HLS Status: {'Running' if hls_stats['hls_running'] else 'Stopped'}")
        print(f"System Performance:")
        print(f"  CPU Usage: {system_stats['cpu_percent']}%")
        print(f"  Memory Usage: {system_stats['memory_percent']}%")
        print(f"  Disk Usage: {system_stats['disk_percent']}%")
        print(f"Network Performance:")
        print(f"  Current Bandwidth Usage: {format_bytes(network_stats.bandwidth_usage)}/s")
        print(f"  Server Latency: {latency:.2f} ms")
        print(f"  Segment Download Time: {segment_download_time:.2f} ms")
        print(f"  Segment Size: {format_bytes(segment_size)}")
        print(f"  Total Data Sent: {format_bytes(network_stats.bytes_sent)}")
        print(f"  Total Data Received: {format_bytes(network_stats.bytes_recv)}")
        
        # Calculate and print statistics if we have enough data
        if len(latencies) > 0:
            print(f"Statistics:")
            print(f"  Avg Latency: {np.mean(latencies):.2f} ms")
            print(f"  Min Latency: {np.min(latencies):.2f} ms")
            print(f"  Max Latency: {np.max(latencies):.2f} ms")
            if len(bandwidths) > 0:
                avg_bandwidth = np.mean(bandwidths)
                print(f"  Avg Bandwidth: {format_bytes(avg_bandwidth)}/s")
                if len(segment_sizes) > 0:
                    print(f"  Estimated CDN Usage: {format_bytes(total_cdn_bytes)}")
        
        print("-" * 70)
        
        time.sleep(5)  # Check every 5 seconds
    
    # Save stats to file
    with open('hls_performance_stats.json', 'w') as f:
        json.dump(stats, f, indent=4)
    
    # Create summary for performance report
    summary = {
        "avg_cpu": np.mean(cpu_usages) if cpu_usages else 0,
        "avg_memory": np.mean(memory_usages) if memory_usages else 0,
        "avg_disk": np.mean(disk_usages) if disk_usages else 0,
        "avg_bandwidth": np.mean(bandwidths) if bandwidths else 0,
        "avg_latency": np.mean(latencies) if latencies else 0,
        "min_latency": np.min(latencies) if latencies else 0,
        "max_latency": np.max(latencies) if latencies else 0,
        "std_latency": np.std(latencies) if latencies else 0,
        "avg_segment_time": np.mean(segment_times) if segment_times else 0,
        "min_segment_time": np.min(segment_times) if segment_times else 0,
        "max_segment_time": np.max(segment_times) if segment_times else 0,
        "std_segment_time": np.std(segment_times) if segment_times else 0,
        "total_cdn_bytes": total_cdn_bytes,
        "last_bytes_sent": network_stats.bytes_sent,
        "last_bytes_recv": network_stats.bytes_recv
    }
    
    # Print final statistics
    print("\nFinal Statistics:")
    
    if len(latencies) > 0:
        print(f"Latency (ms):")
        print(f"  Average: {np.mean(latencies):.2f}")
        print(f"  Minimum: {np.min(latencies):.2f}")
        print(f"  Maximum: {np.max(latencies):.2f}")
        print(f"  Standard Deviation: {np.std(latencies):.2f}")
    
    if len(segment_times) > 0:
        print(f"\nSegment Download Time (ms):")
        print(f"  Average: {np.mean(segment_times):.2f}")
        print(f"  Minimum: {np.min(segment_times):.2f}")
        print(f"  Maximum: {np.max(segment_times):.2f}")
        print(f"  Standard Deviation: {np.std(segment_times):.2f}")
    
    if len(bandwidths) > 0:
        print(f"\nBandwidth Usage (bytes/s):")
        print(f"  Average: {format_bytes(np.mean(bandwidths))}/s")
        print(f"  Minimum: {format_bytes(np.min(bandwidths))}/s")
        print(f"  Maximum: {format_bytes(np.max(bandwidths))}/s")
        print(f"  Standard Deviation: {format_bytes(np.std(bandwidths))}/s")
    
    print(f"\nData Transfer:")
    print(f"  Total Data Sent: {format_bytes(network_stats.bytes_sent)}")
    print(f"  Total Data Received: {format_bytes(network_stats.bytes_recv)}")
    print(f"  Estimated CDN Data: {format_bytes(total_cdn_bytes)}")
    
    # Save performance report
    save_performance_report(stats, duration, summary)
    
    print("\nMonitoring completed. Detailed stats saved to hls_performance_stats.json")
    return stats

if __name__ == "__main__":
    # Start monitoring
    monitor_hls_performance() 