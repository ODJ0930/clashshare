#!/bin/bash

# Clash订阅管理系统 - 一键安装脚本
# 适用于 Linux 系统

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置变量
INSTALL_DIR="/opt/clashshare"
SERVICE_NAME="clashshare"
DEFAULT_PORT=5000
GITHUB_REPO="https://github.com/ODJ0930/clashshare.git"
PYTHON_MIN_VERSION="3.8"

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示横幅
show_banner() {
    clear
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════╗"
    echo "║                                                           ║"
    echo "║          Clash 订阅管理系统 - 一键安装脚本                ║"
    echo "║                                                           ║"
    echo "╚═══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 检查是否为root用户
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "此脚本需要root权限运行"
        print_info "请使用 sudo 运行此脚本：sudo bash $0"
        exit 1
    fi
}

# 检测系统信息
detect_system() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    else
        print_error "无法检测系统信息"
        exit 1
    fi
    
    print_info "检测到系统: $OS $OS_VERSION"
}

# 检查Python版本
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version | awk '{print $2}')
        print_info "检测到 Python 版本: $PYTHON_VERSION"
        
        # 检查Python版本是否满足最低要求
        if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
            return 0
        else
            print_warning "Python 版本过低，需要 $PYTHON_MIN_VERSION 或更高版本"
            return 1
        fi
    else
        return 1
    fi
}

# 检查pip
check_pip() {
    if command -v pip3 &> /dev/null; then
        print_info "检测到 pip3"
        return 0
    else
        return 1
    fi
}

# 检查git
check_git() {
    if command -v git &> /dev/null; then
        print_info "检测到 git"
        return 0
    else
        return 1
    fi
}

# 安装依赖
install_dependencies() {
    print_info "正在安装系统依赖..."
    
    case $OS in
        ubuntu|debian)
            apt-get update
            apt-get install -y python3 python3-pip git curl wget
            ;;
        centos|rhel|fedora)
            yum install -y python3 python3-pip git curl wget
            ;;
        *)
            print_error "不支持的系统: $OS"
            exit 1
            ;;
    esac
    
    print_success "系统依赖安装完成"
}

# 检查并安装所有依赖
check_and_install_dependencies() {
    print_info "检查系统依赖..."
    
    local need_install=0
    
    if ! check_python; then
        print_warning "未检测到 Python 3.8+，需要安装"
        need_install=1
    fi
    
    if ! check_pip; then
        print_warning "未检测到 pip3，需要安装"
        need_install=1
    fi
    
    if ! check_git; then
        print_warning "未检测到 git，需要安装"
        need_install=1
    fi
    
    if [[ $need_install -eq 1 ]]; then
        print_info "需要安装缺失的依赖"
        read -p "是否继续安装？[Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            install_dependencies
        else
            print_error "用户取消安装"
            exit 1
        fi
    else
        print_success "所有系统依赖已满足"
    fi
}

# 下载/更新项目文件
download_project() {
    print_info "正在下载/更新项目文件..."
    
    if [[ -d "$INSTALL_DIR" ]]; then
        print_info "检测到已存在的安装目录，正在更新..."
        cd "$INSTALL_DIR"
        
        # 备份配置文件
        if [[ -f "clash_manager.db" ]]; then
            print_info "备份数据库..."
            cp clash_manager.db clash_manager.db.backup.$(date +%Y%m%d_%H%M%S)
        fi
        
        # 更新代码
        git fetch origin
        git reset --hard origin/main
        print_success "项目更新完成"
    else
        print_info "正在克隆项目..."
        git clone "$GITHUB_REPO" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
        print_success "项目下载完成"
    fi
}

# 安装Python依赖
install_python_dependencies() {
    print_info "正在安装Python依赖..."
    cd "$INSTALL_DIR"
    
    if [[ -f "requirements.txt" ]]; then
        # 尝试正常安装
        if pip3 install -r requirements.txt 2>/dev/null; then
            print_success "Python依赖安装完成"
        else
            # 如果失败，尝试使用 --break-system-packages（Debian 12+, Ubuntu 23.04+）
            print_warning "检测到系统包管理限制，使用 --break-system-packages 参数"
            pip3 install -r requirements.txt --break-system-packages
            print_success "Python依赖安装完成"
        fi
    else
        print_error "未找到 requirements.txt 文件"
        exit 1
    fi
}

