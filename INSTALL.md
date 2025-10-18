# Clash 订阅管理系统 - 一键安装脚本

## 📦 快速安装

### 一键安装命令

```bash
curl -fsSL https://raw.githubusercontent.com/yourusername/clashshare/main/install.sh | sudo bash
```

或者下载后执行：

```bash
wget https://raw.githubusercontent.com/yourusername/clashshare/main/install.sh
chmod +x install.sh
sudo ./install.sh
```

## 🎯 功能特性

- ✅ 自动检测并安装系统依赖
- ✅ 一键安装/更新/卸载
- ✅ 自动配置 systemd 服务
- ✅ 支持自定义端口
- ✅ 重置管理员密码
- ✅ 数据库自动备份
- ✅ 完整的服务管理

## 📋 系统要求

### 支持的系统

- Ubuntu 18.04+
- Debian 10+
- CentOS 7+
- RHEL 7+
- Fedora 30+

### 最低要求

- Python 3.8+
- 512MB 内存
- 1GB 磁盘空间
- Root 权限

## 🚀 使用指南

### 交互式菜单

直接运行脚本会显示交互式菜单：

```bash
sudo ./install.sh
```

菜单选项：
```
1) 安装
2) 更新
3) 卸载
4) 重置管理员密码
5) 修改端口
6) 查看状态
7) 启动服务
8) 停止服务
9) 重启服务
0) 退出
```

### 命令行模式

也可以直接使用命令行参数：

```bash
# 安装
sudo ./install.sh install

# 更新
sudo ./install.sh update

# 卸载
sudo ./install.sh uninstall
```

## 📝 详细操作说明

### 1️⃣ 安装

执行安装后，脚本会：

1. 检测系统环境
2. 自动安装缺失的依赖（Python3, pip3, git）
3. 从 GitHub 克隆项目代码
4. 安装 Python 依赖包
5. 提示设置运行端口（默认 5000）
6. 初始化数据库
7. 创建 systemd 服务
8. 启动服务

**安装完成后会显示：**
- 访问地址
- 默认账号：`admin`
- 默认密码：`admin123`

⚠️ **请立即登录并修改默认密码！**

### 2️⃣ 更新

更新功能会：

1. 停止当前运行的服务
2. 备份数据库
3. 从 GitHub 拉取最新代码
4. 更新 Python 依赖
5. 保持原有端口配置
6. 重启服务

**数据不会丢失**，数据库文件会自动保留。

### 3️⃣ 卸载

卸载时会询问：

- 是否保留数据库文件（可选择备份到 `/root/` 目录）
- 确认是否继续卸载

卸载会删除：
- 安装目录（`/opt/clashshare`）
- systemd 服务配置
- 不会删除系统依赖（Python、git 等）

### 4️⃣ 重置管理员密码

重置密码功能：

1. 停止服务
2. 备份数据库
3. 提示输入新的用户名和密码
4. 删除所有旧管理员账号
5. 创建新管理员账号
6. 重启服务

### 5️⃣ 修改端口

修改端口功能：

1. 显示当前端口
2. 提示输入新端口（1-65535）
3. 更新 systemd 服务配置
4. 重启服务

## 🔧 服务管理

### systemd 命令

```bash
# 启动服务
sudo systemctl start clashshare

# 停止服务
sudo systemctl stop clashshare

# 重启服务
sudo systemctl restart clashshare

# 查看状态
sudo systemctl status clashshare

# 查看日志
sudo journalctl -u clashshare -f

# 开机自启
sudo systemctl enable clashshare

# 禁用自启
sudo systemctl disable clashshare
```

## 📂 文件位置

```
/opt/clashshare/              # 安装目录
├── app.py                    # 主程序
├── models.py                 # 数据模型
├── requirements.txt          # Python依赖
├── clash_manager.db          # 数据库文件
├── .port                     # 端口配置
└── ...                       # 其他文件

/etc/systemd/system/clashshare.service  # systemd服务配置
```

## 🔍 故障排查

### 服务无法启动

```bash
# 查看服务状态
sudo systemctl status clashshare

# 查看详细日志
sudo journalctl -u clashshare -n 50

# 检查端口占用
sudo netstat -tlnp | grep <端口号>

# 手动启动测试
cd /opt/clashshare
sudo python3 app.py
```

### 端口被占用

```bash
# 查看占用端口的进程
sudo lsof -i :<端口号>

# 或使用 netstat
sudo netstat -tlnp | grep <端口号>

# 修改为其他端口
sudo ./install.sh
# 选择选项 5) 修改端口
```

### 依赖安装失败

```bash
# 手动安装依赖
sudo apt-get update  # Ubuntu/Debian
sudo apt-get install -y python3 python3-pip git

sudo yum install -y python3 python3-pip git  # CentOS/RHEL

# 安装Python依赖
cd /opt/clashshare
sudo pip3 install -r requirements.txt
```

### 数据库损坏

```bash
# 使用备份恢复
cd /opt/clashshare
sudo cp clash_manager.db.backup.XXXXXX clash_manager.db
sudo systemctl restart clashshare

# 或删除数据库重新初始化
cd /opt/clashshare
sudo rm clash_manager.db
sudo python3 -c "from app import init_db; init_db()"
sudo systemctl restart clashshare
```

## 🔒 安全建议

1. **修改默认密码**：安装后立即修改默认的管理员密码
2. **防火墙配置**：只开放必要的端口
   ```bash
   # UFW (Ubuntu)
   sudo ufw allow 5000/tcp
   sudo ufw enable
   
   # firewalld (CentOS)
   sudo firewall-cmd --permanent --add-port=5000/tcp
   sudo firewall-cmd --reload
   ```
3. **使用反向代理**：建议使用 Nginx 作为反向代理并配置 HTTPS
4. **定期备份**：定期备份数据库文件
5. **更新系统**：保持系统和软件包更新

## 🔄 更新日志

查看项目的 [CHANGELOG.md](CHANGELOG.md) 获取详细更新信息。

## 📞 获取帮助

- 🐛 报告问题：[GitHub Issues](https://github.com/yourusername/clashshare/issues)
- 📖 文档：[项目 Wiki](https://github.com/yourusername/clashshare/wiki)
- 💬 讨论：[GitHub Discussions](https://github.com/yourusername/clashshare/discussions)

## 📄 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

**注意**：请将上述所有的 `yourusername/clashshare` 替换为您的实际 GitHub 仓库地址。

