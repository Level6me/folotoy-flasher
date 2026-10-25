#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Releases 固件在线拉取模块
支持从任意 GitHub 仓库的 Release 列表中提取 .bin 等固件资产并下载
"""

import os
import re
import requests
from typing import List, Dict, Any, Optional, Tuple

DEFAULT_GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

def get_auth_token(custom_token: Optional[str] = None) -> Optional[str]:
    """获取 GitHub Token（优先自定义 -> 环境变量 -> 备用令牌）"""
    if custom_token and custom_token.strip():
        return custom_token.strip()
    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token
    return DEFAULT_GITHUB_TOKEN

def parse_github_repo(repo_input: str) -> Tuple[str, str]:
    """
    解析 GitHub 仓库地址，支持各种格式：
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - http://github.com/owner/repo
    - github.com/owner/repo
    - owner/repo
    """
    cleaned = repo_input.strip()
    # 移除结尾的斜杠和 .git
    cleaned = re.sub(r"\.git/?$", "", cleaned).rstrip("/")
    
    # 匹配 https://github.com/owner/repo 或 github.com/owner/repo
    match = re.search(r"(?:github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$", cleaned)
    if match:
        owner, repo = match.group(1), match.group(2)
        return owner, repo
    
    raise ValueError(f"无法识别的 GitHub 仓库地址: '{repo_input}'。格式应如 'owner/repo' 或 'https://github.com/owner/repo'")

def fetch_github_releases(owner: str, repo: str, token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    获取指定仓库的 Release 列表及固件资产
    """
    auth_token = get_auth_token(token)
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "folotoy-flasher"
    }
    if auth_token:
        headers["Authorization"] = f"token {auth_token}"

    url = f"https://api.github.com/repos/{owner}/{repo}/releases"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 404:
            raise ValueError(f"未找到仓库 '{owner}/{repo}'，请检查名称是否正确或仓库是否为私有仓库。")
        elif resp.status_code == 403:
            msg = resp.json().get("message", "API 调用频率受限") if resp.headers.get("Content-Type", "").startswith("application/json") else "403 Forbidden"
            raise ValueError(f"GitHub API 请求受限 (403): {msg}")
        resp.raise_for_status()
        releases_data = resp.json()
    except requests.exceptions.RequestException as e:
        raise ValueError(f"请求 GitHub API 失败: {e}")

    parsed_releases = []
    for rel in releases_data:
        tag_name = rel.get("tag_name", "untagged")
        title = rel.get("name") or tag_name
        published_at = rel.get("published_at", "")[:10]
        prerelease = rel.get("prerelease", False)
        body = rel.get("body", "")

        raw_assets = rel.get("assets", [])
        assets = []
        for a in raw_assets:
            name = a.get("name", "")
            download_url = a.get("browser_download_url")
            size = a.get("size", 0)
            is_bin = name.lower().endswith(".bin")
            assets.append({
                "id": a.get("id"),
                "name": name,
                "size": size,
                "download_url": download_url,
                "is_bin": is_bin
            })

        parsed_releases.append({
            "id": rel.get("id"),
            "tag_name": tag_name,
            "title": title,
            "published_at": published_at,
            "prerelease": prerelease,
            "body": body,
            "assets": assets,
            "bin_count": sum(1 for a in assets if a["is_bin"]),
            "total_count": len(assets)
        })

    return parsed_releases

def download_github_firmware(download_url: str, filename: Optional[str] = None, token: Optional[str] = None) -> str:
    """
    下载 GitHub Release 中的固件文件到本地缓存
    """
    # 仅允许 github.com 及其子域，防止被当作任意 URL 抓取代理并携带 Token 外泄
    from urllib.parse import urlparse
    host = (urlparse(download_url).hostname or "").lower()
    if host != "github.com" and not host.endswith(".github.com"):
        raise ValueError(f"仅支持从 github.com 下载固件，拒绝地址: {download_url}")

    if filename:
        # 防止路径穿越（如 "../../.bashrc"）把固件写到缓存目录之外
        filename = os.path.basename(filename.strip())
    if not filename:
        filename = download_url.split("/")[-1].split("?")[0]
        if not filename.endswith(".bin"):
            filename += ".bin"

    cache_dir = os.path.expanduser("~/.cache/folotoy-flasher/github")
    os.makedirs(cache_dir, exist_ok=True)
    save_path = os.path.join(cache_dir, filename)

    headers = {
        "User-Agent": "folotoy-flasher"
    }
    auth_token = get_auth_token(token)
    if auth_token:
        headers["Authorization"] = f"token {auth_token}"

    try:
        with requests.get(download_url, headers=headers, stream=True, timeout=60, allow_redirects=True) as r:
            r.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        return save_path
    except Exception as e:
        if os.path.exists(save_path):
            os.remove(save_path)
        raise e
