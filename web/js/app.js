/**
 * Web Flasher · 本地固件刷机工具
 * 完美集成 Web Serial 与 WebUSB (web-serial-polyfill) 双通道
 * 严格对齐官方原生 12346/4097 (USB JTAG/serial debug unit) 连接协议
 */

import { ESPLoader, Transport, UsbJtagSerialReset, HardReset, ClassicReset } from "./esptool-bundle.js";
import { serial as polyfillSerial } from "./serial-polyfill.js";

let isConnected = false;
let isBusy = false;
let activePort = null;
let transport = null;
let loader = null;
let files = [];

// 官方特定过滤规则 (0x303A: 0x1001 即 12346 / 4097)
const OFFICIAL_FILTERS = [
    { usbVendorId: 12346, usbProductId: 4097 }, // 官方专用 USB JTAG/serial debug unit
    { usbVendorId: 0x303a, usbProductId: 0x1002 }, // ESP32-S3 CDC
    { usbVendorId: 0x303a },                       // 乐鑫 Espressif
    { usbVendorId: 0x10c4 },                       // CP210x
    { usbVendorId: 0x1a86 },                       // CH340 / CH9102
    { usbVendorId: 0x0403 }                        // FTDI
];

// DOM 元素引用
const btnConnect = document.getElementById("btn-connect");
const connectText = document.getElementById("connect-text");
const statusBadge = document.getElementById("status-badge");
const statusText = document.getElementById("status-text");
const compatWarn = document.getElementById("compat-warn");

const filePicker = document.getElementById("file-picker");
const dropArea = document.getElementById("drop-area");
const dropLabel = document.getElementById("drop-label");
const fileList = document.getElementById("file-list");

const baudSelect = document.getElementById("baud-select");
const btnFlash = document.getElementById("btn-flash");
const flashText = document.getElementById("flash-text");
const btnErase = document.getElementById("btn-erase");

const progressBox = document.getElementById("progress-box");
const progressLabel = document.getElementById("progress-label");
const progressVal = document.getElementById("progress-val");
const progressBar = document.getElementById("progress-bar");

const logDetails = document.getElementById("log-details");
const logPre = document.getElementById("log-pre");
const btnClearLog = document.getElementById("btn-clear-log");

function formatKB(bytes) {
    return (bytes / 1024).toFixed(1) + " KB";
}

function appendLog(line) {
    if (!line) return;
    const time = new Date().toLocaleTimeString();
    logPre.textContent += `\n[${time}] ${line}`;
    logPre.scrollTop = logPre.scrollHeight;
}

const terminal = {
    clean() { logPre.textContent = ""; },
    writeLine(data) { appendLog(data); },
    write(data) { if (data && data.trim()) appendLog(data.trim()); }
};

// 获取可用通信引擎 (对标官方双通道探测)
function getSerialEngine() {
    const isAndroid = /Android/i.test(navigator.userAgent) || navigator.userAgentData?.platform === 'Android';
    if (isAndroid && navigator.usb) {
        return { engine: polyfillSerial, type: "webusb" };
    }
    if (navigator.serial) {
        return { engine: navigator.serial, type: "webserial" };
    }
    if (navigator.usb) {
        return { engine: polyfillSerial, type: "webusb" };
    }
    return { engine: null, type: "unsupported" };
}

// 检查环境
function checkEnv() {
    const { type } = getSerialEngine();
    if (type === "unsupported") {
        compatWarn.style.display = "block";
        statusText.textContent = "无串口/USB权限";
    } else {
        compatWarn.style.display = "none";
        statusText.textContent = type === "webusb" ? "WebUSB 模式" : "未连接";
    }
}

// 更新界面状态
function updateUI() {
    if (isConnected) {
        statusBadge.className = "status-indicator connected";
        btnConnect.className = "btn btn-connect connected";
        connectText.textContent = "断开设备";
        baudSelect.disabled = true;
    } else {
        statusBadge.className = "status-indicator";
        btnConnect.className = "btn btn-connect";
        connectText.textContent = isBusy ? "连接中..." : "连接设备";
        const { type } = getSerialEngine();
        statusText.textContent = type === "webusb" ? "WebUSB" : "未连接";
        baudSelect.disabled = false;
    }

    const canFlash = isConnected && files.length > 0 && !isBusy;
    btnFlash.disabled = !canFlash;
    btnErase.disabled = !isConnected || isBusy;
}

