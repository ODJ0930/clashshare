#!/usr/bin/env python3
"""
Web 管理界面主程序
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from models import db, Admin, Subscription, Node, User, Template
from parsers import ProxyParser
from generator import ClashConfigGenerator
import os
import secrets
from datetime import timedelta
from functools import wraps
import requests as req
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clash_manager.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Session 保持 7 天

db.init_app(app)


def login_required(f):
    """登录验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    """首页 - 重定向到管理面板"""
    if 'admin_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """管理员登录"""
    if request.method == 'GET':
        return render_template('login.html')
    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    remember = data.get('remember', False)
    
    admin = Admin.query.filter_by(username=username).first()
    
    if admin and admin.check_password(password):
        session['admin_id'] = admin.id
        session['username'] = admin.username
        
        if remember:
            session.permanent = True
        
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'message': '用户名或密码错误'}), 401


@app.route('/logout')
def logout():
    """登出"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    """管理面板"""
    return render_template('dashboard.html')


# ============ 订阅管理 API ============

@app.route('/api/subscriptions', methods=['GET', 'POST'])
@login_required
def manage_subscriptions():
    """获取或添加订阅（节点分组）"""
    if request.method == 'GET':
        subs = Subscription.query.all()
        return jsonify([{
            'id': s.id,
            'name': s.name,
            'subscription_token': s.subscription_token,
            'custom_slug': s.custom_slug,
            'user_names': [u.username for u in s.users],  # 多个用户
            'user_count': len(s.users),
            'node_count': len(s.nodes),
            'created_at': s.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for s in subs])
    
    # POST - 创建订阅分组
    data = request.get_json()
    name = data.get('name')
    user_ids = data.get('user_ids', [])  # 可选：指定多个用户
    
    if not name:
        return jsonify({'success': False, 'message': '名称不能为空'}), 400
    
    sub = Subscription(
        name=name,
        subscription_token=secrets.token_urlsafe(32)
    )
    
    # 关联用户
    if user_ids:
        users = User.query.filter(User.id.in_(user_ids)).all()
        sub.users = users
    
    db.session.add(sub)
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'id': sub.id,
        'token': sub.subscription_token
    })


@app.route('/api/subscriptions/<int:sub_id>', methods=['PUT', 'DELETE'])
@login_required
def update_subscription(sub_id):
    """更新或删除订阅分组"""
    sub = Subscription.query.get_or_404(sub_id)
    
    if request.method == 'DELETE':
        db.session.delete(sub)
        db.session.commit()
        return jsonify({'success': True})
    
    # PUT - 更新订阅
    data = request.get_json()
    if 'name' in data:
        sub.name = data['name']
    if 'custom_slug' in data:
        # 验证自定义后缀
        custom_slug = data['custom_slug'].strip() if data['custom_slug'] else None
        if custom_slug:
            # 检查是否已存在（排除自己）
            existing = Subscription.query.filter(
                Subscription.custom_slug == custom_slug,
                Subscription.id != sub_id
            ).first()
            if existing:
                return jsonify({'success': False, 'message': '该自定义后缀已被使用'}), 400
            # 验证格式（只允许字母、数字、下划线、中划线）
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', custom_slug):
                return jsonify({'success': False, 'message': '自定义后缀只能包含字母、数字、下划线和中划线'}), 400
        sub.custom_slug = custom_slug
    if 'user_ids' in data:
        # 更新关联的用户
        user_ids = data['user_ids']
        # 清除现有关联并添加新关联
        if user_ids:
            users = User.query.filter(User.id.in_(user_ids)).all()
            sub.users = users
        else:
            sub.users = []
    
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/subscriptions/<int:sub_id>/regenerate-token', methods=['POST'])
@login_required
def regenerate_subscription_token(sub_id):
    """重新生成订阅令牌"""
    sub = Subscription.query.get_or_404(sub_id)
    sub.subscription_token = secrets.token_urlsafe(32)
    db.session.commit()
    
    return jsonify({'success': True, 'token': sub.subscription_token})


@app.route('/api/subscriptions/<int:sub_id>/nodes', methods=['GET', 'POST'])
@login_required
def manage_subscription_nodes(sub_id):
    """获取或设置订阅分组的节点"""
    sub = Subscription.query.get_or_404(sub_id)
    
    if request.method == 'GET':
        return jsonify([{
            'id': n.id,
            'name': n.name,
            'protocol': n.protocol
        } for n in sub.nodes])
    
    # POST - 设置订阅分组的节点（多对多关系）
    data = request.get_json()
    node_ids = data.get('node_ids', [])
    
    # 获取所有要关联的节点
    if node_ids:
        nodes = Node.query.filter(Node.id.in_(node_ids)).all()
        sub.nodes = nodes
    else:
        # 如果node_ids为空，清空该订阅的所有节点
        sub.nodes = []
    
    db.session.commit()
    
    return jsonify({'success': True, 'count': len(node_ids)})


# ============ 节点管理 API ============

@app.route('/api/nodes', methods=['GET', 'POST'])
@login_required
def manage_nodes():
    """获取或添加节点"""
    if request.method == 'GET':
        # 按排序字段排序
        nodes = Node.query.order_by(Node.order.asc(), Node.id.asc()).all()
        return jsonify([{
            'id': n.id,
            'name': n.name,
            'original_name': n.original_name,
            'protocol': n.protocol,
            'subscription_id': n.subscription_id,  # 保留用于兼容性
            'subscription_name': ', '.join([s.name for s in n.subscriptions]) if n.subscriptions else '手动添加',
            'subscription_names': [s.name for s in n.subscriptions],  # 新增：所有订阅名称列表
            'subscription_ids': [s.id for s in n.subscriptions],  # 新增：所有订阅ID列表
            'user_names': list(set([u.username for s in n.subscriptions for u in s.users])) if n.subscriptions else [],
            'order': n.order if hasattr(n, 'order') else 0,
            'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for n in nodes])
    
    # POST - 添加单个节点
    data = request.get_json()
    node_url = data.get('url')
    custom_name = data.get('name')
    subscription_id = data.get('subscription_id')  # 可选：指定订阅分组
    
    if not node_url:
        return jsonify({'success': False, 'message': '节点配置不能为空'}), 400
    
    node_url = node_url.strip()
    
    # 检测是 YAML 配置还是节点链接
    proxy = None
    
    # 情况1: 检测是否为 YAML 格式（包含 "type:" 关键字或以 "{" 开头）
    if ('type:' in node_url or node_url.startswith('{') or node_url.startswith('- {')):
        print("检测到 YAML 格式配置")
        try:
            import yaml
            
            # 预处理 YAML 内容
            yaml_content = node_url
            
            # 如果是单行字典格式，需要包装成数组
            if yaml_content.startswith('{') and not yaml_content.startswith('- {'):
                yaml_content = '- ' + yaml_content
            elif yaml_content.startswith('- {'):
                pass  # 已经是正确格式
            
            # 尝试解析
            parsed = yaml.safe_load(yaml_content)
            
            if isinstance(parsed, list) and len(parsed) > 0:
                proxy = parsed[0]  # 取第一个节点
            elif isinstance(parsed, dict):
                proxy = parsed
            
            if proxy and isinstance(proxy, dict):
                print(f"成功解析 YAML 节点: {proxy.get('name')}")
            else:
                return jsonify({'success': False, 'message': 'YAML 格式不正确'}), 400
                
        except Exception as e:
            print(f"YAML 解析失败: {e}")
            return jsonify({'success': False, 'message': f'YAML 解析失败: {str(e)}'}), 400
    else:
        # 情况2: 传统节点分享链接（ss://, vmess://, trojan:// 等）
        print("检测到节点分享链接")
        proxy = ProxyParser.parse_proxy(node_url)
        if not proxy:
            return jsonify({'success': False, 'message': '无法解析节点链接。请使用标准分享链接或 YAML 配置格式。'}), 400
    
    # 验证节点配置
    if not proxy or not isinstance(proxy, dict):
        return jsonify({'success': False, 'message': '节点配置无效'}), 400
    
    if 'name' not in proxy or 'type' not in proxy:
        return jsonify({'success': False, 'message': '节点配置缺少必要字段（name 或 type）'}), 400
    
    # 确定节点名称（自定义名称优先，仅对节点链接生效）
    node_name = custom_name or proxy['name']
    original_name = proxy['name']
    
    # 如果使用了自定义名称，更新配置中的名称
    if custom_name:
        proxy['name'] = custom_name
    
    # 获取当前最大排序值，新节点排在最后，从1开始
    max_order = db.session.query(db.func.max(Node.order)).scalar() or 0
    
    node = Node(
        name=node_name,
        original_name=original_name,
        protocol=proxy['type'],
        subscription_id=subscription_id,
        order=max_order + 1
    )
    node.set_config(proxy)
    
    db.session.add(node)
    
    # 如果指定了订阅分组，添加到多对多关系
    if subscription_id:
        subscription = Subscription.query.get(subscription_id)
        if subscription:
            node.subscriptions.append(subscription)
    
    db.session.commit()
    
    return jsonify({'success': True, 'id': node.id})


@app.route('/api/nodes/batch-import', methods=['POST'])
@login_required
def batch_import_nodes():
    """批量导入节点（从机场订阅URL）"""
    data = request.get_json()
    url = data.get('url')
    subscription_id = data.get('subscription_id')  # 可选：归属到某个订阅分组
    
    if not url:
        return jsonify({'success': False, 'message': '订阅链接不能为空'}), 400
    
    try:
        # 获取订阅内容
        response = req.get(url, timeout=30)
        response.raise_for_status()
        content = response.text
        
        # 解析节点
        proxies = ProxyParser.parse_subscription(content)
        
        if not proxies:
            return jsonify({'success': False, 'message': '未能解析到任何节点'}), 400
        
        # 获取当前最大排序值，从1开始
        max_order = db.session.query(db.func.max(Node.order)).scalar() or 0
        
        # 如果指定了订阅分组，先获取订阅对象
        subscription = None
        if subscription_id:
            subscription = Subscription.query.get(subscription_id)
        
        # 添加节点
        added_count = 0
        for proxy in proxies:
            node = Node(
                name=proxy['name'],
                original_name=proxy['name'],
                protocol=proxy['type'],
                subscription_id=subscription_id,
                order=max_order + added_count + 1
            )
            node.set_config(proxy)
            db.session.add(node)
            
            # 添加到多对多关系
            if subscription:
                node.subscriptions.append(subscription)
            
            added_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'count': added_count
        })
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/nodes/<int:node_id>', methods=['PUT', 'DELETE'])
@login_required
def update_node(node_id):
    """更新或删除节点"""
    node = Node.query.get_or_404(node_id)
    
    if request.method == 'DELETE':
        db.session.delete(node)
        db.session.commit()
        return jsonify({'success': True})
    
    # PUT - 更新节点（重命名、更改订阅分组或排序）
    data = request.get_json()
    if 'name' in data:
        node.name = data['name']
        # 同时更新配置中的名称
        config = node.get_config()
        config['name'] = data['name']
        node.set_config(config)
    if 'subscription_id' in data:
        node.subscription_id = data['subscription_id']
    if 'order' in data:
        node.order = data['order']
    
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/nodes/batch-delete', methods=['POST'])
@login_required
def batch_delete_nodes():
    """批量删除节点"""
    data = request.get_json()
    node_ids = data.get('node_ids', [])
    
    if not node_ids:
        return jsonify({'success': False, 'message': '未选择任何节点'}), 400
    
    try:
        # 删除指定的节点
        deleted_count = 0
        for node_id in node_ids:
            node = Node.query.get(node_id)
            if node:
                db.session.delete(node)
                deleted_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'count': deleted_count,
            'message': f'成功删除 {deleted_count} 个节点'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/nodes/<int:node_id>/detail', methods=['GET'])
@login_required
def get_node_detail(node_id):
    """获取节点详细信息"""
    node = Node.query.get_or_404(node_id)
    
    return jsonify({
        'id': node.id,
        'name': node.name,
        'original_name': node.original_name,
        'protocol': node.protocol,
        'config': node.get_config(),
        'subscription_id': node.subscription_id,
        'created_at': node.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/api/nodes/<int:node_id>/config', methods=['PUT'])
@login_required
def update_node_config(node_id):
    """更新节点完整配置"""
    node = Node.query.get_or_404(node_id)
    
    data = request.get_json()
    new_config = data.get('config')
    
    if not new_config:
        return jsonify({'success': False, 'message': '配置不能为空'}), 400
    
    # 验证配置中必须包含基本字段
    if 'name' not in new_config or 'type' not in new_config:
        return jsonify({'success': False, 'message': '配置缺少必要字段'}), 400
    
    # 更新节点信息
    node.name = new_config['name']
    node.protocol = new_config['type']
    node.set_config(new_config)
    
    db.session.commit()
    
    return jsonify({'success': True})


@app.route('/api/nodes/manual-create', methods=['POST'])
@login_required
def manual_create_node():
    """手动创建节点（不通过URL解析）"""
    data = request.get_json()
    config = data.get('config')
    subscription_id = data.get('subscription_id')
    
    if not config:
        return jsonify({'success': False, 'message': '配置不能为空'}), 400
    
    # 验证必要字段
    required_fields = ['name', 'type', 'server', 'port']
    for field in required_fields:
        if field not in config:
            return jsonify({'success': False, 'message': f'缺少必要字段: {field}'}), 400
    
    # 根据不同协议验证额外的必要字段
    protocol = config['type']
    protocol_required = {
        'ss': ['cipher', 'password'],
        'ssr': ['cipher', 'password', 'protocol', 'obfs'],
        'vmess': ['uuid'],
        'vless': ['uuid'],
        'trojan': ['password'],
        'hysteria2': ['password'],
        'socks5': [],  # 用户名密码可选
        'http': []  # 用户名密码可选
    }
    
    if protocol in protocol_required:
        for field in protocol_required[protocol]:
            if field not in config or not config[field]:
                return jsonify({'success': False, 'message': f'{protocol.upper()} 协议缺少必要字段: {field}'}), 400
    
    # 获取当前最大排序值，从1开始
    max_order = db.session.query(db.func.max(Node.order)).scalar() or 0
    
    # 创建节点
    node = Node(
        name=config['name'],
        original_name=config['name'],
        protocol=protocol,
        subscription_id=subscription_id,
        order=max_order + 1
    )
    node.set_config(config)
    
    db.session.add(node)
    
    # 如果指定了订阅分组，添加到多对多关系
    if subscription_id:
        subscription = Subscription.query.get(subscription_id)
        if subscription:
            node.subscriptions.append(subscription)
    
    db.session.commit()
    
    return jsonify({'success': True, 'id': node.id})


@app.route('/api/nodes/relay', methods=['POST'])
@login_required
def create_relay_node():
    """创建链式代理节点（relay类型）"""
    data = request.get_json()
    config = data.get('config')
    subscription_id = data.get('subscription_id')
    
    if not config:
        return jsonify({'success': False, 'message': '配置不能为空'}), 400
    
    # 验证必要字段
    if 'name' not in config or 'type' not in config or 'proxies' not in config:
        return jsonify({'success': False, 'message': '缺少必要字段: name, type, proxies'}), 400
    
    if config['type'] != 'relay':
        return jsonify({'success': False, 'message': '节点类型必须为 relay'}), 400
    
    if not isinstance(config['proxies'], list) or len(config['proxies']) < 2:
        return jsonify({'success': False, 'message': '至少需要2个代理节点'}), 400
    
    # 获取当前最大排序值，从1开始
    max_order = db.session.query(db.func.max(Node.order)).scalar() or 0
    
    # 创建relay节点
    node = Node(
        name=config['name'],
        original_name=config['name'],
        protocol='relay',
        subscription_id=subscription_id,
        order=max_order + 1
    )
    node.set_config(config)
    
    db.session.add(node)
    
    # 如果指定了订阅分组，添加到多对多关系
    if subscription_id:
        subscription = Subscription.query.get(subscription_id)
        if subscription:
            node.subscriptions.append(subscription)
    
    db.session.commit()
    
    return jsonify({'success': True, 'id': node.id})


@app.route('/api/nodes/batch-relay', methods=['POST'])
@login_required
def batch_create_relay_nodes():
    """批量创建链式代理节点"""
    data = request.get_json()
    configs = data.get('configs', [])
    subscription_id = data.get('subscription_id')
    
    if not configs:
        return jsonify({'success': False, 'message': '配置列表不能为空'}), 400
    
    if not isinstance(configs, list):
        return jsonify({'success': False, 'message': '配置必须是列表'}), 400
    
    try:
        # 获取当前最大排序值
        max_order = db.session.query(db.func.max(Node.order)).scalar() or 0
        
        # 如果指定了订阅分组，先获取订阅对象
        subscription = None
        if subscription_id:
            subscription = Subscription.query.get(subscription_id)
        
        created_count = 0
        for config in configs:
            # 验证必要字段
            if 'name' not in config or 'type' not in config or 'proxies' not in config:
                continue
            
            if config['type'] != 'relay':
                continue
            
            if not isinstance(config['proxies'], list) or len(config['proxies']) < 2:
                continue
            
            # 创建relay节点
            node = Node(
                name=config['name'],
                original_name=config['name'],
                protocol='relay',
                subscription_id=subscription_id,
                order=max_order + created_count + 1
            )
            node.set_config(config)
            
            db.session.add(node)
            
            # 添加到多对多关系
            if subscription:
                node.subscriptions.append(subscription)
            
            created_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'count': created_count,
            'message': f'成功创建 {created_count} 个链式节点'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ============ 用户管理 API ============

@app.route('/api/users', methods=['GET', 'POST'])
@login_required
def manage_users():
    """获取或添加用户（分组）"""
    if request.method == 'GET':
        users = User.query.all()
        return jsonify([{
            'id': u.id,
            'username': u.username,
            'subscription_token': u.subscription_token,
            'custom_slug': u.custom_slug,
            'subscription_count': len(u.subscriptions),
            'node_count': sum(len(s.nodes) for s in u.subscriptions),
            'enabled': u.enabled,
            'remark': u.remark or '',
            'template_id': u.template_id,
            'template_name': u.template.name if u.template else None,
            'created_at': u.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for u in users])
    
    # POST - 添加用户（分组）
    data = request.get_json()
    username = data.get('username')
    remark = data.get('remark', '')
    
    if not username:
        return jsonify({'success': False, 'message': '名称不能为空'}), 400
    
    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': '名称已存在'}), 400
    
    user = User(
        username=username,
        remark=remark,
        subscription_token=secrets.token_urlsafe(32)
    )
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({
        'success': True,
        'id': user.id,
        'token': user.subscription_token
    })


@app.route('/api/users/<int:user_id>', methods=['PUT', 'DELETE'])
@login_required
def update_user(user_id):
    """更新或删除用户（分组）"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'DELETE':
        db.session.delete(user)
        db.session.commit()
        return jsonify({'success': True})
    
    # PUT - 更新用户（分组）
    data = request.get_json()
    
    if 'username' in data:
        # 检查新名称是否已存在
        existing = User.query.filter(User.username == data['username'], User.id != user_id).first()
        if existing:
            return jsonify({'success': False, 'message': '名称已存在'}), 400
        user.username = data['username']
    
    if 'remark' in data:
        user.remark = data['remark']
    
    if 'custom_slug' in data:
        # 验证自定义后缀
        custom_slug = data['custom_slug'].strip() if data['custom_slug'] else None
        if custom_slug:
            # 检查是否已存在（排除自己）
            existing = User.query.filter(
                User.custom_slug == custom_slug,
                User.id != user_id
            ).first()
            if existing:
                return jsonify({'success': False, 'message': '该自定义后缀已被使用'}), 400
            # 验证格式（只允许字母、数字、下划线、中划线）
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', custom_slug):
                return jsonify({'success': False, 'message': '自定义后缀只能包含字母、数字、下划线和中划线'}), 400
        user.custom_slug = custom_slug
    
    if 'template_id' in data:
        user.template_id = data['template_id'] if data['template_id'] else None
    
    if 'enabled' in data:
        user.enabled = data['enabled']
    
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/users/<int:user_id>/subscriptions', methods=['GET', 'POST'])
@login_required
def manage_user_subscriptions(user_id):
    """获取或设置用户的订阅"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'GET':
        return jsonify([{
            'id': s.id,
            'name': s.name,
            'subscription_token': s.subscription_token,
            'node_count': len(s.nodes),
            'created_at': s.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for s in user.subscriptions])
    
    # POST - 设置用户订阅（分配订阅给用户）
    data = request.get_json()
    subscription_ids = data.get('subscription_ids', [])
    
    # 清空当前用户的所有订阅关联
    user.subscriptions = []
    
    # 添加新的订阅关联（多对多，不会影响其他用户）
    if subscription_ids:
        subscriptions = Subscription.query.filter(Subscription.id.in_(subscription_ids)).all()
        user.subscriptions = subscriptions
    
    db.session.commit()
    
    return jsonify({'success': True, 'count': len(subscription_ids)})


@app.route('/api/users/<int:user_id>/regenerate-token', methods=['POST'])
@login_required
def regenerate_user_token(user_id):
    """重新生成用户订阅令牌"""
    user = User.query.get_or_404(user_id)
    user.subscription_token = secrets.token_urlsafe(32)
    db.session.commit()
    
    return jsonify({'success': True, 'token': user.subscription_token})


# ============ 订阅接口 ============

@app.route('/sub/user/<token>')
def user_subscription(token):
    """用户订阅接口（支持自定义后缀和系统token）"""
    # 先尝试用custom_slug查找，再用subscription_token查找
    user = User.query.filter_by(custom_slug=token).first()
    if not user:
        user = User.query.filter_by(subscription_token=token).first()
    
    if not user or not user.enabled:
        return "Invalid subscription", 404
    
    # 获取用户的所有订阅下的所有节点，并按排序字段排序
    all_nodes = []
    for subscription in user.subscriptions:
        all_nodes.extend(subscription.nodes)
    
    if not all_nodes:
        return "No nodes available", 404
    
    # 按order字段排序节点
    all_nodes.sort(key=lambda n: (n.order if hasattr(n, 'order') and n.order is not None else 0, n.id))
    
    # 获取所有节点配置
    proxies = [node.get_config() for node in all_nodes]
    
    # 生成 Clash 配置
    generator = ClashConfigGenerator()
    
    # 如果用户设置了模板，使用模板生成
    template_content = None
    if user.template_id:
        template = Template.query.get(user.template_id)
        if template:
            template_content = template.content
    
    config = generator.generate(proxies, f"🚀 {user.username} 专属", template_content)
    
    # 转换为 YAML
    import yaml
    from urllib.parse import quote
    yaml_content = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    # 对文件名进行URL编码以支持中文
    filename = f'clash_{user.username}.yaml'
    encoded_filename = quote(filename)
    
    # 返回文件
    return yaml_content, 200, {
        'Content-Type': 'text/yaml; charset=utf-8',
        'Content-Disposition': f"attachment; filename={encoded_filename}; filename*=UTF-8''{encoded_filename}",
        'Subscription-Userinfo': f'upload=0; download=0; total=0; expire=0'
    }


@app.route('/sub/subscription/<token>')
def subscription_access(token):
    """订阅分组访问接口（支持自定义后缀和系统token）"""
    # 先尝试用custom_slug查找，再用subscription_token查找
    subscription = Subscription.query.filter_by(custom_slug=token).first()
    if not subscription:
        subscription = Subscription.query.filter_by(subscription_token=token).first()
    
    if not subscription:
        return "Invalid subscription", 404
    
    if not subscription.nodes:
        return "No nodes available", 404
    
    # 按order字段排序节点
    sorted_nodes = sorted(subscription.nodes, key=lambda n: (n.order if hasattr(n, 'order') and n.order is not None else 0, n.id))
    
    # 获取订阅分组的所有节点配置
    proxies = [node.get_config() for node in sorted_nodes]
    
    # 生成 Clash 配置
    generator = ClashConfigGenerator()
    
    # 如果订阅分组设置了模板，使用模板生成
    template_content = None
    if subscription.template_id:
        template = Template.query.get(subscription.template_id)
        if template:
            template_content = template.content
    
    config = generator.generate(proxies, f"📡 {subscription.name}", template_content)
    
    # 转换为 YAML
    import yaml
    from urllib.parse import quote
    yaml_content = yaml.dump(config, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    # 对文件名进行URL编码以支持中文
    filename = f'clash_{subscription.name}.yaml'
    encoded_filename = quote(filename)
    
    # 返回文件
    return yaml_content, 200, {
        'Content-Type': 'text/yaml; charset=utf-8',
        'Content-Disposition': f"attachment; filename={encoded_filename}; filename*=UTF-8''{encoded_filename}",
        'Subscription-Userinfo': f'upload=0; download=0; total=0; expire=0'
    }


# ============ 模板管理 API ============

@app.route('/api/templates', methods=['GET', 'POST'])
@login_required
def manage_templates():
    """获取或创建模板"""
    if request.method == 'GET':
        templates = Template.query.all()
        return jsonify([{
            'id': t.id,
            'name': t.name,
            'description': t.description,
            'is_default': t.is_default,
            'created_at': t.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'usage_count': len(t.subscriptions) + len(t.users)
        } for t in templates])
    
    # POST - 创建新模板
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    content = data.get('content')
    
    if not name or not content:
        return jsonify({'success': False, 'message': '模板名称和内容不能为空'}), 400
    
    # 验证YAML格式
    try:
        import yaml
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        return jsonify({'success': False, 'message': f'YAML格式错误: {str(e)}'}), 400
    
    template = Template(
        name=name,
        description=description,
        content=content,
        is_default=False
    )
    
    db.session.add(template)
    db.session.commit()
    
    return jsonify({'success': True, 'id': template.id})


@app.route('/api/templates/<int:template_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def manage_template(template_id):
    """获取、更新或删除模板"""
    template = Template.query.get_or_404(template_id)
    
    if request.method == 'GET':
        return jsonify({
            'id': template.id,
            'name': template.name,
            'description': template.description,
            'content': template.content,
            'is_default': template.is_default,
            'created_at': template.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    if request.method == 'PUT':
        data = request.get_json()
        
        if 'name' in data:
            template.name = data['name']
        if 'description' in data:
            template.description = data['description']
        if 'content' in data:
            # 验证YAML格式
            try:
                import yaml
                yaml.safe_load(data['content'])
                template.content = data['content']
            except yaml.YAMLError as e:
                return jsonify({'success': False, 'message': f'YAML格式错误: {str(e)}'}), 400
        
        db.session.commit()
        return jsonify({'success': True})
    
    if request.method == 'DELETE':
        # 检查是否有订阅或用户在使用此模板
        if template.subscriptions or template.users:
            return jsonify({
                'success': False, 
                'message': f'此模板正在被 {len(template.subscriptions) + len(template.users)} 个订阅/用户使用，无法删除'
            }), 400
        
        db.session.delete(template)
        db.session.commit()
        return jsonify({'success': True})


@app.route('/api/templates/<int:template_id>/set-default', methods=['POST'])
@login_required
def set_default_template(template_id):
    """设置默认模板"""
    # 取消所有模板的默认状态
    Template.query.update({'is_default': False})
    
    # 设置指定模板为默认
    template = Template.query.get_or_404(template_id)
    template.is_default = True
    
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/templates/import', methods=['POST'])
@login_required
def import_template():
    """从YAML配置文件导入模板"""
    data = request.get_json()
    name = data.get('name')
    description = data.get('description', '')
    yaml_content = data.get('content')
    
    if not name or not yaml_content:
        return jsonify({'success': False, 'message': '模板名称和内容不能为空'}), 400
    
    try:
        import yaml
        
        # 解析YAML
        config = yaml.safe_load(yaml_content)
        
        # 提取proxies中的所有节点名称
        proxies = config.get('proxies', [])
        node_names = set()
        for proxy in proxies:
            if isinstance(proxy, dict) and 'name' in proxy:
                node_names.add(proxy['name'])
        
        # 特殊策略列表（不应被替换）
        special_policies = {'DIRECT', 'REJECT', 'PASS', 'COMPATIBLE'}
        
        # 处理proxy-groups
        proxy_groups = config.get('proxy-groups', [])
        processed_groups = []
        
        # 收集所有策略组名称
        group_names = {group['name'] for group in proxy_groups if isinstance(group, dict) and 'name' in group}
        
        for group in proxy_groups:
            if not isinstance(group, dict):
                continue
                
            processed_group = group.copy()
            
            if 'proxies' in processed_group and len(processed_group['proxies']) > 0:
                new_proxies = []
                
                for proxy in processed_group['proxies']:
                    # 保留特殊策略
                    if proxy in special_policies:
                        new_proxies.append(proxy)
                    # 保留策略组引用
                    elif proxy in group_names:
                        new_proxies.append(proxy)
                    # 其他的都是实际节点，不添加（会被PROXY_NODES替代）
                
                # 无论如何都添加 PROXY_NODES，这样每个组都包含所有节点
                new_proxies.append('PROXY_NODES')
                
                processed_group['proxies'] = new_proxies
            elif 'proxies' in processed_group:
                # 如果原来proxies是空列表，也添加PROXY_NODES
                processed_group['proxies'] = ['PROXY_NODES']
            
            processed_groups.append(processed_group)
        
        # 构建新的配置（移除proxies部分）
        new_config = {}
        for key, value in config.items():
            if key == 'proxies':
                new_config[key] = []  # 清空proxies
            elif key == 'proxy-groups':
                new_config[key] = processed_groups
            else:
                new_config[key] = value
        
        # 转换回YAML
        template_content = yaml.dump(new_config, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        # 保存模板
        template = Template(
            name=name,
            description=description,
            content=template_content,
            is_default=False
        )
        
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'id': template.id,
            'replaced_nodes': len(node_names)
        })
        
    except yaml.YAMLError as e:
        return jsonify({'success': False, 'message': f'YAML格式错误: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'导入失败: {str(e)}'}), 500


# ============ 统计 API ============

@app.route('/api/stats')
@login_required
def get_stats():
    """获取统计信息"""
    return jsonify({
        'subscriptions': Subscription.query.count(),
        'nodes': Node.query.count(),
        'users': User.query.count(),
        'templates': Template.query.count()
    })


# ============ 管理员设置 API ============

@app.route('/api/admin/profile', methods=['GET'])
@login_required
def get_admin_profile():
    """获取管理员信息"""
    admin = Admin.query.get(session['admin_id'])
    return jsonify({
        'username': admin.username,
        'created_at': admin.created_at.strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/api/admin/change-password', methods=['POST'])
@login_required
def change_admin_password():
    """修改管理员密码"""
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    
    if not current_password or not new_password:
        return jsonify({'success': False, 'message': '请填写完整信息'}), 400
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': '新密码至少需要6位'}), 400
    
    admin = Admin.query.get(session['admin_id'])
    
    # 验证当前密码
    if not admin.check_password(current_password):
        return jsonify({'success': False, 'message': '当前密码错误'}), 401
    
    # 设置新密码
    admin.set_password(new_password)
    db.session.commit()
    
    return jsonify({'success': True, 'message': '密码修改成功'})


@app.route('/api/admin/change-username', methods=['POST'])
@login_required
def change_admin_username():
    """修改管理员用户名"""
    data = request.get_json()
    new_username = data.get('new_username')
    password = data.get('password')
    
    if not new_username or not password:
        return jsonify({'success': False, 'message': '请填写完整信息'}), 400
    
    if len(new_username) < 3:
        return jsonify({'success': False, 'message': '用户名至少需要3位'}), 400
    
    admin = Admin.query.get(session['admin_id'])
    
    # 验证密码
    if not admin.check_password(password):
        return jsonify({'success': False, 'message': '密码错误'}), 401
    
    # 检查用户名是否已存在
    existing = Admin.query.filter(Admin.username == new_username, Admin.id != admin.id).first()
    if existing:
        return jsonify({'success': False, 'message': '用户名已存在'}), 400
    
    # 修改用户名
    admin.username = new_username
    session['username'] = new_username
    db.session.commit()
    
    return jsonify({'success': True, 'message': '用户名修改成功'})


# ============ 初始化数据库 ============

def init_db():
    """初始化数据库"""
    with app.app_context():
        try:
            db.create_all()
            
            # 创建默认管理员（如果不存在）
            if not Admin.query.first():
                admin = Admin(username='admin')
                admin.set_password('admin123')  # 默认密码
                db.session.add(admin)
                db.session.commit()
                print("✅ 默认管理员已创建")
                print("   用户名: admin")
                print("   密码: admin123")
                print("   ⚠️  请登录后立即修改密码！")
            
            # 创建默认模板（如果不存在）
            if not Template.query.first():
                default_template_content = """# Clash Meta 配置模板
