"""
数据库模型
"""

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json

db = SQLAlchemy()

# 用户与订阅的多对多关联表
user_subscription = db.Table('user_subscription',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('subscription_id', db.Integer, db.ForeignKey('subscriptions.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)

# 订阅与节点的多对多关联表
subscription_node = db.Table('subscription_node',
    db.Column('subscription_id', db.Integer, db.ForeignKey('subscriptions.id'), primary_key=True),
    db.Column('node_id', db.Integer, db.ForeignKey('nodes.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)


class Admin(db.Model):
    """管理员表"""
    __tablename__ = 'admins'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        """设置密码"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password_hash, password)


class Template(db.Model):
    """配置模板表"""
    __tablename__ = 'templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255))  # 模板描述
    content = db.Column(db.Text, nullable=False)  # YAML模板内容
    is_default = db.Column(db.Boolean, default=False)  # 是否为默认模板
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 关联的订阅分组和用户
    subscriptions = db.relationship('Subscription', backref='template', lazy=True)
    users = db.relationship('User', backref='template', lazy=True)


class Subscription(db.Model):
    """订阅分组表"""
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    subscription_token = db.Column(db.String(64), unique=True, nullable=False)  # 订阅令牌
    template_id = db.Column(db.Integer, db.ForeignKey('templates.id'), nullable=True)  # 使用的模板
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 多对多关系：订阅可以包含多个节点，节点也可以属于多个订阅
    nodes = db.relationship('Node', secondary=subscription_node, back_populates='subscriptions', lazy=True)
    
    # 多对多关系：订阅可以被多个用户使用
    users = db.relationship('User', secondary=user_subscription, back_populates='subscriptions')


class Node(db.Model):
    """节点表"""
    __tablename__ = 'nodes'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    original_name = db.Column(db.String(100))  # 原始名称
    protocol = db.Column(db.String(20), nullable=False)  # ss, vmess, trojan, etc.
    config = db.Column(db.Text, nullable=False)  # JSON格式的节点配置
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=True)  # 保留用于兼容性，但不再使用
    order = db.Column(db.Integer, default=0)  # 排序字段，数字越小越靠前
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 多对多关系：节点可以属于多个订阅
    subscriptions = db.relationship('Subscription', secondary=subscription_node, back_populates='nodes')
    
    def get_config(self):
        """获取节点配置"""
        return json.loads(self.config)
    
    def set_config(self, config_dict):
        """设置节点配置"""
        self.config = json.dumps(config_dict, ensure_ascii=False)


class User(db.Model):
    """用户表（实际上是分组/标签）"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    subscription_token = db.Column(db.String(64), unique=True, nullable=False)  # 订阅令牌
    enabled = db.Column(db.Boolean, default=True)
    remark = db.Column(db.String(255))  # 备注说明
    template_id = db.Column(db.Integer, db.ForeignKey('templates.id'), nullable=True)  # 使用的模板
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 多对多关系：用户可以使用多个订阅，订阅也可以被多个用户使用
    subscriptions = db.relationship('Subscription', secondary=user_subscription, back_populates='users')

