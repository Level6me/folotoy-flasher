#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Folotoy Web Flasher 本地 CLI 主入口
基于 Click + Rich 实现交互式与命令行直通模式
"""

import os
import sys
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from flasher.detector import scan_ports, get_recommended_port
from flasher.burner import flash_firmware, erase_chip, read_chip_info
from flasher.online import get_recommendations, download_firmware

console = Console()

def format_size(bytes_num: int) -> str:
    """格式化字节大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_num < 1024.0:
            return f"{bytes_num:.1f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.1f} TB"

@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(version="1.0.0", prog_name="folotoy-flasher")
def cli(ctx):
    """🤖 Folotoy AI Passport 本地固件刷机工具 (CLI 版)"""
    if ctx.invoked_subcommand is None:
        interactive_menu()

def interactive_menu():
    """交互式引导菜单"""
    console.print(Panel.fit(
        "[bold cyan]Folotoy AI Passport Web-Flasher 本地 CLI 工具[/bold cyan]\n"
        "[dim]移植自 https://ai-passport.folotoy.cn/tools/web-flasher/[/dim]",
        border_style="cyan"
    ))

    while True:
        console.print("\n[bold yellow]请选择操作：[/bold yellow]")
        console.print("  [1] ⚡ 刷入本地固件 (.bin)")
        console.print("  [2] 🌐 浏览并刷入官方精选玩法")
        console.print("  [3] 🔌 查看可用串口设备")
        console.print("  [4] 🧹 清除设备数据 (Erase Flash)")
        console.print("  [5] 🖥️  启动 Web 刷机页面 (极简毛玻璃 UI)")
        console.print("  [0] 退出")

        choice = Prompt.ask("输入选项", choices=["0", "1", "2", "3", "4", "5"], default="1")

        if choice == "0":
            console.print("[dim]已退出。[/dim]")
            sys.exit(0)
        elif choice == "1":
            interactive_flash_local()
        elif choice == "2":
            interactive_install_play()
        elif choice == "3":
            list_ports_command()
        elif choice == "4":
            interactive_erase()
        elif choice == "5":
            start_web_server(port=8080, open_browser=True)
        elif choice == "2":
            interactive_install_play()
        elif choice == "3":
            list_ports_command()
        elif choice == "4":
            interactive_erase()

def select_port_interactive() -> str:
    """交互式选择端口"""
    ports = scan_ports()
    if not ports:
        console.print("[red]❌ 未检测到可用串口设备，请使用数据线连接 ESP32/JTAG 设备后重试！[/red]")
        sys.exit(1)

    table = Table(title="🔌 检测到的串口设备")
    table.add_column("序号", justify="center", style="cyan")
    table.add_column("设备路径", style="green")
    table.add_column("描述", style="white")
    table.add_column("芯片推荐", justify="center")

    choices = []
    default_choice = "1"
    for idx, p in enumerate(ports, start=1):
        idx_str = str(idx)
        choices.append(idx_str)
        rec = "[bold green]★ 推荐 (ESP)[/bold green]" if p["is_esp"] else "[dim]普通[/dim]"
        if p["is_esp"] and default_choice == "1":
            default_choice = idx_str
        table.add_row(idx_str, p["device"], p["description"] or "Unknown", rec)

    console.print(table)
    selected = Prompt.ask("请选择端口序号", choices=choices, default=default_choice)
    return ports[int(selected) - 1]["device"]

def interactive_flash_local():
    """交互式安装本地固件"""
    port = select_port_interactive()
    
    file_path = Prompt.ask("请输入本地 .bin 固件文件的绝对或相对路径")
    file_path = os.path.expanduser(file_path.strip().strip("'\""))
    if not os.path.isfile(file_path):
        console.print(f"[red]❌ 文件不存在: {file_path}[/red]")
        return

    address = Prompt.ask("写入起始地址 (单个合并固件通常为 0x0)", default="0x0")
    baud = Prompt.ask("波特率 (默认 921600)", default="921600")

    console.print(f"\n[cyan]准备烧录:[/cyan] {file_path} -> [green]{port}[/green] @ {address} (波特率 {baud})")
    if not Confirm.ask("确认开始写入?"):
        console.print("[yellow]已取消操作。[/yellow]")
        return

    do_flash_job(port, [(address, file_path)], int(baud))

