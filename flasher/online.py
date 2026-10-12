#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
社区与官方精选固件在线拉取模块
对接 ai-passport.folotoy.cn 官方接口
"""

import os
import hashlib
import requests
from typing import List, Dict, Any, Optional

API_BASE = "https://ai-passport.folotoy.cn"

def get_recommendations() -> List[Dict[str, Any]]:
    """获取官方推荐玩法列表"""
    url = f"{API_BASE}/api/plays/recommendations"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("plays", [])
    except Exception as e:
        return []

def download_firmware(firmware_url: str, expected_sha256: Optional[str] = None, save_path: Optional[str] = None) -> Optional[str]:
    """下载指定固件并校验 SHA-256"""
    if not firmware_url.startswith("http"):
        firmware_url = f"{API_BASE}{firmware_url}"

    if not save_path:
        cache_dir = os.path.expanduser("~/.cache/folotoy-flasher")
        os.makedirs(cache_dir, exist_ok=True)
        filename = os.path.basename(firmware_url.split("?")[0]) + ".bin"
        save_path = os.path.join(cache_dir, filename)

    try:
        with requests.get(firmware_url, stream=True, timeout=30) as r:
            r.raise_for_status()
            hasher = hashlib.sha256()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)
            
            if expected_sha256 and hasher.hexdigest().lower() != expected_sha256.lower():
                os.remove(save_path)
                raise ValueError("SHA-256 校验失败，固件已被篡改或下载不完整")

            return save_path
    except Exception as e:
        if save_path and os.path.exists(save_path):
            os.remove(save_path)
        raise e
