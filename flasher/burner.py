#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
固件烧录与底模通信驱动模块
对标 Web 版 esptool-js 核心参数与行为
"""

import sys
import subprocess
import shutil
from typing import List, Tuple, Optional, Callable

def find_esptool_cmd() -> List[str]:
    """寻找可用的 esptool 命令形式"""
    if shutil.which("esptool"):
        return ["esptool"]
    elif shutil.which("esptool.py"):
        return ["esptool.py"]
    return [sys.executable, "-m", "esptool"]

def read_chip_info(port: str, baud: int = 115200) -> Tuple[bool, str]:
    """读取目标设备的芯片信息"""
    base_cmd = find_esptool_cmd()
    cmd = base_cmd + ["--port", port, "--baud", str(baud), "chip_id"]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
        return proc.returncode == 0, proc.stdout
    except Exception as e:
        return False, str(e)

def erase_chip(port: str, baud: int = 921600, log_callback: Optional[Callable[[str], None]] = None) -> bool:
    """擦除整片 Flash 数据（对标网页端 清除设备数据 按钮）"""
    base_cmd = find_esptool_cmd()
    cmd = base_cmd + [
        "--chip", "auto",
        "--port", port,
        "--baud", str(baud),
        "erase_flash"
    ]
    if log_callback:
        log_callback(f"[CMD] {' '.join(cmd)}")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    if proc.stdout:
        for line in proc.stdout:
            if log_callback:
                log_callback(line.rstrip())
    proc.wait()
    return proc.returncode == 0

def flash_firmware(
    port: str,
    files_with_offsets: List[Tuple[str, str]],  # [(offset_hex_or_int, filepath), ...]
    baud: int = 921600,
    chip: str = "auto",
    flash_mode: str = "keep",
    flash_freq: str = "keep",
    flash_size: str = "keep",
    log_callback: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    烧录固件到设备
    files_with_offsets: 例如 [('0x0', '/path/to/firmware.bin')] 或多个分卷
    """
    base_cmd = find_esptool_cmd()
    cmd = base_cmd + [
        "--chip", chip,
        "--port", port,
        "--baud", str(baud),
        "--before", "default_reset",
        "--after", "hard_reset",
        "write_flash",
        "-z",  # 启用压缩写入（对标 compress: true）
        "--flash_mode", flash_mode,
        "--flash_freq", flash_freq,
        "--flash_size", flash_size,
    ]

    for offset, filepath in files_with_offsets:
        # 确保 offset 为 0x 格式
        if not offset.startswith("0x") and not offset.startswith("0X"):
            try:
                val = int(offset, 0)
                offset = hex(val)
            except ValueError:
                pass
        cmd.extend([offset, filepath])

    if log_callback:
        log_callback(f"[CMD] {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    if proc.stdout:
        for line in proc.stdout:
            clean_line = line.rstrip()
            if clean_line and log_callback:
                log_callback(clean_line)

    proc.wait()
    return proc.returncode == 0