def interactive_install_play():
    """交互式浏览精选玩法并安装"""
    console.print("[dim]正在加载官方精选玩法列表...[/dim]")
    plays = get_recommendations()
    if not plays:
        console.print("[red]❌ 获取官方玩法列表失败，请检查网络连接。[/red]")
        return

    table = Table(title="🎮 AI Passport 官方精选玩法")
    table.add_column("序号", justify="center", style="cyan")
    table.add_column("玩法名称", style="bold green")
    table.add_column("作者", style="yellow")
    table.add_column("固件大小", justify="right")
    table.add_column("简介", style="dim")

    choices = []
    valid_plays = []
    for idx, play in enumerate(plays, start=1):
        fw = play.get("firmware") or {}
        if not fw.get("available") or not fw.get("url"):
            continue
        valid_plays.append(play)
        idx_str = str(len(valid_plays))
        choices.append(idx_str)

        title = play.get("title", {}).get("zh") or play.get("title", {}).get("en") or "未命名"
        author = play.get("author", "官方")
        size_str = format_size(fw.get("size", 0))
        desc = (play.get("description", {}).get("zh") or "")[:28] + "..."
        table.add_row(idx_str, title, author, size_str, desc)

    console.print(table)
    selected = Prompt.ask("请选择要安装的玩法序号 (0 取消)", choices=["0"] + choices, default="1")
    if selected == "0":
        return

    chosen_play = valid_plays[int(selected) - 1]
    title = chosen_play.get("title", {}).get("zh") or chosen_play.get("title", {}).get("en")
    fw_info = chosen_play["firmware"]
    fw_url = fw_info["url"]
    expected_sha256 = fw_info.get("sha256")

    console.print(f"\n[bold green]已选择：{title}[/bold green]")
    port = select_port_interactive()
    
    console.print("[dim]正在下载官方固件并进行 SHA-256 完整性校验...[/dim]")
    try:
        bin_path = download_firmware(fw_url, expected_sha256)
        console.print(f"[green]✔ 固件下载完成并通过安全校验: {bin_path}[/green]")
    except Exception as e:
        console.print(f"[red]❌ 固件下载失败: {e}[/red]")
        return

    do_flash_job(port, [("0x0", bin_path)], 921600)

def interactive_erase():
    """交互式擦除设备数据"""
    port = select_port_interactive()
    if not Confirm.ask(f"[bold red]确定要彻底擦除设备 {port} 上的所有 Flash 数据吗？此操作不可逆！[/bold red]"):
        return

    console.print("[yellow]正在擦除 Flash，请稍候...[/yellow]")
    success = erase_chip(port, baud=921600, log_callback=lambda l: console.print(f"[dim]{l}[/dim]"))
    if success:
        console.print("[bold green]✔ 设备数据清除完成！[/bold green]")
    else:
        console.print("[bold red]❌ 擦除失败，请检查端口占用或硬件连接状态。[/bold red]")

def do_flash_job(port: str, files_with_offsets, baud: int):
    """执行烧录任务"""
    console.print(f"\n[bold cyan]⚡ 正在同步 Bootloader 并写入固件...[/bold cyan]")
    
    def log_handler(line: str):
        # 美化进度展示
        if "Writing at" in line:
            console.print(f"[cyan]{line}[/cyan]")
        elif "Compressed" in line or "Hash of data verified" in line:
            console.print(f"[green]✔ {line}[/green]")
        elif "Connecting" in line:
            console.print(f"[yellow]{line}[/yellow]")
        else:
            console.print(f"[dim]{line}[/dim]")

    ok = flash_firmware(
        port=port,
        files_with_offsets=files_with_offsets,
        baud=baud,
        log_callback=log_handler
    )

    if ok:
        console.print("\n[bold green]🎉 写入完成！设备已自动重启，可以开始使用。[/bold green]")
    else:
        console.print("\n[bold red]❌ 写入失败，请检查串口权限或设备连接后重试。[/bold red]")

@cli.command("ports")
def list_ports_command():
    """列出当前已连接的串口与设备"""
    ports = scan_ports()
    if not ports:
        console.print("[yellow]未发现任何可用串口设备。[/yellow]")
        return

    table = Table(title="🔌 可用串口列表")
    table.add_column("设备路径", style="green")
    table.add_column("类型", justify="center")
    table.add_column("VID:PID", style="cyan")
    table.add_column("硬件描述", style="white")

    for p in ports:
        vid_pid = f"{p['vid']:04X}:{p['pid']:04X}" if p['vid'] is not None and p['pid'] is not None else "-"
        kind = "[bold green]ESP 设备[/bold green]" if p["is_esp"] else "[dim]串口[/dim]"
        table.add_row(p["device"], kind, vid_pid, p["description"] or "-")

    console.print(table)

