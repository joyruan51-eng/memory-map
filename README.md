# 记忆地图

这是一个带账号、SQLite 数据库、图片上传和 PWA 安装能力的个人记忆地图。

## 本机启动

```powershell
cd C:\Users\76619\Documents\Codex\2026-05-31\20\outputs\memory-map
.\start-server.ps1
```

浏览器打开：

```text
http://127.0.0.1:8765
```

## 公网访问

已经安装了 `cloudflared`。运行：

```powershell
.\start-public.ps1
```

脚本会启动本地服务，并通过 Cloudflare Tunnel 生成一个 HTTPS 公网地址。最新地址会写入：

```text
PUBLIC_URL.txt
```

停止公网访问：

```powershell
.\stop-public.ps1
```

注意：
- 这台电脑必须保持开机和联网。
- 免费 quick tunnel 地址是临时的，重启隧道后可能变化。
- 任何拿到地址的人都能打开注册页，临时公网环境里不要保存敏感隐私数据。

## 永久公网部署

推荐使用：

- 前端：Vercel
- 后端和数据库：Railway
- 数据持久化：Railway Volume

详细步骤见：

```text
DEPLOYMENT_GUIDE.md
```

## 账号和数据

- 注册账号后会自动生成示例记忆。
- 每个账号只能看到自己的记忆。
- 数据保存在 `data/memory-map.sqlite3`。
- 图片保存在 `data/uploads`，数据库里记录图片地址。
- 密码使用 PBKDF2-SHA256 加盐哈希保存。

## 添加图片

进入“新增记忆”或“编辑记忆”，在“照片”一栏选择图片，保存后会显示在详情照片区。当前支持一次选择多张图片，单张建议 5MB 以内。

## 手机安装

页面已包含 PWA manifest 和 service worker。使用 HTTPS 公网地址打开后，手机浏览器通常可以通过菜单添加到主屏幕。