# 设置端口
setup_port() {
    local current_port=$1
    
    if [[ -z "$current_port" ]]; then
        current_port=$DEFAULT_PORT
    fi
    
    print_info "当前端口: $current_port"
    read -p "请输入运行端口 [默认: $current_port]: " new_port
    
    if [[ -z "$new_port" ]]; then
        new_port=$current_port
    fi
    
    # 验证端口号
    if ! [[ "$new_port" =~ ^[0-9]+$ ]] || [[ "$new_port" -lt 1 ]] || [[ "$new_port" -gt 65535 ]]; then
        print_error "无效的端口号"
        exit 1
    fi
    
    echo "$new_port" > "$INSTALL_DIR/.port"
    print_success "端口设置为: $new_port"
    echo "$new_port"
}

# 创建systemd服务
create_systemd_service() {
    local port=$1
    
    print_info "创建systemd服务..."
    
    cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Clash Subscription Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PORT=$port"
ExecStart=/usr/bin/python3 $INSTALL_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    print_success "systemd服务创建完成"
}

# 创建全局管理命令
create_manage_command() {
    print_info "创建管理命令..."
    
    # 复制脚本到安装目录
    if [[ -f "$0" ]]; then
        cp "$0" "$INSTALL_DIR/install.sh" 2>/dev/null || true
    fi
    
    # 创建全局命令链接
    cat > /usr/local/bin/clashshare <<'EOF'
#!/bin/bash
INSTALL_DIR="/opt/clashshare"
if [[ -f "$INSTALL_DIR/install.sh" ]]; then
    bash "$INSTALL_DIR/install.sh"
else
    echo "错误: 找不到管理脚本"
    echo "请重新下载: wget https://raw.githubusercontent.com/ODJ0930/clashshare/main/install.sh"
    exit 1
fi
EOF
    
    chmod +x /usr/local/bin/clashshare
    print_success "管理命令创建完成"
}

# 启动服务
start_service() {
    print_info "启动服务..."
    systemctl restart ${SERVICE_NAME}
    sleep 2
    
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        print_success "服务启动成功"
        return 0
    else
        print_error "服务启动失败"
        print_info "查看日志: journalctl -u ${SERVICE_NAME} -f"
        return 1
    fi
}

# 停止服务
stop_service() {
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        print_info "停止服务..."
        systemctl stop ${SERVICE_NAME}
        print_success "服务已停止"
    fi
}

# 重置管理员密码
reset_admin_password() {
    cd "$INSTALL_DIR"
    
    print_info "重置管理员账号密码"
    echo
    read -p "请输入新的管理员用户名 [默认: admin]: " new_username
    read -s -p "请输入新的管理员密码 [默认: admin123]: " new_password
    echo
    
    if [[ -z "$new_username" ]]; then
        new_username="admin"
    fi
    
    if [[ -z "$new_password" ]]; then
        new_password="admin123"
    fi
    
    # 停止服务
    stop_service
    
    # 备份数据库
    if [[ -f "clash_manager.db" ]]; then
        cp clash_manager.db clash_manager.db.backup.$(date +%Y%m%d_%H%M%S)
    fi
    
    # 创建Python脚本来重置密码
    cat > /tmp/reset_admin.py <<EOF
import sys
sys.path.insert(0, '$INSTALL_DIR')

from app import app, db
from models import Admin

with app.app_context():
    # 删除所有管理员
    Admin.query.delete()
    
    # 创建新管理员
    admin = Admin(username='$new_username')
    admin.set_password('$new_password')
    db.session.add(admin)
    db.session.commit()
    
    print('✅ 管理员密码重置成功')
    print(f'用户名: $new_username')
    print(f'密码: $new_password')
EOF

    # 执行Python脚本
    python3 /tmp/reset_admin.py
    rm -f /tmp/reset_admin.py
    
    print_success "管理员密码已重置"
    print_info "用户名: $new_username"
    print_info "密码: $new_password"
    
    # 重启服务
    start_service
}