// 渲染文件列表
function renderFiles() {
    if (files.length === 0) {
        fileList.style.display = "none";
        dropLabel.textContent = "点击或拖拽本地 .bin 固件";
    } else {
        fileList.style.display = "flex";
        dropLabel.textContent = `已选 ${files.length} 个固件 (点击继续添加)`;
    }

    fileList.innerHTML = "";
    files.forEach((item, idx) => {
        const div = document.createElement("div");
        div.className = "file-item";
        div.innerHTML = `
            <span class="file-name" title="${item.name}">${item.name} (${formatKB(item.size)})</span>
            <input class="file-addr" type="text" value="${item.address}" title="写入地址">
            <button class="file-del" title="移除">✕</button>
        `;

        div.querySelector(".file-addr").addEventListener("change", (e) => {
            item.address = e.target.value.trim();
        });

        div.querySelector(".file-del").addEventListener("click", () => {
            files.splice(idx, 1);
            renderFiles();
            updateUI();
        });

        fileList.appendChild(div);
    });

    updateUI();
}

function getDefaultOffset(idx) {
    return idx === 0 ? "0x0" : idx === 1 ? "0x8000" : idx === 2 ? "0x10000" : "0x0";
}

function handleAddFiles(fileListInput) {
    const remain = Math.max(0, 8 - files.length);
    const added = Array.from(fileListInput).slice(0, remain);
    added.forEach((f) => {
        files.push({
            id: Date.now() + Math.random(),
            file: f,
            name: f.name,
            size: f.size,
            address: getDefaultOffset(files.length)
        });
    });
    renderFiles();
}

// 连接与断开
async function toggleConnection() {
    const { engine, type } = getSerialEngine();
    if (!engine) {
        alert("当前浏览器缺少 Web Serial 或 WebUSB API。\n请在电脑端使用 Google Chrome 或 Microsoft Edge 连接 USB 硬件。");
        return;
    }

    if (isConnected) {
        if (isBusy) return;
        try {
            await transport?.disconnect();
            appendLog("设备已断开连接。");
        } catch (e) {
            appendLog(`断开异常: ${e.message}`);
        } finally {
            isConnected = false;
            transport = null;
            loader = null;
            activePort = null;
            updateUI();
        }
        return;
    }

    try {
        isBusy = true;
        updateUI();
        appendLog(`[${type}] 正在请求选择串口设备 (匹配官方 JTAG 过滤器)...`);

        let portObj = null;
        try {
            // 优先使用官方原版硬件过滤器
            portObj = await engine.requestPort({ filters: OFFICIAL_FILTERS });
        } catch (err) {
            if (err.name === "NotFoundError") {
                appendLog("用户取消了设备选择。");
                isBusy = false;
                updateUI();
                return;
            }
            // 回退尝试：如果带过滤器失败，尝试无过滤模式
            appendLog("尝试以全部设备模式请求...");
            portObj = await engine.requestPort();
        }

        activePort = portObj;
        appendLog("已获取设备权限，正在同步 Bootloader...");
        transport = new Transport(activePort);
        const baud = parseInt(baudSelect.value, 10);

        loader = new ESPLoader({
            transport: transport,
            baudrate: baud,
            terminal: terminal
        });

        const chipName = await loader.main();
        isConnected = true;
        statusText.textContent = chipName || "已连接";
        appendLog(`🎉 设备就绪！识别到芯片: ${chipName}`);
    } catch (e) {
        if (e.name !== "NotFoundError") {
            appendLog(`连接失败: ${e.message || e}`);
        }
        if (transport) await transport.disconnect().catch(() => {});
        isConnected = false;
        transport = null;
        loader = null;
        activePort = null;
    } finally {
        isBusy = false;
        updateUI();
    }
}

