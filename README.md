# Folotoy AI Passport 本地固件刷机 CLI 工具 (folotoy-flasher)

本项目移植自 [Folotoy AI Passport Web Flasher](https://ai-passport.folotoy.cn/tools/web-flasher/)，将原先在网页端通过 Web Serial 刷写 ESP 芯片固件的功能，完整迁移为本地命令行 CLI 工具。

不仅去除了浏览器权限拦截、弹窗限制以及驱动不稳定问题，还增加了**自动识别 ESP 端口**、**分卷自定义烧录**、**整片 Flash 擦除**及**官方精选玩法一键拉取**等功能。

---

## 🚀 核心特性

1. **安装本地固件（对标网页端）**：
   - 支持单个合并固件（Factory Image，默认写入起始地址 `0x0`）。
   - 支持多分卷文件映射（例如 `0x0:bootloader.bin 0x8000:partition-table.bin 0x10000:app.bin`）。
   - 支持压缩传输（`-z` / `compress: true`）、保留 Flash 参数（`keep`）、烧录完成后自动硬复位（`hard_reset`）。
2. **智能端口发现**：
   - 自动扫描连接的串口，根据 VID/PID 和驱动特征优先匹配 ESP32、USB JTAG / Serial Debug Unit、CH340、CP210x 设备。
3. **清除设备数据（Erase Flash）**：
   - 一键彻底擦除设备存储，解决启动报错或分区异常问题。
4. **官方精选玩法同步（附加特性）**：
   - 对接 `ai-passport.folotoy.cn` 官方 API，查看最新玩法并带 SHA-256 完整性校验下载刷入。
5. **两种使用方式**：
   - **交互式 TUI**：直接输入 `folotoy-flasher` 开启图形化菜单引导。
   - **直通命令**：适合自动化脚本或一键运行。

---

## 📦 安装与配置

本项目位于 `/home/ubuntu/folotoy-flasher-cli`。

### 1. 以可编辑模式安装到全局环境
```bash
cd /home/ubuntu/folotoy-flasher-cli
pip install -e .
```
安装完成后，可在任意路径直接使用 `folotoy-flasher` 命令。

---

## 🛠 使用说明

### 1. 交互式模式（推荐小白使用）
```bash
folotoy-flasher
```
系统会弹出图形化菜单，自动扫描串口，引导你选择固件文件、设置地址并开始烧录。

### 3. Web 网页刷机模式 (现代极简磨砂质感 UI)
本项目内置了**极简磨砂质感 WebUI**（界面风格汲取自 [Level6me/Abit](https://github.com/Level6me/Abit)）：
```bash
folotoy-flasher web
# 或指定端口:
folotoy-flasher web -p 8080
```
启动后可在 Chrome / Edge 浏览器中直接打开 `http://localhost:8080`，通过 Web Serial 原生串口交互、实时日志、精选玩法一键下载及多分区文件拖拽烧录！

静态页面目录位于 `/home/ubuntu/folotoy-flasher-web`（或 `/home/ubuntu/folotoy-flasher-cli/web`），支持直接通过 Nginx / 静态文件服务器托管部署。

---

## 🛠 命令行直通说明

#### 刷入单个本地固件（默认从 0x0 写入，自动寻找 ESP 端口）：
```bash
folotoy-flasher flash /path/to/firmware.bin
```

#### 指定串口和波特率：
```bash
folotoy-flasher flash -p /dev/ttyACM0 -b 115200 /path/to/firmware.bin
```

#### 刷入前先彻底擦除设备（Erase First）：
```bash
folotoy-flasher flash -e /path/to/firmware.bin
```

#### 刷入多分卷固件：
```bash
folotoy-flasher flash 0x0:bootloader.bin 0x8000:partitions.bin 0x10000:app.bin
```

#### 独立清除设备数据：
```bash
folotoy-flasher erase
# 或指定端口
folotoy-flasher erase -p /dev/ttyACM0
```

#### 查看已连接的串口列表：
```bash
folotoy-flasher ports
```

#### 查看官方精选玩法列表：
```bash
folotoy-flasher plays
```

#### 从 GitHub 仓库拉取固件：
```bash
# 交互式选择 Release 版本与固件并刷机
folotoy-flasher github
folotoy-flasher github wled/WLED
folotoy-flasher github https://github.com/wled/WLED

# 仅列出该仓库所有 Release 及包含的 .bin 固件：
folotoy-flasher github wled/WLED -l

# 指定端口、波特率并先擦除后刷入：
folotoy-flasher github wled/WLED -p /dev/ttyACM0 -b 921600 -e
```

---

## 📄 网页端逻辑与本工具映射表

| 网页端功能 / 参数 | Web Flasher 实现 | 本工具 (CLI) 实现 |
| :--- | :--- | :--- |
| 设备连接 | Web Serial API (`navigator.serial.requestPort`) | `serial.tools.list_ports` 自动识别 |
| 芯片探测 | `esptool-js` -> `loader.main()` | `esptool` auto-detect |
| 固件写入 | `loader.writeFlash(...)` | `esptool write_flash -z` |
| 波特率 | 默认 921600 | 默认 921600（支持 `-b` 自由配置）|
| Flash 模式 | `flashMode: 'keep'` | `--flash_mode keep` |
| 重启设备 | `hardReset(transport)` | `--after hard_reset` |
| 清除数据 | `eraseAll: true` | `folotoy-flasher erase` |
