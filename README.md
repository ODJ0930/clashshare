# Clash Meta 订阅管理系统

一个简单而强大的工具，用于将各种代理协议订阅转换为 Clash Meta 配置文件。
![示例图片](https://github.com/ODJ0930/clashshare/blob/main/example/4f0af236-ae40-4366-81d4-3440555b23c0.png?raw=true)

## 🆕 现在包含 Web 管理界面！

**v2.0 新增功能**：
- 🌐 完整的 Web 管理界面
- 👤 用户管理系统（支持多用户共享订阅）
- 📡 订阅自动更新
- 🔗 独立的用户订阅接口
- 📝 配置模板管理
- 🔗 链式代理支持
- 🔢 节点自定义排序
- 🔄 节点多分组支持（一个节点可同时属于多个分组）

---

## 📦 系统要求

- **Python**: 3.7 或更高版本
- **操作系统**: Windows / Linux / macOS
- **网络**: 能够访问机场订阅链接

---

## 🚀 快速开始

### 第一步：安装 Python

#### Windows

1. 访问 [Python官网](https://www.python.org/downloads/) 下载 Python
2. 运行安装程序，**务必勾选** "Add Python to PATH"
3. 验证安装：
```bash
python --version
# 应该显示: Python 3.x.x
```

#### Linux (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install python3 python3-pip
python3 --version
```

#### macOS

```bash
# 使用 Homebrew 安装
brew install python3
python3 --version
```

### 第二步：下载项目

```bash
# 方法1: 使用 git clone（推荐）
git clone https://github.com/ODJ0930/clashshare.git
cd dychange

# 方法2: 下载 ZIP 文件后解压
# 然后在命令行中进入项目目录
cd dychange
```

### 第三步：安装依赖

在项目目录下运行：

```bash
# Windows
pip install -r requirements.txt

# Linux/macOS
pip3 install -r requirements.txt

# 如果提示权限错误，使用
pip install --user -r requirements.txt
```

**常见依赖说明：**
- `Flask`: Web 框架
- `Flask-SQLAlchemy`: 数据库 ORM
- `requests`: HTTP 请求库
- `PyYAML`: YAML 配置文件处理

### 第四步：启动 Web 管理界面

```bash
# Windows 用 Python 启动
python app.py

# Linux/macOS用 Python 启动
python3 app.py
```

### 第五步：访问管理界面

启动成功后，在浏览器中打开：

```
http://127.0.0.1:5000
```

**默认登录信息：**
- 用户名: `admin`
- 密码: `admin123`

⚠️ **重要**：首次登录后请立即修改密码！

---

## 📖 快速使用指南

### 1. 添加订阅分组
1. 点击"订阅管理"
2. 点击"创建分组"
3. 输入分组名称（如：香港节点）

### 2. 批量导入节点
1. 点击"节点管理"
2. 点击"批量导入"
3. 粘贴机场订阅链接
4. 选择归属分组
5. 点击"开始导入"

### 3. 创建用户
1. 点击"用户管理"
2. 点击"添加用户"
3. 输入用户名称和备注
4. 点击"管理订阅"为用户分配订阅

### 4. 获取用户订阅链接
在用户列表中复制订阅链接，导入到 Clash 客户端即可使用。

---

## 🛠️ 故障排除

### 问题1：提示 "No module named 'xxx'"

**解决方法：**
```bash
# 重新安装依赖
pip install -r requirements.txt --upgrade
```

### 问题2：端口被占用

**错误信息：** `Address already in use`

**解决方法：**
```bash
# Windows - 查找占用 5000 端口的进程
netstat -ano | findstr :5000
taskkill /PID <进程ID> /F

# Linux/macOS
lsof -i :5000
kill -9 <PID>

# 或修改端口（在 app.py 最后一行）
app.run(debug=True, host='0.0.0.0', port=5001)  # 改为其他端口
```

### 问题3：数据库错误

**解决方法：**
```bash
# 备份数据库（如果有重要数据）
copy instance\clash_manager.db instance\clash_manager.db.backup

# 重置数据库
python reset_database.py

# 或删除数据库重新初始化
del instance\clash_manager.db  # Windows
rm instance/clash_manager.db   # Linux/macOS

# 重新启动应用
python app.py
```

### 问题4：无法访问 Web 界面

**检查步骤：**
1. 确认应用已启动（控制台显示"Running on..."）
2. 检查防火墙是否拦截
3. 尝试使用 `http://localhost:5000` 而不是 127.0.0.1
4. 确认浏览器没有使用代理

---

## 支持的协议

- Shadowsocks (SS)
- ShadowsocksR (SSR)
- VMess
- VLESS (包括 Reality)
- Hysteria2
- Trojan
- HTTP/HTTPS
- SOCKS4/SOCKS5

## ✨ 功能特性

### Web 管理功能
- 🌐 **图形化界面**：友好的 Web 管理界面
- 👤 **多用户管理**：多个用户可以共享同一个订阅
- 📡 **订阅管理**：支持创建订阅分组，批量管理节点
- 🔗 **独立订阅**：每个用户有独立的订阅链接
- 📝 **模板管理**：自定义 Clash 配置模板
- 🔗 **链式代理**：支持创建多级代理节点
- 🔢 **节点排序**：自定义节点在订阅中的输出顺序
- ✏️ **节点编辑**：手动创建或编辑节点配置

### 协议支持
- ✅ 支持多种主流代理协议（见上方列表）
- ✅ 自动解析订阅链接和单节点分享链接
- ✅ 国内外智能分流（中国直连，国外走代理）
- ✅ 生成适配 Clash Meta 的配置文件
- ✅ 支持自定义配置选项

---

## 💻 命令行模式（可选）

如果你只想使用命令行转换订阅，无需启动 Web 界面：

### 基本用法

```bash
# 从订阅链接转换
python converter.py --url "https://your-subscription-url" --output clash_config.yaml

# 从本地文件读取订阅
python converter.py --file subscription.txt --output clash_config.yaml

# 混合模式：既有订阅又有单节点
python converter.py --url "https://sub-url" --nodes "vmess://xxx" "ss://yyy" --output config.yaml
```

### 参数说明

- `--url`: 订阅链接 URL
- `--file`: 本地订阅文件路径
- `--nodes`: 单个节点分享链接（可以多个）
- `--output`: 输出的 YAML 配置文件路径（默认：clash_config.yaml）
- `--proxy-group`: 代理组名称（默认：🚀 节点选择）

## 配置说明

生成的配置文件包含以下分流规则：

- 🎯 **国内直连**：中国大陆的域名和 IP 直接连接
- 🚀 **代理访问**：国外网站通过代理访问
- 📺 **流媒体优化**：常见流媒体平台规则
- 🛑 **广告拦截**：拦截常见广告域名

## 示例

### 输入订阅内容示例

```
vmess://eyJ2IjoiMiIsInBzIjoi5rWL6K+V6IqC54K5IiwiYWRkIjoiZXhhbXBsZS5jb20iLCJwb3J0IjoiNDQzIiwiaWQiOiJ1dWlkLXN0cmluZyIsImFpZCI6IjAiLCJuZXQiOiJ3cyIsInR5cGUiOiJub25lIiwiaG9zdCI6ImV4YW1wbGUuY29tIiwicGF0aCI6Ii9wYXRoIiwidGxzIjoidGxzIn0=
ss://YWVzLTI1Ni1nY206cGFzc3dvcmRAMTkyLjE2OC4xLjE6ODM4OA==#测试节点
```

### 输出配置示例

生成的 YAML 配置文件将包含完整的 Clash Meta 配置结构。

---

## 📚 更多文档

- [启动说明.md](启动说明.md) - 详细的启动和配置说明
- [QUICKSTART.md](QUICKSTART.md) - 快速入门指南
- [WEB_功能说明.md](WEB_功能说明.md) - Web 功能详解

---

## ⚠️ 注意事项

1. **安全性**：
   - 首次登录后务必修改默认密码
   - 不要与他人分享管理员账号
   - 定期备份数据库文件 `instance/clash_manager.db`

2. **网络要求**：
   - 批量导入时需要能够访问机场订阅链接
   - 用户访问订阅时需要能够访问你的服务器

3. **Clash 兼容性**：
   - 生成的配置文件适用于 Clash Meta 核心
   - 建议使用最新版本的 Clash Meta 客户端

4. **性能优化**：
   - 建议定期清理无用节点
   - 大量节点时可以使用订阅分组分类管理

---

## 🔄 更新日志

### v2.1 (2025-10-09)
- ✅ 新增节点自定义排序功能
- ✅ 修复多用户共享订阅的问题
- ✅ 优化前端界面显示
- ✅ 增强自动刷新功能

### v2.0
- ✅ 完整的 Web 管理界面
- ✅ 多用户管理系统
- ✅ 配置模板功能
- ✅ 链式代理支持

---

## 📞 支持

如果遇到问题：
1. 查看上方的"故障排除"章节
2. 查看详细文档 [启动说明.md](启动说明.md)
3. 检查控制台错误信息

---

## 📄 许可证

MIT License