// 写入固件
async function startFlash() {
    if (!isConnected || !loader || isBusy || files.length === 0) return;

    isBusy = true;
    flashText.textContent = "写入中...";
    btnFlash.disabled = true;
    progressBox.style.display = "flex";
    progressBar.style.width = "0%";
    progressVal.textContent = "0%";
    progressLabel.textContent = "写入固件...";
    logDetails.open = true;

    try {
        let fileArray = [];
        for (let f of files) {
            const buf = await f.file.arrayBuffer();
            let addr = f.address.trim().toLowerCase();
            let parsedAddr = addr.startsWith("0x") ? parseInt(addr.slice(2), 16) : parseInt(addr, 10);
            fileArray.push({
                data: new Uint8Array(buf),
                address: parsedAddr
            });
        }

        appendLog(`开始写入 ${fileArray.length} 个固件文件...`);

        await loader.writeFlash({
            fileArray: fileArray,
            flashMode: "keep",
            flashFreq: "keep",
            flashSize: "keep",
            eraseAll: false,
            compress: true,
            reportProgress: (idx, written, total) => {
                const pct = Math.min(100, Math.round((written / total) * 100));
                progressBar.style.width = `${pct}%`;
                progressVal.textContent = `${pct}%`;
                progressLabel.textContent = `写入 (${pct}%)`;
            }
        });

        appendLog("写入完成，正在重启设备...");
        progressBar.style.width = "100%";
        progressVal.textContent = "100%";
        progressLabel.textContent = "写入成功！";

        try {
            if (loader.after) {
                await loader.after("hard_reset");
            } else if (loader.isUsbJtagSerialPort && loader.isUsbJtagSerialPort()) {
                const resetSeq = new UsbJtagSerialReset(transport);
                await resetSeq.reset();
            } else {
                const resetSeq = new HardReset(transport);
                await resetSeq.reset();
            }
            appendLog("🎉 设备已成功重启并运行新固件！");
        } catch (resetErr) {
            appendLog(`自动复位提示: ${resetErr.message || resetErr}（固件已烧录成功，如未自启可手动重新插拔或按 RST）`);
        }
    } catch (e) {
        appendLog(`写入异常: ${e.message || e}`);
        progressLabel.textContent = "写入出错";
    } finally {
        isBusy = false;
        flashText.textContent = "开始写入";
        updateUI();
    }
}

// 擦除数据
async function startErase() {
    if (!isConnected || !loader || isBusy) return;
    if (!confirm("确定彻底擦除设备 Flash 吗？此操作不可逆！")) return;

    isBusy = true;
    updateUI();
    logDetails.open = true;
    appendLog("正在清除 Flash 数据...");

    try {
        await loader.eraseFlash();
        appendLog("Flash 擦除完成！");
    } catch (e) {
        appendLog(`擦除失败: ${e.message || e}`);
    } finally {
        isBusy = false;
        updateUI();
    }
}

// 初始化
function init() {
    btnConnect.addEventListener("click", toggleConnection);
    btnFlash.addEventListener("click", startFlash);
    btnErase.addEventListener("click", startErase);

    filePicker.addEventListener("change", (e) => {
        if (e.target.files.length) {
            handleAddFiles(e.target.files);
            e.target.value = "";
        }
    });

    dropArea.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropArea.classList.add("dragover");
    });
    dropArea.addEventListener("dragleave", () => {
        dropArea.classList.remove("dragover");
    });
    dropArea.addEventListener("drop", (e) => {
        e.preventDefault();
        dropArea.classList.remove("dragover");
        if (e.dataTransfer.files.length) {
            handleAddFiles(e.dataTransfer.files);
        }
    });

    if (btnClearLog) {
        btnClearLog.addEventListener("click", () => {
            logPre.textContent = "[system] 就绪";
        });
    }

    const themeBtn = document.getElementById("theme-toggle");
    const savedTheme = localStorage.getItem("flasher_theme");
    if (savedTheme) {
        document.documentElement.setAttribute("data-theme", savedTheme);
    }
    themeBtn.addEventListener("click", () => {
        const cur = document.documentElement.getAttribute("data-theme");
        const next = cur === "dark" ? "light" : "dark";
        document.documentElement.setAttribute("data-theme", next);
        localStorage.setItem("flasher_theme", next);
    });

    checkEnv();
    updateUI();
}

window.addEventListener("DOMContentLoaded", init);
