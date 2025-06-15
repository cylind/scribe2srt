# -*- coding: utf-8 -*-

"""
这个文件包含了所有与 FFmpeg 和 ffprobe 交互的工具函数。
"""

import sys
import subprocess
import shutil
import json
import os
from typing import Optional, Dict, Any

def is_ffmpeg_available() -> bool:
    """检查 FFmpeg 是否在系统的 PATH 中可用。"""
    return shutil.which("ffmpeg") is not None

def get_media_info(media_file_path: str, log_callback=None) -> Optional[Dict[str, Any]]:
    """使用 ffprobe 获取媒体文件的时长和音频编码。"""
    if not is_ffmpeg_available():
        if log_callback:
            log_callback("  FFmpeg/ffprobe 不可用，跳过媒体信息检测。")
        return None
    
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        command = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name:format=duration",
            "-of", "json",
            media_file_path
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8',
            startupinfo=startupinfo
        )
        
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        codec_name = data.get("streams", [{}])[0].get("codec_name", "N/A")
        
        return {"duration": duration, "codec": codec_name}

    except FileNotFoundError:
        if log_callback:
            log_callback("  错误: ffprobe 未找到。")
        return None
    except (subprocess.CalledProcessError, json.JSONDecodeError, IndexError, KeyError) as e:
        if log_callback:
            log_callback(f"  使用 ffprobe 获取信息失败: {e}")
        return None

def extract_audio(video_path: str, output_path: str, log_callback=None) -> bool:
    """使用 FFmpeg 从视频文件中无损提取音频流。"""
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        command = ["ffmpeg", "-i", video_path, "-vn", "-c:a", "copy", "-y", output_path]
        
        subprocess.run(command, check=True, capture_output=True, text=True, encoding='utf-8', startupinfo=startupinfo)
        
        if log_callback:
            log_callback(f"音频提取成功: {os.path.basename(output_path)}")
        return True
    except FileNotFoundError:
        if log_callback:
            log_callback("FFmpeg 未找到。请确保它已安装并位于系统的PATH中。")
        return False
    except subprocess.CalledProcessError as e:
        error_message = "FFmpeg 提取音频失败。\n"
        error_message += "这可能是因为视频文件已损坏、不包含音频流或编码与容器不兼容。\n"
        error_message += f"返回码: {e.returncode}\n"
        try:
            stderr_output = e.stderr.strip()
            error_message += f"FFmpeg 输出:\n{stderr_output}"
        except Exception as decode_error:
            error_message += f"(无法解码 FFmpeg 的错误输出: {decode_error})"
        if log_callback:
            log_callback(error_message)
        return False
    except Exception as e:
        if log_callback:
            log_callback(f"提取音频时发生未知错误: {e}")
        return False