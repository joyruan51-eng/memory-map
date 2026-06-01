# 「记忆地图」公网部署教程（Vercel + Railway 小白版）

目标网址：

```text
https://你的项目.vercel.app
```

这份项目不是纯静态网页。它已经有账号、密码、SQLite 数据库和图片上传，所以要分成两部分部署：

| 部分 | 平台 | 作用 |
| --- | --- | --- |
| 网页前端 | Vercel | 打开页面、显示地图、登录表单 |
| 数据接口 | Railway | 保存账号、记忆、图片、数据库 |
| 数据持久化 | Railway Volume | 防止重启后数据库和图片丢失 |

## 1. 准备账号和软件

需要：

- GitHub 账号
- Vercel 账号，可以用 GitHub 登录
- Railway 账号，可以用 GitHub 登录
- Git
- Node.js LTS

官方入口：

- GitHub: https://github.com/
- Vercel: https://vercel.com/
- Railway: https://railway.com/
- Node.js: https://nodejs.org/
- Git: https://git-scm.com/

## 2. 上传项目到 GitHub

进入项目目录：

```powershell
cd C:\Users\76619\Documents\Codex\2026-05-31\20\outputs\memory-map
```

初始化并提交：

```powershell
git init
git add .
git commit -m "first upload"
```

去 GitHub 新建仓库，名字建议：

```text
memory-map
```

GitHub 会给你类似下面的命令，复制执行：

```powershell
git remote add origin https://github.com/你的用户名/memory-map.git
git branch -M main
git push -u origin main
```

注意：`.gitignore` 已经排除了 `data/`，本地数据库和图片不会上传到 GitHub。

## 3. 先部署 Railway 后端

1. 打开 Railway。
2. New Project。
3. Deploy from GitHub repo。
4. 选择 `memory-map` 仓库。
5. Railway 会识别 `Dockerfile` 并部署 Python 后端。

部署完成后，进入服务设置：

1. 打开 Settings。
2. 找到 Public Networking。
3. Generate Domain。
4. 你会得到类似：

```text
https://memory-map-production.up.railway.app
```

打开下面地址测试：

```text
https://你的Railway域名/api/health
```

如果看到：

```json
{"ok": true, "service": "memory-map"}
```

说明后端成功。

## 4. 给 Railway 加持久化 Volume

如果不加 Volume，Railway 重启后 SQLite 和图片可能丢失。

在 Railway 项目里：

1. 打开你的服务。
2. 找到 Volumes。
3. Add Volume。
4. Mount Path 填：

```text
/app/data
```

项目里的 `Dockerfile` 已经默认使用：

```text
MEMORY_MAP_DATA_DIR=/app/data
```

所以数据库会保存到：

```text
/app/data/memory-map.sqlite3
```

图片会保存到：

```text
/app/data/uploads
```

## 5. 设置 Railway 环境变量

在 Railway 服务的 Variables 里添加：

```text
MEMORY_MAP_DATA_DIR=/app/data
MEMORY_MAP_COOKIE_SECURE=1
```

如果你后面不用 Vercel 代理，而是让前端直接请求 Railway，再加：

```text
MEMORY_MAP_ALLOWED_ORIGINS=https://你的项目.vercel.app
MEMORY_MAP_COOKIE_SAMESITE=None
```

本教程默认使用 Vercel 代理，所以通常只需要前两个变量。

## 6. 修改 Vercel 代理地址

打开项目里的：

```text
vercel.json
```

把这一段：

```json
"destination": "https://REPLACE_WITH_YOUR_RAILWAY_DOMAIN.up.railway.app/api/:path*"
```

改成你的 Railway 域名，例如：

```json
"destination": "https://memory-map-production.up.railway.app/api/:path*"
```

然后提交并推送：

```powershell
git add .
git commit -m "configure railway api"
git push
```

## 7. 部署 Vercel 前端

1. 打开 Vercel。
2. Add New Project。
3. 选择 GitHub 里的 `memory-map`。
4. Framework Preset 选择 Other 或保持默认。
5. Build Command 留空。
6. Output Directory 留空。
7. Deploy。

部署完成后，会得到：

```text
https://你的项目.vercel.app
```

打开后注册账号，新增一条记忆，再刷新页面。如果数据还在，说明 Vercel + Railway 已连通。

## 8. 常见问题

### 登录后刷新又退出

检查：

- `vercel.json` 的 Railway 地址是否正确。
- Railway 变量里是否有 `MEMORY_MAP_COOKIE_SECURE=1`。
- Vercel 是否重新部署了最新代码。

### 注册时报接口错误

先打开：

```text
https://你的Railway域名/api/health
```

如果这个都打不开，说明 Railway 后端没部署好。

### 上传图片后图片没了

检查 Railway Volume 是否挂载到了：

```text
/app/data
```

### 地图瓦片加载慢

当前项目用的是公开地图瓦片源。正式长期使用时，可以换成高德、Mapbox 或其他带 Key 的地图服务。

## 9. 官方文档

- Vercel Rewrites: https://vercel.com/docs/rewrites
- Railway Dockerfile: https://docs.railway.com/guides/dockerfiles
- Railway Volumes: https://docs.railway.com/guides/volumes