# 使用 PROXY_NODES 占位符代表所有节点

mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
external-controller: 127.0.0.1:9090

dns:
  enable: true
  ipv6: false
  enhanced-mode: fake-ip
  fake-ip-range: 198.18.0.1/16
  default-nameserver:
    - 223.5.5.5
    - 119.29.29.29
  nameserver:
    - https://doh.pub/dns-query
    - https://dns.alidns.com/dns-query
  fallback:
    - https://1.1.1.1/dns-query
    - https://dns.google/dns-query
  fallback-filter:
    geoip: true
    geoip-code: CN

proxies: []

proxy-groups:
  - name: 🚀 节点选择
    type: select
    proxies:
      - ♻️ 自动选择
      - 🎯 全球直连
      - PROXY_NODES

  - name: ♻️ 自动选择
    type: url-test
    proxies:
      - PROXY_NODES
    url: http://www.gstatic.com/generate_204
    interval: 300

  - name: 📺 流媒体
    type: select
    proxies:
      - 🚀 节点选择
      - ♻️ 自动选择
      - PROXY_NODES

  - name: 🎯 全球直连
    type: select
    proxies:
      - DIRECT

  - name: 🛑 广告拦截
    type: select
    proxies:
      - REJECT
      - DIRECT

  - name: 🐟 漏网之鱼
    type: select
    proxies:
      - 🚀 节点选择
      - 🎯 全球直连
      - ♻️ 自动选择