@cli.command("flash")
@click.argument("files", nargs=-1, required=False)
@click.option("-p", "--port", default=None, help="指定串口设备路径 (如 /dev/ttyACM0 或 COM3)")
@click.option("-b", "--baud", default=921600, type=int, help="烧录波特率 (默认 921600)")
@click.option("-a", "--addr", default="0x0", help="默认写入地址偏移 (默认 0x0)")
@click.option("-e", "--erase-first", is_flag=True, help="烧录前先擦除设备数据")
def flash_command(files, port, baud, addr, erase_first):
    """
    烧录本地固件文件到设备

    示例:
      folotoy-flasher flash firmware.bin
      folotoy-flasher flash -p /dev/ttyACM0 -b 921600 firmware.bin
      folotoy-flasher flash 0x0:bootloader.bin 0x8000:partitions.bin 0x10000:app.bin
    """
    if not port:
        port = get_recommended_port()
        if not port:
            port = select_port_interactive()
        else:
            console.print(f"[dim]已自动匹配首选 ESP 串口: {port}[/dim]")

    if not files:
        file_path = Prompt.ask("请输入固件文件路径")
        files = [file_path]

    # 解析文件与地址列表
    parsed_files = []
    default_offsets = ["0x0", "0x8000", "0x10000", "0x20000"]
    for i, item in enumerate(files):
        if ":" in item:
            part_addr, part_path = item.split(":", 1)
        else:
            part_addr = addr if i == 0 else (default_offsets[i] if i < len(default_offsets) else "0x0")
            part_path = item
        
        part_path = os.path.expanduser(part_path.strip().strip("'\""))
        if not os.path.isfile(part_path):
            console.print(f"[red]❌ 文件不存在: {part_path}[/red]")
            sys.exit(1)
        parsed_files.append((part_addr, part_path))

    if erase_first:
        console.print("[yellow]正在执行前置 Flash 擦除...[/yellow]")
        erase_chip(port, baud=baud)

    do_flash_job(port, parsed_files, baud)

@cli.command("erase")
@click.option("-p", "--port", default=None, help="指定串口设备路径")
@click.option("-b", "--baud", default=921600, type=int, help="波特率")
def erase_command(port, baud):
    """清除设备数据 (Erase Flash)"""
    if not port:
        port = select_port_interactive()
    
    if Confirm.ask(f"[bold red]确认擦除 {port} 的全部数据吗？[/bold red]"):
        success = erase_chip(port, baud=baud, log_callback=lambda l: console.print(f"[dim]{l}[/dim]"))
        if success:
            console.print("[bold green]✔ 设备数据清除完成！[/bold green]")
        else:
            console.print("[bold red]❌ 擦除失败！[/bold red]")

@cli.command("plays")
def list_plays_command():
    """列出 AI Passport 官方精选玩法"""
    console.print("[dim]正在加载官方精选玩法列表...[/dim]")
    plays = get_recommendations()
    if not plays:
        console.print("[red]❌ 获取列表失败[/red]")
        return

    table = Table(title="🎮 AI Passport 官方玩法")
    table.add_column("玩法 ID / 别名", style="cyan")
    table.add_column("名称", style="bold green")
    table.add_column("作者", style="yellow")
    table.add_column("固件大小", justify="right")

    for play in plays:
        fw = play.get("firmware") or {}
        if not fw.get("available"):
            continue
        title = play.get("title", {}).get("zh") or play.get("title", {}).get("en") or "未命名"
        table.add_row(play.get("slug") or play.get("id"), title, play.get("author", "官方"), format_size(fw.get("size", 0)))

    console.print(table)

def start_web_server(port: int = 8080, open_browser: bool = True):
    """启动本地 Web 刷机服务"""
    import http.server
    import socketserver
    import webbrowser

    web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
    
    class SilentHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_dir, **kwargs)
        def log_message(self, format, *args):
            pass

    console.print(Panel.fit(
        f"[bold cyan]Folotoy Web Flasher (Frosted Glass UI) 已就绪[/bold cyan]\n\n"
        f"本地访问地址: [bold green]http://localhost:{port}[/bold green]\n"
        f"静态文件目录: [dim]{web_dir}[/dim]\n\n"
        f"[yellow]提示：请使用 Chrome / Edge 浏览器打开以支持 Web Serial 串口通信[/yellow]\n"
        f"[dim]按 Ctrl+C 可停止本地服务[/dim]",
        border_style="cyan"
    ))

    if open_browser:
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

    # 允许端口复用
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), SilentHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]Web 刷机服务已停止。[/dim]")
    except Exception as e:
        console.print(f"[red]❌ 启动失败: {e}[/red]")

@cli.command("web")
@click.option("-p", "--port", default=8080, type=int, help="指定本地 Web 端口 (默认 8080)")
@click.option("--no-open", is_flag=True, help="启动时不自动打开浏览器")
def web_command(port, no_open):
    """启动本地 Web 刷机服务 (极简磨砂质感 UI)"""
    start_web_server(port=port, open_browser=not no_open)

if __name__ == "__main__":
    cli()