# 安装主函数
install_main() {
    show_banner
    print_info "开始安装 Clash 订阅管理系统..."
    echo
    
    # 检查并安装依赖
    check_and_install_dependencies
    
    # 下载项目
    download_project
    
    # 安装Python依赖
    install_python_dependencies
    
    # 设置端口
    port=$(setup_port)
    
    # 初始化数据库（如果是新安装）
    if [[ ! -f "$INSTALL_DIR/clash_manager.db" ]]; then
        print_info "初始化数据库..."
        cd "$INSTALL_DIR"
        python3 -c "from app import init_db; init_db()" || true
    fi
    
    # 创建systemd服务
    create_systemd_service "$port"
    
    # 启动服务
    if start_service; then
        echo
        print_success "===================== 安装完成 ====================="
        echo
        local server_ip=$(curl -s ifconfig.me || echo "YOUR_SERVER_IP")
        print_info "访问地址: http://$server_ip:$port"
        print_info "默认账号: admin"
        print_info "默认密码: admin123"
        echo
        print_warning "⚠️  请立即登录并修改默认密码！"
        echo
        print_info "常用命令："
        print_info "  管理面板: clashshare"
        print_info "  启动服务: systemctl start $SERVICE_NAME"
        print_info "  停止服务: systemctl stop $SERVICE_NAME"
        print_info "  重启服务: systemctl restart $SERVICE_NAME"
        print_info "  查看状态: systemctl status $SERVICE_NAME"
        print_info "  查看日志: journalctl -u $SERVICE_NAME -f"
        echo
        print_success "=================================================="
        
        # 创建全局管理命令
        create_manage_command
    else
        print_error "安装过程中出现错误"
        exit 1
    fi
}

# 更新主函数
update_main() {
    show_banner
    print_info "开始更新 Clash 订阅管理系统..."
    echo
    
    if [[ ! -d "$INSTALL_DIR" ]]; then
        print_error "未检测到已安装的程序"
        print_info "请先执行安装"
        exit 1
    fi
    
    # 停止服务
    stop_service
    
    # 更新项目
    download_project
    
    # 更新Python依赖
    install_python_dependencies
    
    # 读取当前端口
    if [[ -f "$INSTALL_DIR/.port" ]]; then
        port=$(cat "$INSTALL_DIR/.port")
    else
        port=$DEFAULT_PORT
    fi
    
    # 重新创建systemd服务
    create_systemd_service "$port"
    
    # 启动服务
    if start_service; then
        echo
        print_success "==================== 更新完成 ===================="
        print_info "访问地址: http://$(curl -s ifconfig.me || echo "YOUR_SERVER_IP"):$port"
        print_success "=================================================="
    else
        print_error "更新过程中出现错误"
        exit 1
    fi
}

# 卸载主函数
uninstall_main() {
    show_banner
    print_warning "即将卸载 Clash 订阅管理系统"
    echo
    read -p "是否保留数据库文件？[y/N] " -n 1 -r keep_db
    echo
    read -p "确定要卸载吗？此操作不可恢复！[y/N] " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "取消卸载"
        exit 0
    fi
    
    print_info "开始卸载..."
    
    # 停止并删除服务
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        systemctl stop ${SERVICE_NAME}
    fi
    
    systemctl disable ${SERVICE_NAME} 2>/dev/null || true
    rm -f /etc/systemd/system/${SERVICE_NAME}.service
    systemctl daemon-reload
    
    # 备份数据库
    if [[ -f "$INSTALL_DIR/clash_manager.db" ]] && [[ $keep_db =~ ^[Yy]$ ]]; then
        backup_file="/root/clashshare_backup_$(date +%Y%m%d_%H%M%S).db"
        cp "$INSTALL_DIR/clash_manager.db" "$backup_file"
        print_success "数据库已备份到: $backup_file"
    fi
    
    # 删除安装目录
    if [[ -d "$INSTALL_DIR" ]]; then
        rm -rf "$INSTALL_DIR"
        print_success "安装目录已删除"
    fi
    
    print_success "==================== 卸载完成 ===================="
}

# 查看状态
show_status() {
    show_banner
    
    if [[ ! -d "$INSTALL_DIR" ]]; then
        print_error "未检测到已安装的程序"
        exit 1
    fi
    
    print_info "系统状态："
    echo
    
    # 服务状态
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        print_success "服务状态: 运行中 ✓"
    else
        print_error "服务状态: 已停止 ✗"
    fi
    
    # 端口
    if [[ -f "$INSTALL_DIR/.port" ]]; then
        port=$(cat "$INSTALL_DIR/.port")
        print_info "运行端口: $port"
    fi
    
    # 访问地址
    local server_ip=$(curl -s ifconfig.me || echo "YOUR_SERVER_IP")
    print_info "访问地址: http://$server_ip:${port:-$DEFAULT_PORT}"
    
    # 数据库
    if [[ -f "$INSTALL_DIR/clash_manager.db" ]]; then
        db_size=$(du -h "$INSTALL_DIR/clash_manager.db" | cut -f1)
        print_info "数据库大小: $db_size"
    fi
    
    echo
    print_info "详细日志: journalctl -u $SERVICE_NAME -f"
}