rules:
  # 广告拦截
  - DOMAIN-KEYWORD,adservice,🛑 广告拦截
  - DOMAIN-KEYWORD,analytics,🛑 广告拦截
  - DOMAIN-SUFFIX,doubleclick.net,🛑 广告拦截
  - DOMAIN-SUFFIX,googleadservices.com,🛑 广告拦截
  
  # 流媒体规则
  - DOMAIN-KEYWORD,youtube,📺 流媒体
  - DOMAIN-KEYWORD,netflix,📺 流媒体
  - DOMAIN-KEYWORD,spotify,📺 流媒体
  - DOMAIN-SUFFIX,youtube.com,📺 流媒体
  - DOMAIN-SUFFIX,googlevideo.com,📺 流媒体
  - DOMAIN-SUFFIX,netflix.com,📺 流媒体
  - DOMAIN-SUFFIX,nflxvideo.net,📺 流媒体
  
  # 国内直连
  - DOMAIN-SUFFIX,cn,🎯 全球直连
  - DOMAIN-KEYWORD,baidu,🎯 全球直连
  - DOMAIN-KEYWORD,alipay,🎯 全球直连
  - DOMAIN-SUFFIX,qq.com,🎯 全球直连
  - DOMAIN-SUFFIX,taobao.com,🎯 全球直连
  - DOMAIN-SUFFIX,bilibili.com,🎯 全球直连
  
  # 常见国外网站走代理
  - DOMAIN-KEYWORD,google,🚀 节点选择
  - DOMAIN-KEYWORD,facebook,🚀 节点选择
  - DOMAIN-KEYWORD,twitter,🚀 节点选择
  - DOMAIN-KEYWORD,github,🚀 节点选择
  - DOMAIN-SUFFIX,google.com,🚀 节点选择
  - DOMAIN-SUFFIX,facebook.com,🚀 节点选择
  - DOMAIN-SUFFIX,twitter.com,🚀 节点选择
  - DOMAIN-SUFFIX,github.com,🚀 节点选择
  - DOMAIN-SUFFIX,telegram.org,🚀 节点选择
  
  # GeoIP 规则
  - GEOIP,CN,🎯 全球直连
  
  # 最终规则
  - MATCH,🐟 漏网之鱼
