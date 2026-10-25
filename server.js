const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const url = require('url');

const PORT = process.env.PORT || 4192;
const WEB_DIR = path.join(__dirname, 'web');
const DEFAULT_GITHUB_TOKEN = process.env.GITHUB_TOKEN || "";

const MIME_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.mjs': 'application/javascript; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.bin': 'application/octet-stream',
    '.wasm': 'application/wasm'
};

function parseRepo(repoInput) {
    if (!repoInput) return null;
    let cleaned = repoInput.trim().replace(/\.git\/?$/, '').replace(/\/+$/, '');
    const match = cleaned.match(/(?:github\.com\/)?([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)$/);
    if (match) {
        return { owner: match[1], repo: match[2] };
    }
    return null;
}

// 仅允许从 github.com 及其子域下载，防止代理被滥用为任意 URL 抓取（SSRF）并携带 Token 外泄
function isGithubDownloadUrl(u) {
    try {
        const parsed = url.parse(u);
        const host = (parsed.hostname || '').toLowerCase();
        return parsed.protocol === 'https:' && (host === 'github.com' || host.endsWith('.github.com'));
    } catch (_) {
        return false;
    }
}

function fetchHttps(targetUrl, headers, maxRedirects = 5) {
    return new Promise((resolve, reject) => {
        if (maxRedirects < 0) {
            return reject(new Error('Too many redirects'));
        }

        const parsed = url.parse(targetUrl);
        const reqOptions = {
            hostname: parsed.hostname,
            path: parsed.path,
            port: parsed.port || 443,
            headers: headers,
            method: 'GET'
        };

        const client = parsed.protocol === 'http:' ? http : https;
        const req = client.request(reqOptions, (res) => {
            if ([301, 302, 307, 308].includes(res.statusCode) && res.headers.location) {
                let nextHeaders = { ...headers };
                const nextParsed = url.parse(res.headers.location);
                if (nextParsed.hostname && !nextParsed.hostname.endsWith('github.com')) {
                    delete nextHeaders['Authorization'];
                    delete nextHeaders['authorization'];
                }
                return resolve(fetchHttps(res.headers.location, nextHeaders, maxRedirects - 1));
            }
            resolve(res);
        });

        req.on('error', reject);
        req.end();
    });
}

const server = http.createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', '*');

    if (req.method === 'OPTIONS') {
        res.writeHead(204);
        res.end();
        return;
    }

    const parsedUrl = url.parse(req.url, true);
    const pathname = parsedUrl.pathname;
    const query = parsedUrl.query;

    if (pathname === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok', service: 'folotoy-web-flasher' }));
        return;
    }

    // GitHub Releases API 代理
    if (pathname === '/api/github/releases') {
        const repoParam = query.repo || '';
        const parsed = parseRepo(repoParam);
        if (!parsed) {
            res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify({ ok: false, error: '无效的 GitHub 仓库地址' }));
            return;
        }

        const token = query.token || process.env.GITHUB_TOKEN || DEFAULT_GITHUB_TOKEN;
        const apiUrl = `https://api.github.com/repos/${parsed.owner}/${parsed.repo}/releases`;
        const headers = {
            'User-Agent': 'folotoy-flasher-web',
            'Accept': 'application/vnd.github.v3+json'
        };
        if (token) {
            headers['Authorization'] = `token ${token}`;
        }

        try {
            const apiRes = await fetchHttps(apiUrl, headers);
            apiRes.on('error', () => {
                if (!res.headersSent) {
                    res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
                    res.end(JSON.stringify({ ok: false, error: 'GitHub API 连接中断' }));
                } else {
                    res.destroy();
                }
            });
            let rawData = '';
            apiRes.on('data', chunk => { rawData += chunk; });
            apiRes.on('end', () => {
                if (apiRes.statusCode !== 200) {
                    res.writeHead(apiRes.statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
                    res.end(JSON.stringify({ ok: false, error: `GitHub API 响应 ${apiRes.statusCode}` }));
                    return;
                }
                try {
                    const list = JSON.parse(rawData);
                    const formatted = list.map(rel => {
                        const rawAssets = rel.assets || [];
                        const assets = rawAssets.map(a => ({
                            id: a.id,
                            name: a.name,
                            size: a.size,
                            download_url: a.browser_download_url,
                            is_bin: (a.name || '').toLowerCase().endsWith('.bin')
                        }));
                        return {
                            id: rel.id,
                            tag_name: rel.tag_name || 'untagged',
                            title: rel.name || rel.tag_name,
                            published_at: (rel.published_at || '').slice(0, 10),
                            prerelease: rel.prerelease || false,
                            assets: assets,
                            bin_count: assets.filter(a => a.is_bin).length,
                            total_count: assets.length
                        };
                    });
                    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
                    res.end(JSON.stringify({ ok: true, releases: formatted }));
                } catch (err) {
                    res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
                    res.end(JSON.stringify({ ok: false, error: '解析 GitHub 返回数据失败' }));
                }
            });
        } catch (e) {
            res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify({ ok: false, error: e.message }));
        }
        return;
    }

    // GitHub 固件下载代理
    if (pathname === '/api/github/download') {
        const downloadUrl = query.url;
        const filename = query.filename || 'firmware.bin';
        const token = query.token || process.env.GITHUB_TOKEN || DEFAULT_GITHUB_TOKEN;

        if (!downloadUrl) {
            res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify({ ok: false, error: '缺少固件下载地址' }));
            return;
        }
        if (!isGithubDownloadUrl(downloadUrl)) {
            res.writeHead(400, { 'Content-Type': 'application/json; charset=utf-8' });
            res.end(JSON.stringify({ ok: false, error: '仅支持从 github.com 下载固件' }));
            return;
        }

        const headers = { 'User-Agent': 'folotoy-flasher-web' };
        if (token) headers['Authorization'] = `token ${token}`;

        try {
            const dlRes = await fetchHttps(downloadUrl, headers);
            if (dlRes.statusCode !== 200) {
                res.writeHead(dlRes.statusCode, { 'Content-Type': 'application/json; charset=utf-8' });
                res.end(JSON.stringify({ ok: false, error: `下载失败 HTTP ${dlRes.statusCode}` }));
                return;
            }

            // 中途网络错误不能成为未捕获异常（否则整个进程退出）
            dlRes.on('error', () => { res.destroy(); });
            res.on('error', () => { dlRes.destroy(); });
            res.writeHead(200, {
                'Content-Type': 'application/octet-stream',
                'Content-Disposition': `attachment; filename="${encodeURIComponent(filename)}"`
            });
            dlRes.pipe(res);
        } catch (e) {
            if (!res.headersSent) {
                res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' });
                res.end(JSON.stringify({ ok: false, error: e.message }));
            } else {
                res.destroy();
            }
        }
        return;
    }

    let reqPath = decodeURI(pathname);
    if (reqPath === '/' || reqPath === '') {
        reqPath = '/index.html';
    }

    let filePath = path.join(WEB_DIR, reqPath);

    // 必须带路径分隔符做前缀比较，否则 "..%sibling" 这类同级目录（如 web2/）会绕过检查
    if (filePath !== WEB_DIR && !filePath.startsWith(WEB_DIR + path.sep)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
    }

    fs.stat(filePath, (err, stats) => {
        if (err) {
            res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
            res.end('404 Not Found');
            return;
        }

        if (stats.isDirectory()) {
            const indexPath = path.join(filePath, 'index.html');
            if (fs.existsSync(indexPath)) {
                filePath = indexPath;
            } else {
                res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
                res.end('404 Not Found');
                return;
            }
        }

        const ext = path.extname(filePath).toLowerCase();
        const contentType = MIME_TYPES[ext] || 'application/octet-stream';

        res.writeHead(200, {
            'Content-Type': contentType,
            'Cache-Control': 'no-cache, must-revalidate'
        });

        fs.createReadStream(filePath).pipe(res);
    });
});

server.listen(PORT, '0.0.0.0', () => {
    console.log(`Folotoy Web Flasher running at http://0.0.0.0:${PORT}`);
});