# 主菜单
show_menu() {
    show_banner
    echo
    echo "请选择操作："
    echo
    echo "  1) 安装"
    echo "  2) 更新"
    echo "  3) 卸载"
    echo "  4) 重置管理员密码"
    echo "  5) 修改端口"
    echo "  6) 查看状态"
    echo "  7) 启动服务"
    echo "  8) 停止服务"
    echo "  9) 重启服务"
    echo "  0) 退出"
    echo
}

# 修改端口
change_port() {
    show_banner
    
    if [[ ! -d "$INSTALL_DIR" ]]; then
        print_error "未检测到已安装的程序"
        exit 1
    fi
    
    # 停止服务
    stop_service
    
    # 读取当前端口
    if [[ -f "$INSTALL_DIR/.port" ]]; then
        current_port=$(cat "$INSTALL_DIR/.port")
    else
        current_port=$DEFAULT_PORT
    fi
    
    print_info "当前端口: $current_port"
    echo
    read -p "请输入新的运行端口 [1-65535]: " new_port
    
    # 如果用户直接回车，保持原端口
    if [[ -z "$new_port" ]]; then
        print_warning "未输入端口，保持原端口 $current_port"
        new_port=$current_port
    fi
    
    # 验证端口号
    if ! [[ "$new_port" =~ ^[0-9]+$ ]] || [[ "$new_port" -lt 1 ]] || [[ "$new_port" -gt 65535 ]]; then
        print_error "无效的端口号: $new_port"
        print_info "端口号必须是 1-65535 之间的数字"
        start_service
        return 1
    fi
    
    # 保存新端口
    echo "$new_port" > "$INSTALL_DIR/.port"
    print_success "端口已保存: $new_port"
    
    # 重新创建服务配置
    print_info "更新服务配置..."
    create_systemd_service "$new_port"
    
    # 重启服务
    if start_service; then
        echo
        print_success "=============== 端口修改成功 ==============="
        echo
        local server_ip=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")
        print_info "新访问地址: http://$server_ip:$new_port"
        echo
        print_success "=========================================="
    else
        print_error "服务启动失败，请检查日志: journalctl -u clashshare -f"
    fi
}

# 检查是否为交互式终端
is_interactive() {
    [[ -t 0 ]] && [[ -t 1 ]]
}

# 主程序
main() {
    check_root
    detect_system
    
    # 如果不是交互式终端（如通过curl管道执行），直接安装
    if ! is_interactive; then
        print_info "检测到非交互式执行，开始自动安装..."
        install_main
        exit 0
    fi
    
    while true; do
        show_menu
        read -p "请输入选项 [0-9]: " choice
        
        case $choice in
            1)
                install_main
                read -p "按回车键继续..."
                ;;
            2)
                update_main
                read -p "按回车键继续..."
                ;;
            3)
                uninstall_main
                break
                ;;
            4)
                reset_admin_password
                read -p "按回车键继续..."
                ;;
            5)
                change_port
                read -p "按回车键继续..."
                ;;
            6)
                show_status
                read -p "按回车键继续..."
                ;;
            7)
                start_service
                read -p "按回车键继续..."
                ;;
            8)
                stop_service
                read -p "按回车键继续..."
                ;;
            9)
                stop_service
                start_service
                read -p "按回车键继续..."
                ;;
            0)
                print_info "退出脚本"
                exit 0
                ;;
            *)
                print_error "无效的选项"
                sleep 2
                ;;
        esac
    done
}

# 如果脚本带参数，直接执行对应功能
if [[ $# -gt 0 ]]; then
    case $1 in
        install)
            check_root
            detect_system
            install_main
            ;;
        update)
            check_root
            detect_system
            update_main
            ;;
        uninstall)
            check_root
            detect_system
            uninstall_main
            ;;
        *)
            echo "用法: $0 [install|update|uninstall]"
            exit 1
            ;;
    esac
else
    main
fi