"""
                
                default_template = Template(
                    name='默认模板',
                    description='简单分流模板：国内直连，国外代理，包含流媒体和广告拦截',
                    content=default_template_content,
                    is_default=True
                )
                db.session.add(default_template)
                db.session.commit()
                print("✅ 默认配置模板已创建")
        except Exception as e:
            print(f"\n❌ 数据库初始化失败: {e}")
            print("\n可能的原因：")
            print("1. 数据库结构与代码不匹配（需要迁移）")
            print("2. 数据库文件损坏")
            print("\n解决方案：")
            print("选项 1 - 迁移数据库（保留数据）:")
            print("  python migrate_database.py")
            print("\n选项 2 - 重置数据库（清空数据）:")
            print("  python reset_database.py")
            print("\n选项 3 - 手动删除数据库:")
            print("  del clash_manager.db  # Windows")
            print("  rm clash_manager.db   # Linux/Mac")
            print("  然后重新运行 python app.py")
            import sys
            sys.exit(1)


if __name__ == '__main__':
    init_db()
    
    # 从环境变量或配置文件读取端口
    port = int(os.environ.get('PORT', 5000))
    
    print("\n" + "="*60)
    print("🚀 Clash Meta 订阅管理系统")
    print("="*60)
    print(f"📡 访问地址: http://0.0.0.0:{port}")
    print(f"👤 默认账号: admin / admin123")
    print("="*60 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=port)

