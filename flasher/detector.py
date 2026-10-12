#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备与串口自动探测模块
"""

import sys
import serial.tools.list_ports
from typing import List, Dict, Any, Optional

ESP_VID_PID = [
    (0x303A, None),  # Espressif USB JTAG / CDC / OTG
    (0x10C4, 0xEA60),  # Silicon Labs CP210x
    (0x1A86, 0x7523),  # QinHeng CH340
    (0x1A86, 0x55D4),  # QinHeng CH9102 / CH343
    (0x0403, 0x6001),  # FTDI FT232R
    (0x0403, 0x6010),  # FTDI FT2232
]

def scan_ports() -> List[Dict[str, Any]]:
    """
    扫描当前系统中连接的所有串口，并按 ESP 相关设备优先排序
    """
    raw_ports = serial.tools.list_ports.comports()
    results = []

    for p in raw_ports:
        device = p.device
        description = p.description or ""
        hwid = p.hwid or ""
        vid = p.vid
        pid = p.pid

        # 过滤掉 Linux 上未连接物理设备的默认主板虚拟 ttyS0-ttyS31
        if device.startswith("/dev/ttyS") and description == "n/a" and hwid == "n/a":
            continue

        is_esp = False
        priority = 0

        # 判断是否为已知的 ESP / 串口芯片 VID/PID
        if vid is not None:
            for target_vid, target_pid in ESP_VID_PID:
                if vid == target_vid and (target_pid is None or pid == target_pid):
                    is_esp = True
                    priority = 10
                    break

        # 判断关键词
        desc_lower = description.lower()
        if any(k in desc_lower for k in ["espressif", "esp32", "jtag", "ch340", "cp210", "usb-serial", "uart"]):
            is_esp = True
            priority = max(priority, 8)
        elif "usb" in desc_lower or "acm" in device.lower() or "usb" in device.lower():
            priority = max(priority, 5)

        results.append({
            "device": device,
            "description": description,
            "hwid": hwid,
            "vid": vid,
            "pid": pid,
            "is_esp": is_esp,
            "priority": priority
        })

    # 按照优先级降序排列
    results.sort(key=lambda x: x["priority"], reverse=True)
    return results

def get_recommended_port() -> Optional[str]:
    """获取首选的串口设备"""
    ports = scan_ports()
    if ports and ports[0]["priority"] > 0:
        return ports[0]["device"]
    return None
