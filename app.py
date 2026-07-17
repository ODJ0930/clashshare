#!/usr/bin/env python3
"""
Web 管理界面主程序
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file, make_response
from models import db, Admin, Subscription, Node, User, UserNode, UserXuiClient, Template, XuiConfig
from parsers import ProxyParser
from generator import ClashConfigGenerator
import os
import secrets
import copy
import base64
from datetime import datetime, timedelta
from functools import wraps
import requests as req
import io
import hashlib
import json
import re
import time
import uuid
from urllib.parse import quote, quote_plus, urlsplit
import yaml

try:
    from yaml import CDumper as YamlDumper
except ImportError:
    from yaml import Dumper as YamlDumper

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///clash_manager.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Session 保持 7 天

db.init_app(app)

SUBSCRIPTION_CACHE_MAX_SIZE = int(os.environ.get('SUBSCRIPTION_CACHE_MAX_SIZE', '256'))
_subscription_cache = {}
_subscription_cache_version = 0


def _dump_yaml_bytes(config):
    """使用 PyYAML C Dumper（可用时）生成 UTF-8 YAML。"""
    yaml_content = yaml.dump(
        config,
        Dumper=YamlDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False
    )
    return yaml_content.encode('utf-8')


def _invalidate_subscription_cache(reason='api-write'):
    """清空订阅缓存。"""
    global _subscription_cache_version
    _subscription_cache_version += 1
    if _subscription_cache:
        _subscription_cache.clear()
    app.logger.debug("subscription cache invalidated: reason=%s version=%s", reason, _subscription_cache_version)


def _get_subscription_cache(cache_type, entity_id):
    cache_key = (cache_type, entity_id)
    cache_entry = _subscription_cache.get(cache_key)
    if not cache_entry:
        return None

    if cache_entry.get('version') != _subscription_cache_version:
        _subscription_cache.pop(cache_key, None)
        return None

    return cache_entry


def _store_subscription_cache(cache_type, entity_id, cache_entry):
    cache_entry['version'] = _subscription_cache_version

    if SUBSCRIPTION_CACHE_MAX_SIZE <= 0:
        return cache_entry

    if len(_subscription_cache) >= SUBSCRIPTION_CACHE_MAX_SIZE:
        oldest_key = next(iter(_subscription_cache))
        _subscription_cache.pop(oldest_key, None)

    _subscription_cache[(cache_type, entity_id)] = cache_entry
    return cache_entry


class XuiApiError(Exception):
    """3x-ui 远程调用错误。"""

    def __init__(self, message, status_code=502, payload=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.payload = payload


def _safe_json_loads(value, fallback=None):
    if fallback is None:
        fallback = {}
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return fallback
    if isinstance(value, str):
        try:
            return yaml.safe_load(value) or fallback
        except Exception:
            return fallback
    return fallback


def _normalize_xui_base_url(base_url):
    return (base_url or '').strip().rstrip('/')


def _normalize_public_host(value):
    raw_value = (value or '').strip()
    if not raw_value:
        return ''
    parsed = urlsplit(raw_value if '://' in raw_value else f'//{raw_value}')
    return (parsed.hostname or raw_value.split('/')[0]).strip()


def _public_host_from_xui_config(config):
    public_host = _normalize_public_host(getattr(config, 'public_host', None))
    if public_host:
        return public_host
    return _normalize_public_host(config.base_url)


def _join_xui_url(base_url, path):
    base_url = _normalize_xui_base_url(base_url)
    if not base_url:
        raise XuiApiError('请先配置 3x-ui 面板地址', 400)

    normalized_path = '/' + path.lstrip('/')

    # 有些用户会把面板地址填成 https://host/panel；此时避免拼出 /panel/panel/api。
    parsed = urlsplit(base_url)
    if parsed.path.rstrip('/').endswith('/panel') and normalized_path.startswith('/panel/'):
        normalized_path = normalized_path[len('/panel'):]

    return f'{base_url}{normalized_path}'


def _get_xui_config(config_id=None, create_default=False):
    if config_id:
        try:
            config_id = int(config_id)
        except (TypeError, ValueError):
            raise XuiApiError('后端 ID 不正确', 400)

        config = XuiConfig.query.get(config_id)
        if not config:
            raise XuiApiError('指定的 3x-ui 后端不存在', 404)
        return config

    config = XuiConfig.query.order_by(XuiConfig.id.asc()).first()
    if not config and create_default:
        config = XuiConfig(name='默认后端', base_url='')
        db.session.add(config)
        db.session.commit()
    return config


def _require_xui_config(config_id=None):
    config = _get_xui_config(config_id)
    if not config:
        raise XuiApiError('请先新增一个 3x-ui 后端', 400)

    _validate_xui_config_ready(config)
    return config


def _validate_xui_config_ready(config):
    if not config.base_url:
        raise XuiApiError('请先保存 3x-ui 面板地址', 400)

    if config.auth_mode == 'token':
        if not config.api_token:
            raise XuiApiError('请先填写 3x-ui API Token', 400)
    elif not config.username or not config.password:
        raise XuiApiError('请先填写 3x-ui 用户名和密码', 400)

    return True


def _get_xui_backend_id(data=None):
    if data is None:
        data = {}

    backend_id = data.get('backend_id') or request.args.get('backend_id')
    if backend_id in (None, ''):
        return None

    try:
        return int(backend_id)
    except (TypeError, ValueError):
        raise XuiApiError('后端 ID 不正确', 400)


def _xui_timeout(config):
    try:
        return max(3, min(int(config.timeout or 15), 60))
    except (TypeError, ValueError):
        return 15


def _xui_success(data):
    return not (isinstance(data, dict) and data.get('success') is False)


def _xui_message(data, default='3x-ui 请求失败'):
    if isinstance(data, dict):
        return data.get('msg') or data.get('message') or default
    return default


def _xui_obj(data):
    if isinstance(data, dict) and 'obj' in data:
        return data.get('obj')
    return data


def _xui_parse_response(response):
    try:
        data = response.json()
    except ValueError:
        data = {'raw': response.text}

    if not response.ok:
        raise XuiApiError(_xui_message(data, f'3x-ui HTTP {response.status_code}'), response.status_code, data)

    if not _xui_success(data):
        raise XuiApiError(_xui_message(data), 400, data)

    return data


def _raise_xui_connection_error(error):
    if isinstance(error, req.exceptions.SSLError):
        raise XuiApiError(
            f'HTTPS 证书校验失败：如果该 3x-ui 后端使用自签证书，请在新增/编辑后端时关闭“验证 HTTPS 证书”后重试。原始错误: {error}',
            502
        )
    raise XuiApiError(f'无法连接 3x-ui: {error}', 502)


def _xui_session(config):
    session_obj = req.Session()
    session_obj.headers.update({'Accept': 'application/json'})

    if config.auth_mode == 'token':
        session_obj.headers.update({'Authorization': f'Bearer {config.api_token}'})
        return session_obj

    login_payload = {
        'username': config.username,
        'password': config.password
    }
    try:
        login_response = session_obj.post(
            _join_xui_url(config.base_url, '/login'),
            json=login_payload,
            timeout=_xui_timeout(config),
            verify=config.verify_ssl
        )
    except req.RequestException as e:
        _raise_xui_connection_error(e)
    _xui_parse_response(login_response)

    try:
        csrf_response = session_obj.get(
            _join_xui_url(config.base_url, '/csrf-token'),
            timeout=_xui_timeout(config),
            verify=config.verify_ssl
        )
        csrf_data = _xui_parse_response(csrf_response)
        csrf_token = _xui_obj(csrf_data)
        if csrf_token:
            session_obj.headers.update({'X-CSRF-Token': str(csrf_token)})
    except req.RequestException as e:
        _raise_xui_connection_error(e)
    except XuiApiError:
        # 老版本 3x-ui 可能没有 CSRF 端点；后续请求会给出真实错误。
        pass

    return session_obj


def _xui_request(method, path, json_body=None, form_body=None, params=None, config_id=None):
    config = _require_xui_config(config_id)
    session_obj = _xui_session(config)
    try:
        response = session_obj.request(
            method,
            _join_xui_url(config.base_url, path),
            json=json_body,
            data=form_body,
            params=params,
            timeout=_xui_timeout(config),
            verify=config.verify_ssl
        )
    except req.RequestException as e:
        _raise_xui_connection_error(e)

    return _xui_parse_response(response)


def _xui_request_with_config(config, method, path, json_body=None, form_body=None, params=None):
    _validate_xui_config_ready(config)
    session_obj = _xui_session(config)
    try:
        response = session_obj.request(
            method,
            _join_xui_url(config.base_url, path),
            json=json_body,
            data=form_body,
            params=params,
            timeout=_xui_timeout(config),
            verify=config.verify_ssl
        )
    except req.RequestException as e:
        _raise_xui_connection_error(e)

    return _xui_parse_response(response)


def _xui_error_response(error):
    return jsonify({
        'success': False,
        'message': error.message,
        'remote_status': error.status_code,
        'payload': error.payload
    }), error.status_code if error.status_code and error.status_code < 500 else 502


def _apply_xui_config_data(config, data):
    name = (data.get('name') or config.name or '').strip()
    if not name:
        raise XuiApiError('后端名称不能为空', 400)

    base_url = _normalize_xui_base_url(data.get('base_url', config.base_url))
    auth_mode = data.get('auth_mode') or config.auth_mode or 'token'
    if auth_mode not in {'token', 'password'}:
        raise XuiApiError('认证方式只能是 token 或 password', 400)

    timeout = data.get('timeout', config.timeout or 15)
    try:
        timeout = max(3, min(int(timeout), 60))
    except (TypeError, ValueError):
        raise XuiApiError('超时时间必须是 3-60 秒的整数', 400)

    config.name = name
    config.base_url = base_url
    if 'public_host' in data:
        config.public_host = _normalize_public_host(data.get('public_host'))
    elif not getattr(config, 'public_host', None):
        config.public_host = _normalize_public_host(base_url)
    config.auth_mode = auth_mode
    config.username = (data.get('username') or config.username or '').strip()
    config.verify_ssl = bool(data.get('verify_ssl', True))
    config.timeout = timeout

    if data.get('password'):
        config.password = data.get('password')
    if data.get('clear_password'):
        config.password = None

    if data.get('api_token'):
        config.api_token = data.get('api_token').strip()
    if data.get('clear_api_token'):
        config.api_token = None

    return config


def _gb_to_bytes(value, default=0):
    if value in (None, ''):
        return default
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        raise XuiApiError('流量上限必须是数字', 400)
    if numeric_value <= 0:
        return 0
    return int(numeric_value * 1024 * 1024 * 1024)


def _bytes_to_gb(value):
    try:
        bytes_value = int(value or 0)
    except (TypeError, ValueError):
        bytes_value = 0
    if bytes_value <= 0:
        return 0
    return round(bytes_value / 1024 / 1024 / 1024, 3)


def _int_or_zero(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _coerce_ms_timestamp(value, default=0):
    if value in (None, ''):
        return int(default or 0)
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        raise XuiApiError('到期时间必须是毫秒时间戳', 400)
    return max(0, timestamp)


def _unix_seconds_from_ms(value):
    try:
        ms = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return int(ms / 1000) if ms > 0 else 0


def _expiry_from_days(value, default=None):
    if value in (None, ''):
        return default
    try:
        days = int(value)
    except (TypeError, ValueError):
        raise XuiApiError('有效期天数必须是整数', 400)
    if days <= 0:
        return 0
    return int((time.time() + days * 86400) * 1000)


def _parse_advanced_payload(raw_value):
    if not raw_value:
        return None
    if isinstance(raw_value, dict):
        return raw_value
    try:
        parsed = yaml.safe_load(raw_value)
    except Exception as e:
        raise XuiApiError(f'高级 JSON/YAML 解析失败: {e}', 400)
    if not isinstance(parsed, dict):
        raise XuiApiError('高级配置必须是一个对象', 400)
    return parsed


def _coerce_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'on', 'enable', 'enabled'}
    return bool(value)


def _coerce_port(value, default=None):
    if value in (None, ''):
        if default is None:
            raise XuiApiError('端口不能为空', 400)
        value = default
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise XuiApiError('端口必须是 1-65535 的整数', 400)
    if port < 1 or port > 65535:
        raise XuiApiError('端口必须在 1-65535 之间', 400)
    return port


XUI_INBOUND_PROTOCOLS = {
    'vless',
    'vmess',
    'trojan',
    'shadowsocks',
    'wireguard',
    'hysteria2',
    'http',
    'socks',
    'dokodemo-door',
    'tun',
}

XUI_INBOUND_NETWORKS = {'tcp', 'kcp', 'ws', 'grpc', 'httpupgrade', 'xhttp'}
XUI_INBOUND_SECURITIES = {'none', 'tls', 'xtls', 'reality'}
XUI_INBOUND_RUNTIME_FIELDS = {'id', 'up', 'down', 'clientStats', 'raw'}
XUI_SUBSCRIPTION_PROTOCOLS = {'vless', 'vmess', 'trojan', 'shadowsocks', 'hysteria2'}
XUI_SUBSCRIPTION_NETWORKS = {'tcp', 'ws', 'grpc', 'httpupgrade', 'xhttp'}


def _new_reality_short_id():
    return secrets.token_hex(4)


def _normalize_inbound_object_field(payload, key, default):
    value = payload.get(key)
    if isinstance(value, str):
        value = _safe_json_loads(value, default)
    if value in (None, ''):
        value = copy.deepcopy(default)
    if not isinstance(value, dict):
        raise XuiApiError(f'{key} 必须是对象，不能是空值或数组', 400)
    payload[key] = value
    return value


def _strip_inbound_runtime_fields(payload):
    for key in XUI_INBOUND_RUNTIME_FIELDS:
        payload.pop(key, None)
    return payload


def _merge_existing_inbound_payload(payload, existing, preserve_clients=True):
    payload = copy.deepcopy(payload or {})
    existing = copy.deepcopy(existing or {})
    _strip_inbound_runtime_fields(payload)
    _strip_inbound_runtime_fields(existing)

    if existing.get('tag') and not payload.get('tag'):
        payload['tag'] = existing.get('tag')

    existing_settings = _safe_json_loads(existing.get('settings'), {})
    payload_settings = _safe_json_loads(payload.get('settings'), {})
    if preserve_clients and isinstance(existing_settings, dict) and isinstance(payload_settings, dict):
        for key in ('clients', 'accounts', 'peers'):
            existing_value = existing_settings.get(key)
            payload_value = payload_settings.get(key)
            if isinstance(existing_value, list) and existing_value and (not isinstance(payload_value, list) or not payload_value):
                payload_settings[key] = existing_value
        payload['settings'] = payload_settings

    return payload


def _validate_inbound_payload(payload):
    if not isinstance(payload, dict):
        raise XuiApiError('入站节点配置必须是对象', 400)

    required_fields = ['enable', 'remark', 'port', 'protocol', 'settings', 'streamSettings', 'sniffing']
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise XuiApiError(f'入站节点配置不完整，缺少字段: {", ".join(missing)}', 400)

    remark = str(payload.get('remark') or '').strip()
    if not remark:
        raise XuiApiError('节点名称不能为空', 400)
    payload['remark'] = remark
    payload['port'] = _coerce_port(payload.get('port'))
    payload['enable'] = _coerce_bool(payload.get('enable'), True)
    payload['listen'] = payload.get('listen') or ''
    payload['protocol'] = str(payload.get('protocol') or '').strip().lower()
    if not payload['protocol']:
        raise XuiApiError('协议不能为空', 400)
    if payload['protocol'] not in XUI_INBOUND_PROTOCOLS:
        raise XuiApiError(f'不支持的入站协议: {payload["protocol"]}', 400)
    try:
        payload['total'] = int(payload.get('total') or 0)
        payload['expiryTime'] = int(payload.get('expiryTime') or 0)
        payload['reset'] = int(payload.get('reset') or 0)
    except (TypeError, ValueError):
        raise XuiApiError('total、expiryTime 和 reset 必须是数字', 400)

    settings = _normalize_inbound_object_field(payload, 'settings', {'clients': []})
    stream_settings = _normalize_inbound_object_field(payload, 'streamSettings', {})
    _normalize_inbound_object_field(payload, 'sniffing', {
        'enabled': True,
        'destOverride': ['http', 'tls', 'quic', 'fakedns'],
        'metadataOnly': False,
        'routeOnly': False
    })

    if 'clients' in settings and not isinstance(settings.get('clients'), list):
        raise XuiApiError('settings.clients 必须是数组', 400)
    if 'network' not in stream_settings:
        stream_settings['network'] = 'tcp'
    if not isinstance(stream_settings.get('network'), str):
        raise XuiApiError('streamSettings.network 必须是字符串', 400)
    stream_settings['network'] = stream_settings.get('network').strip().lower() or 'tcp'
    if stream_settings['network'] not in XUI_INBOUND_NETWORKS:
        raise XuiApiError(f'不支持的传输方式: {stream_settings["network"]}', 400)

    if 'security' not in stream_settings:
        stream_settings['security'] = 'none'
    if not isinstance(stream_settings.get('security'), str):
        raise XuiApiError('streamSettings.security 必须是字符串', 400)
    stream_settings['security'] = stream_settings.get('security').strip().lower() or 'none'
    if stream_settings['security'] not in XUI_INBOUND_SECURITIES:
        raise XuiApiError(f'不支持的安全类型: {stream_settings["security"]}', 400)

    if stream_settings['security'] == 'reality':
        reality_settings = stream_settings.get('realitySettings')
        if not isinstance(reality_settings, dict):
            raise XuiApiError('Reality 配置缺少 streamSettings.realitySettings', 400)
        short_ids = reality_settings.get('shortIds')
        if isinstance(short_ids, str):
            short_ids = [item.strip() for item in short_ids.split(',') if item.strip()]
            reality_settings['shortIds'] = short_ids
        valid_short_ids = [str(item).strip() for item in short_ids or [] if str(item or '').strip()] if isinstance(short_ids, list) else []
        if not valid_short_ids:
            raise XuiApiError('Reality 配置 shortIds 不能为空，请点击“随机”生成 Short IDs 后再保存', 400)
        reality_settings['shortIds'] = valid_short_ids

    return payload


def _build_existing_inbound_update_payload(data, existing):
    structural_fields = {'protocol', 'network', 'security', 'settings', 'streamSettings', 'sniffing'}
    requested_structural = structural_fields.intersection(data.keys())
    if requested_structural:
        raise XuiApiError('基础编辑只允许修改名称、端口、启用、流量和到期；协议/传输/TLS/Reality 等结构变更请粘贴完整高级 payload。', 400)

    payload = copy.deepcopy(existing or {})
    for readonly_key in ('clientStats', 'raw'):
        payload.pop(readonly_key, None)

    payload['settings'] = _safe_json_loads(payload.get('settings'), {'clients': []})
    payload['streamSettings'] = _safe_json_loads(payload.get('streamSettings'), {})
    payload['sniffing'] = _safe_json_loads(payload.get('sniffing'), {
        'enabled': True,
        'destOverride': ['http', 'tls', 'quic', 'fakedns'],
        'metadataOnly': False,
        'routeOnly': False
    })
    if 'enable' not in payload:
        payload['enable'] = True

    if data.get('remark') is not None:
        payload['remark'] = (data.get('remark') or '').strip()
    if data.get('listen') is not None:
        payload['listen'] = data.get('listen') or ''
    if data.get('port') not in (None, ''):
        payload['port'] = _coerce_port(data.get('port'), payload.get('port'))
    if 'enable' in data:
        payload['enable'] = _coerce_bool(data.get('enable'), payload.get('enable', True))
    if 'expiry_time' in data:
        payload['expiryTime'] = _coerce_ms_timestamp(data.get('expiry_time'), payload.get('expiryTime', 0))
    elif 'expiry_days' in data:
        payload['expiryTime'] = _expiry_from_days(data.get('expiry_days'), payload.get('expiryTime', 0))
    if 'total_gb' in data:
        payload['total'] = _gb_to_bytes(data.get('total_gb'), payload.get('total', 0))
    if 'reset' in data:
        payload['reset'] = _int_or_zero(data.get('reset'))

    return _validate_inbound_payload(payload)


def _default_stream_settings(network, security, data):
    network = (network or 'tcp').lower()
    security = (security or 'none').lower()
    stream = {
        'network': network,
        'security': security
    }

    accept_proxy_protocol = _coerce_bool(data.get('accept_proxy_protocol'), False)

    if network == 'tcp':
        stream['tcpSettings'] = {
            'acceptProxyProtocol': accept_proxy_protocol,
            'header': {
                'type': 'http' if _coerce_bool(data.get('http_obfuscation'), False) else 'none'
            }
        }
    elif network == 'kcp':
        stream['kcpSettings'] = {
            'mtu': int(data.get('kcp_mtu') or 1350),
            'tti': int(data.get('kcp_tti') or 20),
            'uplinkCapacity': int(data.get('kcp_uplink') or 5),
            'downlinkCapacity': int(data.get('kcp_downlink') or 20),
            'congestion': _coerce_bool(data.get('kcp_congestion'), False),
            'readBufferSize': int(data.get('kcp_read_buffer') or 2),
            'writeBufferSize': int(data.get('kcp_write_buffer') or 2),
            'header': {'type': data.get('kcp_header') or 'none'}
        }
    elif network == 'ws':
        stream['wsSettings'] = {
            'acceptProxyProtocol': accept_proxy_protocol,
            'path': data.get('path') or '/',
            'host': data.get('host') or '',
            'headers': {'Host': data.get('host') or ''} if data.get('host') else {}
        }
    elif network == 'grpc':
        stream['grpcSettings'] = {
            'serviceName': data.get('service_name') or '',
            'multiMode': False
        }
    elif network == 'httpupgrade':
        stream['httpupgradeSettings'] = {
            'acceptProxyProtocol': accept_proxy_protocol,
            'path': data.get('path') or '/',
            'host': data.get('host') or '',
            'headers': {'Host': data.get('host') or ''} if data.get('host') else {}
        }
    elif network == 'xhttp':
        stream['xhttpSettings'] = {
            'path': data.get('path') or '/',
            'host': data.get('host') or '',
            'mode': data.get('xhttp_mode') or 'auto',
            'extra': _safe_json_loads(data.get('xhttp_extra'), {})
        }

    if _coerce_bool(data.get('sockopt_enabled'), False):
        stream['sockopt'] = {
            'tcpFastOpen': False,
            'tproxy': 'off',
            'domainStrategy': 'AsIs',
            'dialerProxy': ''
        }

    if security == 'tls':
        stream['tlsSettings'] = {
            'serverName': data.get('sni') or '',
            'minVersion': '1.2',
            'maxVersion': '1.3',
            'cipherSuites': '',
            'certificates': [],
            'alpn': ['http/1.1'],
            'settings': {}
        }
    elif security == 'xtls':
        stream['xtlsSettings'] = {
            'serverName': data.get('sni') or '',
            'minVersion': '1.2',
            'maxVersion': '1.3',
            'cipherSuites': '',
            'certificates': [],
            'alpn': ['http/1.1'],
            'settings': {}
        }
    elif security == 'reality':
        stream['realitySettings'] = {
            'show': False,
            'xver': 0,
            'dest': data.get('reality_dest') or 'www.cloudflare.com:443',
            'serverNames': [data.get('sni') or 'www.cloudflare.com'],
            'privateKey': data.get('reality_private_key') or '',
            'minClientVer': '',
            'maxClientVer': '',
            'maxTimeDiff': 0,
            'shortIds': [data.get('reality_short_id') or _new_reality_short_id()]
        }

    return stream


def _default_inbound_settings(protocol, data):
    protocol = (protocol or 'vless').lower()

    if protocol == 'vless':
        return {
            'clients': [],
            'decryption': data.get('decryption') or 'none',
            'encryption': data.get('encryption') or 'none',
            'fallbacks': _safe_json_loads(data.get('fallbacks'), [])
        }
    if protocol == 'vmess':
        return {
            'clients': [],
            'disableInsecureEncryption': _coerce_bool(data.get('disable_insecure_encryption'), False)
        }
    if protocol == 'trojan':
        return {
            'clients': [],
            'fallbacks': _safe_json_loads(data.get('fallbacks'), [])
        }
    if protocol == 'shadowsocks':
        return {
            'method': data.get('ss_method') or 'aes-256-gcm',
            'password': data.get('ss_password') or secrets.token_urlsafe(16),
            'network': data.get('ss_network') or 'tcp,udp',
            'clients': []
        }
    if protocol == 'wireguard':
        return {
            'secretKey': data.get('wg_secret_key') or secrets.token_urlsafe(32),
            'address': [data.get('wg_address') or '10.0.0.1/24'],
            'peers': _safe_json_loads(data.get('wg_peers'), []),
            'mtu': int(data.get('wg_mtu') or 1420),
            'kernelMode': _coerce_bool(data.get('wg_kernel_mode'), False),
            'workers': int(data.get('wg_workers') or 0)
        }
    if protocol == 'hysteria2':
        return {
            'clients': [],
            'masquerade': data.get('hy_masquerade') or '',
            'up_mbps': int(data.get('hy_up_mbps') or 100),
            'down_mbps': int(data.get('hy_down_mbps') or 100),
            'ignoreClientBandwidth': _coerce_bool(data.get('hy_ignore_bandwidth'), False)
        }
    if protocol == 'http':
        return {
            'accounts': _safe_json_loads(data.get('accounts'), []),
            'allowTransparent': _coerce_bool(data.get('allow_transparent'), False),
            'userLevel': int(data.get('user_level') or 0)
        }
    if protocol == 'socks':
        return {
            'auth': data.get('socks_auth') or 'noauth',
            'accounts': _safe_json_loads(data.get('accounts'), []),
            'udp': _coerce_bool(data.get('socks_udp'), True),
            'ip': data.get('socks_ip') or '127.0.0.1',
            'userLevel': int(data.get('user_level') or 0)
        }
    if protocol == 'dokodemo-door':
        return {
            'address': data.get('target_address') or '',
            'port': int(data.get('target_port') or 0),
            'network': data.get('target_network') or 'tcp,udp',
            'followRedirect': _coerce_bool(data.get('follow_redirect'), False),
            'userLevel': int(data.get('user_level') or 0)
        }
    if protocol == 'tun':
        return {
            'mtu': int(data.get('tun_mtu') or 1500),
            'stack': data.get('tun_stack') or 'system',
            'endpointIndependentNat': _coerce_bool(data.get('tun_nat'), False),
            'sniff': _coerce_bool(data.get('tun_sniff'), True)
        }

    return {'clients': []}


def _build_inbound_payload(data, existing=None):
    full_payload = data.get('inbound_payload') or data.get('payload')
    if full_payload is not None:
        parsed_payload = _parse_advanced_payload(full_payload) if isinstance(full_payload, str) else full_payload
        if not isinstance(parsed_payload, dict):
            raise XuiApiError('完整入站 payload 必须是对象', 400)
        if existing:
            parsed_payload = _merge_existing_inbound_payload(
                parsed_payload,
                existing,
                _coerce_bool(data.get('preserve_clients'), True)
            )
        else:
            parsed_payload = _strip_inbound_runtime_fields(copy.deepcopy(parsed_payload))
        return _validate_inbound_payload(parsed_payload)

    advanced_payload = _parse_advanced_payload(data.get('advanced_payload'))
    if advanced_payload is not None:
        if existing:
            advanced_payload = _merge_existing_inbound_payload(
                advanced_payload,
                existing,
                _coerce_bool(data.get('preserve_clients'), True)
            )
        return _validate_inbound_payload(copy.deepcopy(advanced_payload))

    existing = existing or {}

    if existing:
        return _build_existing_inbound_update_payload(data, existing)

    protocol = data.get('protocol') or existing.get('protocol') or 'vless'
    network = data.get('network') or _safe_json_loads(existing.get('streamSettings')).get('network') or 'tcp'
    security = data.get('security') or _safe_json_loads(existing.get('streamSettings')).get('security') or 'none'

    if protocol not in XUI_INBOUND_PROTOCOLS:
        raise XuiApiError(f'不支持的入站协议: {protocol}', 400)
    if network not in XUI_INBOUND_NETWORKS:
        raise XuiApiError(f'不支持的传输方式: {network}', 400)
    if security not in XUI_INBOUND_SECURITIES:
        raise XuiApiError(f'不支持的安全类型: {security}', 400)

    settings = _default_inbound_settings(protocol, data)

    payload = {
        'enable': _coerce_bool(data.get('enable'), existing.get('enable', True)),
        'remark': (data.get('remark') or existing.get('remark') or 'New Inbound').strip(),
        'listen': data.get('listen', existing.get('listen', '')) or '',
        'port': _coerce_port(data.get('port'), existing.get('port') or 443),
        'protocol': protocol,
        'expiryTime': _expiry_from_days(data.get('expiry_days'), existing.get('expiryTime', 0)),
        'total': _gb_to_bytes(data.get('total_gb'), existing.get('total', 0)),
        'settings': settings,
        'streamSettings': _default_stream_settings(network, security, data),
        'sniffing': {
            'enabled': bool(data.get('sniffing_enabled', True)),
            'destOverride': ['http', 'tls', 'quic', 'fakedns'],
            'metadataOnly': False,
            'routeOnly': False
        }
    }

    return _validate_inbound_payload(payload)


def _build_client_payload(data, existing=None):
    existing = existing or {}
    client = dict(existing)
    for runtime_key in ('traffic', 'inboundIds', 'inbound_ids', 'inboundNames', 'remainingBytes', 'online', 'raw'):
        client.pop(runtime_key, None)

    if data.get('email'):
        client['email'] = data.get('email')
    if data.get('sub_id'):
        client['subId'] = data.get('sub_id')
    if data.get('comment') is not None:
        client['comment'] = data.get('comment') or ''
    if data.get('flow') is not None:
        client['flow'] = data.get('flow') or ''
    if data.get('limit_ip') not in (None, ''):
        client['limitIp'] = int(data.get('limit_ip'))
    elif 'limitIp' not in client:
        client['limitIp'] = 0
    if data.get('tg_id') not in (None, ''):
        client['tgId'] = int(data.get('tg_id'))
    elif 'tgId' not in client:
        client['tgId'] = 0
    if data.get('enable') is not None:
        client['enable'] = bool(data.get('enable'))
    elif 'enable' not in client:
        client['enable'] = True

    if 'total_gb' in data:
        client['totalGB'] = _gb_to_bytes(data.get('total_gb'), client.get('totalGB', 0))
    elif 'totalGB' not in client:
        client['totalGB'] = 0

    if 'expiry_time' in data:
        client['expiryTime'] = _coerce_ms_timestamp(data.get('expiry_time'), client.get('expiryTime', 0))
    elif 'expiry_days' in data:
        client['expiryTime'] = _expiry_from_days(data.get('expiry_days'), client.get('expiryTime', 0))
    elif 'expiryTime' not in client:
        client['expiryTime'] = 0

    if not client.get('email'):
        raise XuiApiError('客户端 Email 不能为空', 400)
    if client.get('id') not in (None, '') and not isinstance(client.get('id'), str):
        client['id'] = str(client.get('id'))

    return client


def _normalize_xui_inbound(inbound):
    settings = _safe_json_loads(inbound.get('settings'), {})
    stream_settings = _safe_json_loads(inbound.get('streamSettings'), {})
    sniffing = _safe_json_loads(inbound.get('sniffing'), {})
    client_stats = inbound.get('clientStats') or []
    clients = settings.get('clients') if isinstance(settings, dict) else []
    if not isinstance(clients, list):
        clients = []

    return {
        'id': inbound.get('id'),
        'remark': inbound.get('remark') or inbound.get('tag') or f"Inbound {inbound.get('id')}",
        'tag': inbound.get('tag') or '',
        'protocol': inbound.get('protocol') or '',
        'port': inbound.get('port') or 0,
        'listen': inbound.get('listen') or '',
        'enable': bool(inbound.get('enable', True)),
        'total': inbound.get('total') or 0,
        'up': inbound.get('up') or 0,
        'down': inbound.get('down') or 0,
        'expiryTime': inbound.get('expiryTime') or 0,
        'reset': inbound.get('reset') or 0,
        'client_count': len(clients) or len(client_stats),
        'network': stream_settings.get('network') if isinstance(stream_settings, dict) else '',
        'security': stream_settings.get('security') if isinstance(stream_settings, dict) else '',
        'settings': settings,
        'streamSettings': stream_settings,
        'sniffing': sniffing,
        'raw': inbound
    }


def _normalize_xui_client(client, inbound_map=None, online_emails=None):
    inbound_map = inbound_map or {}
    online_emails = online_emails or set()
    traffic = client.get('traffic') or {}
    inbound_ids = client.get('inboundIds') or client.get('inbound_ids') or []
    if not isinstance(inbound_ids, list):
        inbound_ids = []

    total = client.get('totalGB') or client.get('total') or 0
    up = traffic.get('up') if isinstance(traffic, dict) else client.get('up')
    down = traffic.get('down') if isinstance(traffic, dict) else client.get('down')
    up = up or 0
    down = down or 0
    used = up + down

    inbound_names = []
    for inbound_id in inbound_ids:
        inbound = inbound_map.get(inbound_id)
        inbound_names.append(inbound.get('remark') if inbound else str(inbound_id))

    return {
        'id': client.get('id'),
        'email': client.get('email') or '',
        'subId': client.get('subId') or '',
        'enable': bool(client.get('enable', True)),
        'totalGB': total,
        'expiryTime': client.get('expiryTime') or 0,
        'limitIp': client.get('limitIp') or 0,
        'comment': client.get('comment') or '',
        'flow': client.get('flow') or '',
        'traffic': {'up': up, 'down': down, 'used': used},
        'remainingBytes': max(total - used, 0) if total else 0,
        'inboundIds': inbound_ids,
        'inboundNames': inbound_names,
        'online': (client.get('email') or '') in online_emails,
        'raw': client
    }


def _json_dump(value):
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _coerce_int_list(value):
    if value in (None, ''):
        return []
    if isinstance(value, str):
        value = [item.strip() for item in value.split(',')]
    if not isinstance(value, list):
        raise XuiApiError('ID 列表格式不正确', 400)

    result = []
    seen = set()
    for item in value:
        try:
            item_id = int(item)
        except (TypeError, ValueError):
            raise XuiApiError('ID 必须是数字', 400)
        if item_id > 0 and item_id not in seen:
            seen.add(item_id)
            result.append(item_id)
    return result


def _xui_identifier_slug(value):
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', value or '').strip('-').lower()
    return slug or 'user'


def _make_user_xui_client_email(user, inbound_id):
    return f'{_xui_identifier_slug(user.username)}-u{user.id}-in{int(inbound_id)}'


def _make_user_xui_sub_id(user, inbound_id):
    return f'{_make_user_xui_client_email(user, inbound_id)}-sub'


def _xui_fetch_client_state(backend_id):
    inbounds_data = _xui_request('GET', '/panel/api/inbounds/options', config_id=backend_id)
    inbound_options = _xui_obj(inbounds_data) or []
    normalized_inbounds = [_normalize_xui_inbound(item) for item in inbound_options]
    inbound_map = {
        int(item['id']): item
        for item in normalized_inbounds
        if item.get('id') is not None
    }

    clients_data = _xui_request('GET', '/panel/api/clients/list', config_id=backend_id)
    clients = _xui_obj(clients_data) or []
    try:
        online_data = _xui_request('POST', '/panel/api/clients/onlines', config_id=backend_id)
        online_obj = _xui_obj(online_data) or []
        online_emails = set(online_obj if isinstance(online_obj, list) else [])
    except XuiApiError:
        online_emails = set()

    normalized_clients = [_normalize_xui_client(item, inbound_map, online_emails) for item in clients]
    client_map = {
        item['email']: item
        for item in normalized_clients
        if item.get('email')
    }
    return inbound_map, client_map


def _xui_fetch_inbound_by_id(backend_id, inbound_id):
    try:
        target_id = int(inbound_id or 0)
    except (TypeError, ValueError):
        return None
    if target_id <= 0:
        return None

    last_error = None
    for path in ('/panel/api/inbounds/options', '/panel/api/inbounds/list'):
        try:
            data = _xui_request('GET', path, config_id=backend_id)
        except XuiApiError as e:
            last_error = e
            continue
        for item in _xui_obj(data) or []:
            inbound = _normalize_xui_inbound(item)
            if int(inbound.get('id') or 0) == target_id:
                return inbound

    if last_error:
        raise last_error
    return None


def _xui_fetch_inbound_raw_by_id(backend_id, inbound_id):
    data = _xui_request('GET', f'/panel/api/inbounds/get/{int(inbound_id)}', config_id=backend_id)
    inbound = _xui_obj(data) or {}
    if not inbound:
        raise XuiApiError(f'入站不存在: {inbound_id}', 404)
    return inbound


def _xui_fetch_inbound_list(backend_id):
    data = _xui_request('GET', '/panel/api/inbounds/list', config_id=backend_id)
    inbounds = _xui_obj(data) or []
    return [_normalize_xui_inbound(item) for item in inbounds]


def _extract_xui_created_inbound_id(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    if isinstance(value, dict):
        for key in ('id', 'inboundId', 'inbound_id'):
            found = _extract_xui_created_inbound_id(value.get(key))
            if found:
                return found
        for key in ('obj', 'data', 'payload', 'inbound'):
            found = _extract_xui_created_inbound_id(value.get(key))
            if found:
                return found
    if isinstance(value, list) and len(value) == 1:
        return _extract_xui_created_inbound_id(value[0])
    return None


def _find_created_xui_inbound(before_inbounds, after_inbounds, inbound_payload, add_response):
    created_id = _extract_xui_created_inbound_id(add_response)
    if created_id:
        for inbound in after_inbounds:
            if int(inbound.get('id') or 0) == created_id:
                return inbound

    before_ids = {int(item.get('id') or 0) for item in before_inbounds if item.get('id')}
    new_inbounds = [
        item for item in after_inbounds
        if item.get('id') and int(item.get('id') or 0) not in before_ids
    ]
    if len(new_inbounds) == 1:
        return new_inbounds[0]

    expected_port = int(inbound_payload.get('port') or 0)
    expected_remark = (inbound_payload.get('remark') or '').strip()
    for candidates in (new_inbounds, after_inbounds):
        matched = [
            item for item in candidates
            if int(item.get('port') or 0) == expected_port
            and (item.get('remark') or '').strip() == expected_remark
        ]
        if len(matched) == 1:
            return matched[0]

    raise XuiApiError('入站已创建，但无法识别新入站 ID，请刷新后重试', 502)


def _xui_inbound_missing_limit_fields(inbound):
    raw = inbound.get('raw') if isinstance(inbound, dict) else inbound
    if not isinstance(raw, dict):
        return True
    return any(field not in raw for field in ('enable', 'total', 'expiryTime', 'reset'))


def _xui_inbound_cache_raw(mapping, inbound):
    raw = inbound.get('raw') if isinstance(inbound, dict) and isinstance(inbound.get('raw'), dict) else inbound
    raw = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    existing = _safe_json_loads(mapping.raw_inbound, {})
    if isinstance(existing, dict):
        for field in ('enable', 'total', 'up', 'down', 'expiryTime', 'reset'):
            if field not in raw and field in existing:
                raw[field] = existing[field]
    return raw


def _cache_user_xui_mapping(mapping, inbound=None, client=None, error=None):
    if inbound:
        raw_inbound = _xui_inbound_cache_raw(mapping, inbound)
        mapping.inbound_name = inbound.get('remark') or mapping.inbound_name
        mapping.inbound_protocol = inbound.get('protocol') or mapping.inbound_protocol
        mapping.traffic_limit = int(raw_inbound.get('total') or inbound.get('total') or 0)
        mapping.expiry_time = int(raw_inbound.get('expiryTime') or inbound.get('expiryTime') or 0)
        mapping.raw_inbound = _json_dump(raw_inbound)

    if client:
        traffic = client.get('traffic') or {}
        mapping.sub_id = client.get('subId') or mapping.sub_id
        mapping.comment = client.get('comment') or mapping.comment
        mapping.flow = client.get('flow') or ''
        mapping.limit_ip = int(client.get('limitIp') or 0)
        mapping.enabled = bool(client.get('enable', True))
        mapping.online = bool(client.get('online', False))
        mapping.traffic_up = int(traffic.get('up') or 0)
        mapping.traffic_down = int(traffic.get('down') or 0)
        mapping.traffic_used = int(traffic.get('used') or 0)
        mapping.raw_client = _json_dump(client.get('raw') or client)
        mapping.last_error = None
    elif error:
        mapping.last_error = str(error)

    mapping.last_sync_at = datetime.utcnow()
    return mapping


def _user_xui_inbound_state(mapping):
    raw_inbound = _safe_json_loads(mapping.raw_inbound, {})
    inbound = _normalize_xui_inbound(raw_inbound) if isinstance(raw_inbound, dict) and raw_inbound else {}
    up = _int_or_zero(inbound.get('up'))
    down = _int_or_zero(inbound.get('down'))
    used = up + down
    total = _int_or_zero(inbound.get('total'))
    expiry_time = _int_or_zero(inbound.get('expiryTime'))
    now_ms = int(time.time() * 1000)

    return {
        'enable': bool(inbound.get('enable', True)),
        'total': total,
        'up': up,
        'down': down,
        'used': used,
        'remaining': max(total - used, 0) if total else 0,
        'expiry_time': expiry_time,
        'reset': _int_or_zero(inbound.get('reset')),
        'expired': bool(expiry_time and expiry_time <= now_ms),
        'exhausted': bool(total and used >= total)
    }


def _strip_user_xui_client_limits(client_payload):
    for key in ('totalGB', 'total', 'expiryTime'):
        client_payload.pop(key, None)
    return client_payload


def _user_xui_inbound_limit_update_data(data):
    update = {}
    if 'total_gb' in data:
        update['total_gb'] = data.get('total_gb')
    if 'expiry_time' in data:
        update['expiry_time'] = data.get('expiry_time')
    elif 'expiry_days' in data:
        update['expiry_days'] = data.get('expiry_days')
    if 'reset' in data:
        update['reset'] = data.get('reset')
    return update


def _update_user_xui_inbound_limits(backend_id, inbound_id, data, current_inbound=None):
    update_data = _user_xui_inbound_limit_update_data(data)
    if not update_data:
        return current_inbound

    current_raw = None
    if isinstance(current_inbound, dict):
        current_raw = current_inbound.get('raw') if isinstance(current_inbound.get('raw'), dict) else current_inbound
    required_fields = {'enable', 'remark', 'port', 'protocol', 'settings', 'streamSettings', 'sniffing'}
    if not current_raw or any(field not in current_raw for field in required_fields):
        current_raw = _xui_fetch_inbound_raw_by_id(backend_id, inbound_id)

    payload = _build_inbound_payload(update_data, current_raw)
    _xui_request(
        'POST',
        f'/panel/api/inbounds/update/{int(inbound_id)}',
        json_body=payload,
        config_id=backend_id
    )
    return _normalize_xui_inbound(payload)


def _sync_user_xui_clients(user, raise_errors=False):
    mappings = list(getattr(user, 'xui_clients', []) or [])
    if not mappings:
        return []

    by_backend = {}
    for mapping in mappings:
        by_backend.setdefault(mapping.backend_id, []).append(mapping)

    for backend_id, backend_mappings in by_backend.items():
        try:
            inbound_map, client_map = _xui_fetch_client_state(backend_id)
            full_inbound_cache = {}
            for mapping in backend_mappings:
                inbound_id = int(mapping.inbound_id or 0)
                inbound = inbound_map.get(inbound_id)
                if inbound and _xui_inbound_missing_limit_fields(inbound):
                    try:
                        if inbound_id not in full_inbound_cache:
                            full_inbound_cache[inbound_id] = _normalize_xui_inbound(
                                _xui_fetch_inbound_raw_by_id(backend_id, inbound_id)
                            )
                        inbound = full_inbound_cache[inbound_id]
                    except XuiApiError as e:
                        app.logger.warning(
                            "failed to fetch full 3x-ui inbound during user sync: backend=%s inbound=%s error=%s",
                            backend_id,
                            inbound_id,
                            e.message
                        )
                client = client_map.get(mapping.client_email)
                error = None if client else '远端客户端不存在'
                _cache_user_xui_mapping(mapping, inbound, client, error)
        except XuiApiError as e:
            if raise_errors:
                raise
            for mapping in backend_mappings:
                _cache_user_xui_mapping(mapping, error=e.message)

    _recalculate_user_traffic_used(user)
    db.session.commit()
    return mappings


def _sync_user_xui_clients_if_stale(user, max_age_seconds=60):
    mappings = list(getattr(user, 'xui_clients', []) or [])
    if not mappings:
        return
    now = time.time()
    stale = any(
        not mapping.last_sync_at or now - mapping.last_sync_at.timestamp() > max_age_seconds
        for mapping in mappings
    )
    if not stale:
        return
    try:
        _sync_user_xui_clients(user, raise_errors=False)
    except Exception as e:
        app.logger.warning("best-effort 3x-ui user sync failed: %s", e)


def _active_user_xui_clients(user):
    result = []
    for mapping in getattr(user, 'xui_clients', []) or []:
        if not mapping.enabled:
            continue
        inbound_state = _user_xui_inbound_state(mapping)
        if not inbound_state['enable']:
            continue
        if inbound_state['expired']:
            continue
        if inbound_state['exhausted']:
            continue
        result.append(mapping)
    return result


def _serialize_user_xui_client(mapping):
    backend = mapping.backend
    inbound_state = _user_xui_inbound_state(mapping)
    raw_inbound = _safe_json_loads(mapping.raw_inbound, {})
    inbound_port = _int_or_zero(raw_inbound.get('port')) if isinstance(raw_inbound, dict) else 0
    default_host = _public_host_from_xui_config(backend) if backend else ''
    subscription_host = (getattr(mapping, 'subscription_host', None) or '').strip()
    subscription_port = _int_or_zero(getattr(mapping, 'subscription_port', 0))
    return {
        'id': mapping.id,
        'user_id': mapping.user_id,
        'backend_id': mapping.backend_id,
        'backend_name': backend.name if backend else f'Backend {mapping.backend_id}',
        'backend_public_host': _public_host_from_xui_config(backend) if backend else '',
        'inbound_id': mapping.inbound_id,
        'inbound_name': mapping.inbound_name or f'Inbound {mapping.inbound_id}',
        'inbound_protocol': mapping.inbound_protocol or '',
        'inbound_port': inbound_port,
        'client_email': mapping.client_email,
        'sub_id': mapping.sub_id or '',
        'display_name': mapping.display_name or mapping.inbound_name or mapping.client_email,
        'comment': mapping.comment or '',
        'flow': mapping.flow or '',
        'limit_ip': mapping.limit_ip or 0,
        'enabled': bool(mapping.enabled),
        'online': bool(mapping.online),
        'traffic_up': mapping.traffic_up or 0,
        'traffic_down': mapping.traffic_down or 0,
        'traffic_used': mapping.traffic_used or 0,
        'traffic_limit': mapping.traffic_limit or 0,
        'traffic_used_gb': _bytes_to_gb(mapping.traffic_used),
        'traffic_limit_gb': _bytes_to_gb(mapping.traffic_limit),
        'expiry_time': mapping.expiry_time or 0,
        'inbound_enable': inbound_state['enable'],
        'inbound_total': inbound_state['total'],
        'inbound_up': inbound_state['up'],
        'inbound_down': inbound_state['down'],
        'inbound_used': inbound_state['used'],
        'inbound_remaining': inbound_state['remaining'],
        'inbound_total_gb': _bytes_to_gb(inbound_state['total']),
        'inbound_used_gb': _bytes_to_gb(inbound_state['used']),
        'inbound_remaining_gb': _bytes_to_gb(inbound_state['remaining']),
        'inbound_expiry_time': inbound_state['expiry_time'],
        'inbound_reset': inbound_state['reset'],
        'inbound_expired': inbound_state['expired'],
        'inbound_exhausted': inbound_state['exhausted'],
        'subscription_host': subscription_host,
        'subscription_port': subscription_port,
        'subscription_effective_host': subscription_host or default_host,
        'subscription_effective_port': subscription_port or inbound_port,
        'last_sync_at': mapping.last_sync_at.strftime('%Y-%m-%d %H:%M:%S') if mapping.last_sync_at else None,
        'last_error': mapping.last_error or ''
    }


def _xui_inbound_support_status(inbound):
    protocol = (inbound.get('protocol') or '').lower()
    network = (inbound.get('network') or '').lower() or 'tcp'
    if protocol not in XUI_SUBSCRIPTION_PROTOCOLS:
        return False, f'协议 {protocol or "unknown"} 暂不支持生成订阅'
    if network not in XUI_SUBSCRIPTION_NETWORKS:
        return False, f'传输 {network or "unknown"} 暂不支持生成订阅'
    return True, ''


def _first_non_empty(*values):
    for value in values:
        if value not in (None, ''):
            return value
    return None


def _first_list_item(value):
    if isinstance(value, list) and value:
        return value[0]
    return None


def _xui_find_client_credentials(inbound_settings, raw_client, email):
    clients = inbound_settings.get('clients') if isinstance(inbound_settings, dict) else []
    if not isinstance(clients, list):
        clients = []

    merged = {}
    for client in clients:
        if isinstance(client, dict) and client.get('email') == email:
            merged.update(client)
            break

    if isinstance(raw_client, dict):
        raw_source = raw_client.get('client') if isinstance(raw_client.get('client'), dict) else raw_client
        for key, value in raw_source.items():
            if value not in (None, ''):
                merged[key] = value

    return merged


def _apply_xui_stream_to_proxy(proxy, stream_settings):
    if not isinstance(stream_settings, dict):
        return proxy

    network = (stream_settings.get('network') or 'tcp').lower()
    security = (stream_settings.get('security') or 'none').lower()
    proxy['network'] = network

    if security in {'tls', 'xtls', 'reality'}:
        proxy['tls'] = True

    tls_settings = stream_settings.get('tlsSettings') if isinstance(stream_settings.get('tlsSettings'), dict) else {}
    reality_settings = stream_settings.get('realitySettings') if isinstance(stream_settings.get('realitySettings'), dict) else {}
    if security == 'reality':
        servername = _first_list_item(reality_settings.get('serverNames')) or reality_settings.get('serverName')
        public_key = reality_settings.get('publicKey')
        short_id = _first_list_item(reality_settings.get('shortIds')) or reality_settings.get('shortId')
        if servername:
            proxy['servername'] = servername
        if public_key or short_id:
            proxy['reality-opts'] = {}
            if public_key:
                proxy['reality-opts']['public-key'] = public_key
            if short_id:
                proxy['reality-opts']['short-id'] = short_id
        fingerprint = reality_settings.get('fingerprint')
        if fingerprint:
            proxy['client-fingerprint'] = fingerprint
    elif security in {'tls', 'xtls'}:
        servername = tls_settings.get('serverName') or tls_settings.get('serverNames')
        if isinstance(servername, list):
            servername = _first_list_item(servername)
        if servername:
            proxy['servername'] = servername
        if tls_settings.get('allowInsecure') is not None:
            proxy['skip-cert-verify'] = bool(tls_settings.get('allowInsecure'))
        fingerprint = tls_settings.get('fingerprint')
        if fingerprint:
            proxy['client-fingerprint'] = fingerprint

    if network == 'ws':
        ws_settings = stream_settings.get('wsSettings') if isinstance(stream_settings.get('wsSettings'), dict) else {}
        opts = {}
        if ws_settings.get('path'):
            opts['path'] = ws_settings.get('path')
        headers = ws_settings.get('headers') if isinstance(ws_settings.get('headers'), dict) else {}
        host = headers.get('Host') or headers.get('host')
        if host:
            opts['headers'] = {'Host': host}
        if opts:
            proxy['ws-opts'] = opts
    elif network == 'grpc':
        grpc_settings = stream_settings.get('grpcSettings') if isinstance(stream_settings.get('grpcSettings'), dict) else {}
        service_name = grpc_settings.get('serviceName') or grpc_settings.get('grpc-service-name')
        if service_name:
            proxy['grpc-opts'] = {'grpc-service-name': service_name}
    elif network in {'httpupgrade', 'xhttp'}:
        key = 'httpupgradeSettings' if network == 'httpupgrade' else 'xhttpSettings'
        settings = stream_settings.get(key) if isinstance(stream_settings.get(key), dict) else {}
        opts = {}
        if settings.get('path'):
            opts['path'] = settings.get('path')
        host = settings.get('host') or settings.get('Host')
        if host:
            opts['headers'] = {'Host': host}
        if opts:
            proxy[f'{network}-opts'] = opts

    return proxy


def _xui_mapping_to_proxy(mapping):
    backend = mapping.backend
    server = (getattr(mapping, 'subscription_host', None) or '').strip()
    if not server:
        server = _public_host_from_xui_config(backend) if backend else ''
    if not server:
        raise XuiApiError('3x-ui 后端缺少订阅连接地址', 400)

    raw_inbound = _safe_json_loads(mapping.raw_inbound, {})
    if not raw_inbound:
        raise XuiApiError('缺少 3x-ui 入站缓存，请先同步', 400)

    protocol = (raw_inbound.get('protocol') or mapping.inbound_protocol or '').lower()
    settings = _safe_json_loads(raw_inbound.get('settings'), {})
    stream_settings = _safe_json_loads(raw_inbound.get('streamSettings'), {})
    normalized_inbound = _normalize_xui_inbound(raw_inbound)
    supported, reason = _xui_inbound_support_status(normalized_inbound)
    if not supported:
        raise XuiApiError(reason, 400)

    raw_client = _safe_json_loads(mapping.raw_client, {})
    credentials = _xui_find_client_credentials(settings, raw_client, mapping.client_email)
    name = mapping.display_name or mapping.inbound_name or mapping.client_email
    proxy = {
        'name': name,
        'type': protocol,
        'server': server,
        'port': int(getattr(mapping, 'subscription_port', 0) or raw_inbound.get('port') or 0),
        'udp': True
    }
    if not proxy['port']:
        raise XuiApiError('3x-ui 入站缺少端口', 400)

    if protocol in {'vless', 'vmess'}:
        uuid = _first_non_empty(credentials.get('id'), credentials.get('uuid'))
        if not uuid:
            raise XuiApiError('3x-ui 客户端缺少 UUID', 400)
        proxy['uuid'] = uuid
        if protocol == 'vmess':
            proxy['alterId'] = int(credentials.get('alterId') or credentials.get('alter_id') or 0)
            proxy['cipher'] = credentials.get('security') or credentials.get('cipher') or 'auto'
        else:
            flow = credentials.get('flow') or mapping.flow
            if flow:
                proxy['flow'] = flow
    elif protocol == 'trojan':
        password = credentials.get('password')
        if not password:
            raise XuiApiError('3x-ui Trojan 客户端缺少密码', 400)
        proxy['password'] = password
    elif protocol == 'shadowsocks':
        cipher = _first_non_empty(credentials.get('method'), credentials.get('cipher'), settings.get('method'))
        password = _first_non_empty(credentials.get('password'), settings.get('password'))
        if not cipher or not password:
            raise XuiApiError('3x-ui Shadowsocks 客户端缺少加密方式或密码', 400)
        proxy['cipher'] = cipher
        proxy['password'] = password
    elif protocol == 'hysteria2':
        password = _first_non_empty(credentials.get('password'), settings.get('password'))
        if not password:
            raise XuiApiError('3x-ui Hysteria2 客户端缺少密码', 400)
        proxy['password'] = password
        obfs_password = _first_non_empty(settings.get('obfsPassword'), settings.get('obfs-password'))
        if obfs_password:
            proxy['obfs'] = settings.get('obfs') or 'salamander'
            proxy['obfs-password'] = obfs_password

    _apply_xui_stream_to_proxy(proxy, stream_settings)
    if protocol in {'trojan', 'hysteria2'} and proxy.get('servername') and not proxy.get('sni'):
        proxy['sni'] = proxy['servername']
    return proxy


def _build_xui_subscription_proxies(user):
    proxies = []
    for mapping in _active_user_xui_clients(user):
        try:
            proxies.append(_xui_mapping_to_proxy(mapping))
        except XuiApiError as e:
            app.logger.warning(
                "skip 3x-ui user client in subscription: user=%s mapping=%s error=%s",
                user.id,
                mapping.id,
                e.message
            )
    return proxies


def _xui_find_inbound_client(inbound, email):
    settings = inbound.get('settings') if isinstance(inbound.get('settings'), dict) else {}
    clients = settings.get('clients') if isinstance(settings, dict) else []
    if not isinstance(clients, list):
        return {}
    for client in clients:
        if isinstance(client, dict) and client.get('email') == email:
            return client
    return {}


def _ensure_xui_client_credentials(client_payload, inbound):
    protocol = (inbound.get('protocol') or '').lower()
    settings = inbound.get('settings') if isinstance(inbound.get('settings'), dict) else {}
    if protocol in {'vless', 'vmess'}:
        client_id = client_payload.get('id')
        if not isinstance(client_id, str) or not client_id.strip() or client_id.strip().isdigit():
            inbound_client = _xui_find_inbound_client(inbound, client_payload.get('email'))
            existing_id = _first_non_empty(inbound_client.get('id'), inbound_client.get('uuid'), client_payload.get('uuid'))
            client_payload['id'] = str(existing_id) if existing_id else str(uuid.uuid4())
    elif protocol == 'trojan' and not client_payload.get('password'):
        client_payload['password'] = secrets.token_urlsafe(18)
    elif protocol in {'shadowsocks', 'hysteria2'} and not client_payload.get('password'):
        client_payload['password'] = secrets.token_urlsafe(18)
    if protocol == 'shadowsocks' and not client_payload.get('method') and settings.get('method'):
        client_payload['method'] = settings.get('method')
    return client_payload


def _create_user_xui_client_mapping(user, backend_id, inbound, client_data, client_map=None, created_remote_emails=None):
    client_data = client_data or {}
    inbound_id = int(inbound.get('id') or 0)
    if inbound_id <= 0:
        raise XuiApiError('入站 ID 不正确', 502)

    supported, reason = _xui_inbound_support_status(inbound)
    if not supported:
        raise XuiApiError(reason, 400)

    existing = UserXuiClient.query.filter_by(
        user_id=user.id,
        backend_id=backend_id,
        inbound_id=inbound_id
    ).first()
    if existing:
        raise XuiApiError(f'用户已绑定入站 {inbound.get("remark") or inbound_id}', 400)

    email = _make_user_xui_client_email(user, inbound_id)
    if client_map is not None and email in client_map:
        raise XuiApiError(f'3x-ui 已存在客户端 {email}', 400)

    comment = (client_data.get('comment') or '').strip()
    if not comment:
        comment = f'用户 {user.username} / 入站 {inbound.get("remark") or inbound_id}'

    client_payload = _build_client_payload({
        'email': email,
        'sub_id': client_data.get('sub_id') or _make_user_xui_sub_id(user, inbound_id),
        'comment': comment,
        'flow': client_data.get('flow') or '',
        'limit_ip': client_data.get('limit_ip'),
        'enable': client_data.get('enable', True)
    })
    _strip_user_xui_client_limits(client_payload)
    client_payload = _ensure_xui_client_credentials(client_payload, inbound)
    _xui_request(
        'POST',
        '/panel/api/clients/add',
        json_body={'client': client_payload, 'inboundIds': [inbound_id]},
        config_id=backend_id
    )
    if created_remote_emails is not None:
        created_remote_emails.append(email)

    display_name = (client_data.get('display_name') or '').strip()
    if not display_name:
        display_name = f'{user.username}-{inbound.get("remark") or inbound_id}'

    mapping = UserXuiClient(
        user_id=user.id,
        backend_id=backend_id,
        inbound_id=inbound_id,
        inbound_name=inbound.get('remark') or f'Inbound {inbound_id}',
        inbound_protocol=inbound.get('protocol') or '',
        client_email=email,
        sub_id=client_payload.get('subId') or '',
        display_name=display_name,
        comment=comment,
        flow=client_payload.get('flow') or '',
        limit_ip=int(client_payload.get('limitIp') or 0),
        enabled=bool(client_payload.get('enable', True)),
        traffic_limit=int(inbound.get('total') or 0),
        expiry_time=int(inbound.get('expiryTime') or 0),
        raw_client=_json_dump(client_payload),
        raw_inbound=_json_dump(inbound.get('raw') or inbound)
    )
    db.session.add(mapping)
    return mapping, email


def _request_etag_matches(etag):
    header_value = request.headers.get('If-None-Match', '')
    if not header_value:
        return False

    for candidate in header_value.split(','):
        normalized = candidate.strip()
        if normalized == '*':
            return True
        if normalized.startswith('W/'):
            normalized = normalized[2:].strip()
        if normalized.strip('"') == etag:
            return True

    return False


def _apply_subscription_headers(response, cache_entry, cache_status):
    encoded_filename = quote(cache_entry['filename'])
    response.headers['Content-Type'] = 'text/yaml; charset=utf-8'
    response.headers['Content-Disposition'] = (
        f"attachment; filename={encoded_filename}; filename*=UTF-8''{encoded_filename}"
    )
    response.headers['Subscription-Userinfo'] = cache_entry.get('subscription_userinfo') or 'upload=0; download=0; total=0; expire=0'
    response.headers['Cache-Control'] = 'no-cache, must-revalidate'
    response.headers['X-Subscription-Cache'] = cache_status
    response.headers['X-Subscription-Cache-Version'] = str(cache_entry['version'])
    response.headers['X-Subscription-Bytes'] = str(cache_entry['yaml_bytes'])
    response.set_etag(cache_entry['etag'])
    return response


def _make_subscription_response(cache_entry, cache_status):
    if _request_etag_matches(cache_entry['etag']):
        response = make_response('', 304)
        return _apply_subscription_headers(response, cache_entry, 'NOT_MODIFIED')

    response = make_response(cache_entry['body'], 200)
    return _apply_subscription_headers(response, cache_entry, cache_status)


def _apply_shadowrocket_subscription_headers(response, cache_entry, cache_status):
    """为 Shadowrocket 远程订阅附加下载、流量和缓存响应头。"""
    encoded_filename = quote(cache_entry['filename'])
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'
    response.headers['Content-Disposition'] = (
        f"attachment; filename={encoded_filename}; filename*=UTF-8''{encoded_filename}"
    )
    response.headers['Subscription-Userinfo'] = cache_entry.get('subscription_userinfo') or 'upload=0; download=0; total=0; expire=0'
    response.headers['Cache-Control'] = 'no-cache, must-revalidate'
    response.headers['X-Subscription-Cache'] = cache_status
    response.headers['X-Subscription-Cache-Version'] = str(cache_entry['version'])
    response.headers['X-Subscription-Bytes'] = str(cache_entry['yaml_bytes'])
    response.headers['X-Subscription-Format'] = 'shadowrocket'
    response.headers['X-Shadowrocket-Node-Count'] = str(cache_entry.get('shadowrocket_node_count', 0))
    response.headers['X-Shadowrocket-Skipped-Count'] = str(cache_entry.get('shadowrocket_skipped_count', 0))
    response.set_etag(cache_entry['etag'])
    return response


def _make_shadowrocket_subscription_response(cache_entry, cache_status):
    if _request_etag_matches(cache_entry['etag']):
        response = make_response('', 304)
        return _apply_shadowrocket_subscription_headers(response, cache_entry, 'NOT_MODIFIED')

    response = make_response(cache_entry['body'], 200)
    return _apply_shadowrocket_subscription_headers(response, cache_entry, cache_status)


def _build_shadowrocket_subscription_body(proxy_configs):
    """将有序 Clash 节点转换为 Shadowrocket 可读取的 Base64 URI 列表。"""
    share_urls = []
    seen_names = set()
    skipped_count = 0

    for raw_proxy in proxy_configs:
        if not isinstance(raw_proxy, dict):
            skipped_count += 1
            continue

        proxy = copy.deepcopy(raw_proxy)
        name = str(proxy.get('name') or '').strip()
        if not name:
            skipped_count += 1
            continue
        if name in seen_names:
            continue

        if (
            str(proxy.get('type') or '').lower() == 'relay'
            or proxy.get('dialer-proxy')
            or proxy.get('__chain_dependencies')
        ):
            skipped_count += 1
            continue

        if str(proxy.get('type') or '').lower() == 'shadowsocks':
            proxy['type'] = 'ss'

        try:
            share_url = ProxyParser.to_share_url(proxy)
        except (TypeError, ValueError) as exc:
            skipped_count += 1
            app.logger.warning(
                "skip node in Shadowrocket subscription: name=%s type=%s error=%s",
                name,
                proxy.get('type') or '',
                exc
            )
            continue

        if not share_url:
            skipped_count += 1
            continue

        seen_names.add(name)
        share_urls.append(share_url)

    plain_body = '\n'.join(share_urls).encode('utf-8')
    return base64.b64encode(plain_body), len(share_urls), skipped_count


def _log_subscription_timing(cache_type, name, cache_status, stats, started_at):
    total_ms = (time.perf_counter() - started_at) * 1000
    app.logger.info(
        "subscription cache=%s type=%s name=%s nodes=%s proxies=%s bytes=%s "
        "collect_ms=%.2f deps_ms=%.2f generate_ms=%.2f yaml_ms=%.2f total_ms=%.2f",
        cache_status,
        cache_type,
        name,
        stats.get('node_count', 0),
        stats.get('proxy_count', 0),
        stats.get('yaml_bytes', 0),
        stats.get('collect_ms', 0),
        stats.get('deps_ms', 0),
        stats.get('generate_ms', 0),
        stats.get('yaml_ms', 0),
        total_ms
    )


def _build_subscription_cache_entry(
    cache_type,
    entity_id,
    name,
    filename,
    nodes,
    proxy_group_name,
    template_content,
    subscription_userinfo=None,
    extra_proxies=None,
    store=True
):
    stats = {}

    deps_start = time.perf_counter()
    proxies = _build_proxy_configs_with_chain_dependencies(nodes)
    if extra_proxies:
        proxies.extend(copy.deepcopy(extra_proxies))
    stats['deps_ms'] = (time.perf_counter() - deps_start) * 1000

    generate_start = time.perf_counter()
    generator = ClashConfigGenerator()
    config = generator.generate(proxies, proxy_group_name, template_content)
    stats['generate_ms'] = (time.perf_counter() - generate_start) * 1000

    yaml_start = time.perf_counter()
    yaml_body = _dump_yaml_bytes(config)
    stats['yaml_ms'] = (time.perf_counter() - yaml_start) * 1000

    stats['node_count'] = len(nodes)
    stats['extra_proxy_count'] = len(extra_proxies or [])
    stats['proxy_count'] = len(config.get('proxies', []))
    stats['yaml_bytes'] = len(yaml_body)

    cache_entry = {
        'body': yaml_body,
        'etag': hashlib.sha256(yaml_body).hexdigest(),
        'filename': filename,
        'name': name,
        'yaml_bytes': len(yaml_body),
        'stats': stats,
        'subscription_userinfo': subscription_userinfo or 'upload=0; download=0; total=0; expire=0',
    }

    if not store:
        cache_entry['version'] = _subscription_cache_version
        return cache_entry

    return _store_subscription_cache(cache_type, entity_id, cache_entry)


@app.after_request
def clear_subscription_cache_after_api_write(response):
    if (
        request.path.startswith('/api/')
        and request.method in {'POST', 'PUT', 'DELETE'}
        and response.status_code < 400
    ):
        _invalidate_subscription_cache(f'{request.method} {request.path}')

    return response


def _dedupe_preserve_order(items):
    """按首次出现顺序去重。"""
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _get_chain_dependency_names(config):
    """提取链式节点依赖的前置/后置节点名称。"""
    if not isinstance(config, dict):
        return []

    dependency_names = []

    # 旧 relay 方式通过 proxies 数组引用前置和后置节点。
    relay_proxies = config.get('proxies') if config.get('type') == 'relay' else None
    if isinstance(relay_proxies, list):
        dependency_names.extend([
            proxy for proxy in relay_proxies
            if isinstance(proxy, str) and proxy
        ])

    # 新 dialer-proxy 方式至少需要前置节点存在于 proxies 中。
    dialer_proxy = config.get('dialer-proxy')
    if isinstance(dialer_proxy, str) and dialer_proxy:
        dependency_names.append(dialer_proxy)

    # 新创建的链式节点会记录原始前置/后置节点，供订阅生成时隐藏写入。
    explicit_dependencies = config.get('__chain_dependencies')
    if isinstance(explicit_dependencies, list):
        dependency_names.extend([
            proxy for proxy in explicit_dependencies
            if isinstance(proxy, str) and proxy
        ])

    return _dedupe_preserve_order(dependency_names)


def _dedupe_nodes(nodes):
    """按节点 ID 去重，避免用户聚合多个订阅时重复输出同一节点。"""
    seen = set()
    result = []
    for node in nodes:
        if node.id in seen:
            continue
        seen.add(node.id)
        result.append(node)
    return result


def _find_nodes_by_name(names):
    """按名称查找节点；同名时使用排序最靠前的节点。"""
    ordered_names = _dedupe_preserve_order(names)
    if not ordered_names:
        return {}

    nodes = Node.query.filter(Node.name.in_(ordered_names)).order_by(
        Node.order.asc(),
        Node.id.asc()
    ).all()

    nodes_by_name = {}
    for node in nodes:
        if node.name not in nodes_by_name:
            nodes_by_name[node.name] = node

    return nodes_by_name


def _build_proxy_configs_with_chain_dependencies(nodes):
    """
    构建订阅输出节点。

    传入的节点会作为可展示节点进入代理组；链式节点依赖的前置/后置节点
    会以隐藏节点追加到 proxies 中，只用于满足客户端解析依赖。
    """
    visible_nodes = _dedupe_nodes(nodes)
    visible_entries = []
    proxy_configs = []
    included_names = set()
    pending_dependency_names = []

    for node in visible_nodes:
        config = node.get_config()
        config_name = config.get('name') or node.name

        visible_entries.append((config_name, config))
        pending_dependency_names.extend(_get_chain_dependency_names(config))

    for config_name, config in visible_entries:
        # Nodes passed in here are explicitly assigned to this output and must
        # remain selectable, even when another chain node depends on them.
        proxy_configs.append(config)

        if config_name:
            included_names.add(config_name)

    while pending_dependency_names:
        dependency_names = [
            name for name in _dedupe_preserve_order(pending_dependency_names)
            if name not in included_names
        ]
        pending_dependency_names = []

        if not dependency_names:
            break

        dependency_nodes = _find_nodes_by_name(dependency_names)

        for name in dependency_names:
            dependency_node = dependency_nodes.get(name)
            if not dependency_node:
                continue

            dependency_config = dependency_node.get_config()
            dependency_name = dependency_config.get('name') or dependency_node.name
            if dependency_name in included_names:
                continue

            dependency_config['__hidden'] = True
            proxy_configs.append(dependency_config)
            included_names.add(dependency_name)

            pending_dependency_names.extend(_get_chain_dependency_names(dependency_config))

    return proxy_configs


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

def _parse_node_config_input(node_url):
    if not node_url:
        raise XuiApiError('节点配置不能为空', 400)

    node_url = node_url.strip()
    proxy = None

    if ('type:' in node_url or node_url.startswith('{') or node_url.startswith('- {')):
        try:
            yaml_content = node_url
            if yaml_content.startswith('{') and not yaml_content.startswith('- {'):
                yaml_content = '- ' + yaml_content

            parsed = yaml.safe_load(yaml_content)
            if isinstance(parsed, list) and parsed:
                proxy = parsed[0]
            elif isinstance(parsed, dict):
                proxy = parsed
            if not proxy or not isinstance(proxy, dict):
                raise XuiApiError('YAML 格式不正确', 400)
        except XuiApiError:
            raise
        except Exception as e:
            raise XuiApiError(f'YAML 解析失败: {e}', 400)
    else:
        proxy = ProxyParser.parse_proxy(node_url)
        if not proxy:
            raise XuiApiError('无法解析节点链接。请使用标准分享链接或 YAML 配置格式。', 400)

    if not proxy or not isinstance(proxy, dict):
        raise XuiApiError('节点配置无效', 400)
    if 'name' not in proxy or 'type' not in proxy:
        raise XuiApiError('节点配置缺少必要字段（name 或 type）', 400)

    return proxy


def _create_node_from_proxy(proxy, custom_name=None, subscription_id=None):
    proxy = copy.deepcopy(proxy)
    node_name = custom_name or proxy['name']
    original_name = proxy['name']

    if custom_name:
        proxy['name'] = custom_name

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

    if subscription_id:
        subscription = Subscription.query.get(subscription_id)
        if subscription:
            node.subscriptions.append(subscription)

    return node


def _recalculate_user_traffic_used(user):
    db.session.flush()
    legacy_used = int(
        db.session.query(db.func.coalesce(db.func.sum(UserNode.traffic_used), 0))
        .filter(UserNode.user_id == user.id)
        .scalar() or 0
    )
    xui_used = int(
        db.session.query(db.func.coalesce(db.func.sum(UserXuiClient.traffic_used), 0))
        .filter(UserXuiClient.user_id == user.id)
        .scalar() or 0
    )
    user.traffic_used = legacy_used + xui_used
    return user.traffic_used


@app.route('/api/nodes', methods=['GET', 'POST'])
@login_required
def manage_nodes():
    """获取或添加节点"""
    if request.method == 'GET':
        # 按排序字段排序
        nodes = Node.query.order_by(Node.order.asc(), Node.id.asc()).all()
        result = []
        for n in nodes:
            config = n.get_config()
            dialer_proxy = config.get('dialer-proxy') if config else None
            subscription_user_names = [u.username for s in n.subscriptions for u in s.users] if n.subscriptions else []
            direct_user_names = [assignment.user.username for assignment in n.user_assignments if assignment.user]
            result.append({
                'id': n.id,
                'name': n.name,
                'original_name': n.original_name,
                'protocol': n.protocol,
                'subscription_id': n.subscription_id,  # 保留用于兼容性
                'subscription_name': ', '.join([s.name for s in n.subscriptions]) if n.subscriptions else '手动添加',
                'subscription_names': [s.name for s in n.subscriptions],  # 新增：所有订阅名称列表
                'subscription_ids': [s.id for s in n.subscriptions],  # 新增：所有订阅ID列表
                'user_names': sorted(set(subscription_user_names + direct_user_names)),
                'order': n.order if hasattr(n, 'order') else 0,
                'dialer_proxy': dialer_proxy,  # 新增：dialer-proxy 前置节点名称
                'created_at': n.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        return jsonify(result)
    
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


@app.route('/api/nodes/<int:node_id>/export', methods=['GET'])
@login_required
def export_node(node_id):
    """导出单个节点为可直接导入客户端的分享链接。"""
    node = Node.query.get_or_404(node_id)
    config = node.get_config()
    config['name'] = node.name

    try:
        share_url = ProxyParser.to_share_url(config)
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 400

    return jsonify({
        'success': True,
        'name': node.name,
        'protocol': node.protocol,
        'url': share_url
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
        'anytls': ['password'],
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


@app.route('/api/nodes/batch-dialer-proxy', methods=['POST'])
@login_required
def batch_create_dialer_proxy_nodes():
    """批量创建 dialer-proxy 链式代理节点（新方式）"""
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
            if 'name' not in config or 'backNodeId' not in config or 'frontNodeName' not in config:
                continue
            
            # 获取后置节点的完整配置
            back_node = Node.query.get(config['backNodeId'])
            if not back_node:
                continue
            
            back_config = back_node.get_config()
            
            # 复制后置节点配置
            new_config = back_config.copy()
            
            # 修改名称
            new_config['name'] = config['name']
            
            # 添加 dialer-proxy 指向前置节点
            new_config['dialer-proxy'] = config['frontNodeName']

            # 记录链式依赖。生成订阅时会把这些节点隐藏写入 proxies，
            # 但不会放进 proxy-groups 里展示。
            back_node_name = back_config.get('name') or back_node.name
            new_config['__chain_dependencies'] = _dedupe_preserve_order([
                config['frontNodeName'],
                back_node_name
            ])
            
            # 处理 UDP 设置
            if config.get('enableUdp'):
                new_config['udp'] = True
                if 'disable-udp' in new_config:
                    del new_config['disable-udp']
            else:
                new_config['disable-udp'] = True
                if 'udp' in new_config:
                    del new_config['udp']
            
            # 创建新节点
            node = Node(
                name=config['name'],
                original_name=config['name'],
                protocol=back_node.protocol,  # 保持原协议类型
                subscription_id=subscription_id,
                order=max_order + created_count + 1
            )
            node.set_config(new_config)
            
            db.session.add(node)
            
            # 添加到多对多关系
            if subscription:
                node.subscriptions.append(subscription)
            
            created_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'count': created_count,
            'message': f'成功创建 {created_count} 个 dialer-proxy 链式节点'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


# ============ 用户管理 API ============

def _active_user_node_assignments(user):
    now_ms = int(time.time() * 1000)
    active_assignments = []

    for assignment in user.node_assignments:
        if not assignment.node:
            continue
        if assignment.expiry_time and assignment.expiry_time <= now_ms:
            continue
        if assignment.traffic_limit and (assignment.traffic_used or 0) >= assignment.traffic_limit:
            continue
        active_assignments.append(assignment)

    return active_assignments


def _serialize_user_node_assignment(assignment):
    node = assignment.node
    subscription_names = [s.name for s in node.subscriptions] if node and node.subscriptions else []
    return {
        'node_id': assignment.node_id,
        'node_name': node.name if node else '',
        'protocol': node.protocol if node else '',
        'subscription_name': ', '.join(subscription_names) if subscription_names else '手动添加',
        'subscription_names': subscription_names,
        'traffic_limit': assignment.traffic_limit or 0,
        'traffic_limit_gb': _bytes_to_gb(assignment.traffic_limit),
        'traffic_used': assignment.traffic_used or 0,
        'traffic_used_gb': _bytes_to_gb(assignment.traffic_used),
        'expiry_time': assignment.expiry_time or 0,
        'expired': bool(assignment.expiry_time and assignment.expiry_time <= int(time.time() * 1000))
    }


def _user_traffic_used_bytes(user):
    legacy_used = sum(int(assignment.traffic_used or 0) for assignment in (user.node_assignments or []))
    xui_used = sum(int(mapping.traffic_used or 0) for mapping in (user.xui_clients or []))
    if legacy_used or xui_used:
        return legacy_used + xui_used
    return int(user.traffic_used or 0)


def _user_xui_subscription_totals(user):
    active_mappings = _active_user_xui_clients(user)
    inbound_states = [_user_xui_inbound_state(mapping) for mapping in active_mappings]
    return {
        'upload': sum(item['up'] for item in inbound_states),
        'download': sum(item['down'] for item in inbound_states),
        'total': sum(item['total'] for item in inbound_states),
        'expire': min(
            [
                _unix_seconds_from_ms(item['expiry_time'])
                for item in inbound_states
                if item['expiry_time']
            ] or [0]
        )
    }


def _serialize_user(user):
    subscription_nodes = []
    for subscription in user.subscriptions:
        subscription_nodes.extend(subscription.nodes)

    direct_assignments = _active_user_node_assignments(user)
    direct_nodes = [assignment.node for assignment in direct_assignments if assignment.node]
    active_xui_clients = _active_user_xui_clients(user)
    visible_nodes = _dedupe_nodes(subscription_nodes + direct_nodes)

    traffic_used = _user_traffic_used_bytes(user)

    return {
        'id': user.id,
        'username': user.username,
        'subscription_token': user.subscription_token,
        'custom_slug': user.custom_slug,
        'subscription_count': len(user.subscriptions),
        'subscription_node_count': len(_dedupe_nodes(subscription_nodes)),
        'direct_node_count': len(_dedupe_nodes(direct_nodes)),
        'direct_node_total_count': len(user.node_assignments),
        'xui_node_count': len(active_xui_clients),
        'xui_node_total_count': len(user.xui_clients),
        'node_count': len(visible_nodes) + len(active_xui_clients),
        'enabled': user.enabled,
        'remark': user.remark or '',
        'template_id': user.template_id,
        'template_name': user.template.name if user.template else None,
        'traffic_limit': user.traffic_limit or 0,
        'traffic_limit_gb': _bytes_to_gb(user.traffic_limit),
        'traffic_used': traffic_used,
        'traffic_used_gb': _bytes_to_gb(traffic_used),
        'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S')
    }


def _user_subscription_userinfo(user):
    total = int(user.traffic_limit or 0)
    if user.xui_clients:
        totals = _user_xui_subscription_totals(user)
        legacy_download = sum(int(assignment.traffic_used or 0) for assignment in (user.node_assignments or []))
        return (
            f"upload={totals['upload']}; download={totals['download'] + legacy_download}; "
            f"total={total}; expire=0"
        )
    download = _user_traffic_used_bytes(user)
    return f'upload=0; download={download}; total={total}; expire=0'


@app.route('/api/users', methods=['GET', 'POST'])
@login_required
def manage_users():
    """获取或添加用户（分组）"""
    if request.method == 'GET':
        users = User.query.all()
        return jsonify([_serialize_user(u) for u in users])
    
    # POST - 添加用户（分组）
    data = request.get_json()
    username = data.get('username')
    remark = data.get('remark', '')
    try:
        traffic_limit = _gb_to_bytes(data.get('traffic_limit_gb'), 0)
    except XuiApiError as e:
        return jsonify({'success': False, 'message': e.message}), 400
    
    if not username:
        return jsonify({'success': False, 'message': '名称不能为空'}), 400
    
    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': '名称已存在'}), 400
    
    user = User(
        username=username,
        remark=remark,
        traffic_limit=traffic_limit,
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

    if 'traffic_limit_gb' in data:
        try:
            user.traffic_limit = _gb_to_bytes(data.get('traffic_limit_gb'), user.traffic_limit or 0)
        except XuiApiError as e:
            return jsonify({'success': False, 'message': e.message}), 400

    if 'traffic_used_gb' in data:
        try:
            user.traffic_used = _gb_to_bytes(data.get('traffic_used_gb'), user.traffic_used or 0)
        except XuiApiError as e:
            return jsonify({'success': False, 'message': e.message}), 400
    
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/users/<int:user_id>/xui-clients', methods=['GET', 'POST'])
@login_required
def manage_user_xui_clients(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'GET':
        sync_enabled = request.args.get('sync', '1') not in {'0', 'false', 'False'}
        include_inbounds = request.args.get('include_inbounds', '1') not in {'0', 'false', 'False'}
        if sync_enabled:
            _sync_user_xui_clients(user, raise_errors=False)

        backends = XuiConfig.query.order_by(XuiConfig.id.asc()).all()
        selected_backend_id = request.args.get('backend_id')
        if selected_backend_id in (None, '') and backends:
            selected_backend_id = backends[0].id

        inbounds = []
        inbound_error = ''
        if include_inbounds and selected_backend_id not in (None, ''):
            try:
                backend_id = int(selected_backend_id)
                inbound_map, _client_map = _xui_fetch_client_state(backend_id)
                for inbound in inbound_map.values():
                    supported, reason = _xui_inbound_support_status(inbound)
                    item = dict(inbound)
                    item['subscription_supported'] = supported
                    item['unsupported_reason'] = reason
                    inbounds.append(item)
            except (TypeError, ValueError):
                inbound_error = '后端 ID 不正确'
            except XuiApiError as e:
                inbound_error = e.message

        return jsonify({
            'success': True,
            'clients': [_serialize_user_xui_client(item) for item in user.xui_clients],
            'backends': [backend.to_public_dict() for backend in backends],
            'selected_backend_id': int(selected_backend_id) if selected_backend_id not in (None, '') else None,
            'inbounds': sorted(inbounds, key=lambda item: (item.get('remark') or '', item.get('id') or 0)),
            'inbound_error': inbound_error,
            'include_inbounds': include_inbounds
        })

    data = request.get_json() or {}
    created_remote = []
    backend_id = None
    try:
        backend_id = _get_xui_backend_id(data)
        backend = _require_xui_config(backend_id)
        backend_id = backend.id
        if not _public_host_from_xui_config(backend):
            raise XuiApiError('请先在 3x-ui 后端配置订阅连接地址', 400)

        inbound_ids = _coerce_int_list(data.get('inbound_ids'))
        if not inbound_ids:
            raise XuiApiError('请选择至少一个 3x-ui 入站', 400)

        inbound_map, client_map = _xui_fetch_client_state(backend_id)
        prepared = []
        for inbound_id in inbound_ids:
            inbound = inbound_map.get(inbound_id)
            if not inbound:
                raise XuiApiError(f'入站不存在: {inbound_id}', 400)
            supported, reason = _xui_inbound_support_status(inbound)
            if not supported:
                raise XuiApiError(reason, 400)
            existing = UserXuiClient.query.filter_by(
                user_id=user.id,
                backend_id=backend_id,
                inbound_id=inbound_id
            ).first()
            if existing:
                raise XuiApiError(f'用户已绑定入站 {inbound.get("remark") or inbound_id}', 400)
            email = _make_user_xui_client_email(user, inbound_id)
            if email in client_map:
                raise XuiApiError(f'3x-ui 已存在客户端 {email}', 400)
            prepared.append((inbound_id, inbound, email))

        created_mappings = []
        for inbound_id, inbound, email in prepared:
            comment = (data.get('comment') or '').strip() or f'用户 {user.username} / 入站 {inbound.get("remark") or inbound_id}'
            client_payload = _build_client_payload({
                'email': email,
                'sub_id': data.get('sub_id') or _make_user_xui_sub_id(user, inbound_id),
                'comment': comment,
                'flow': data.get('flow') or '',
                'limit_ip': data.get('limit_ip'),
                'enable': data.get('enable', True)
            })
            _strip_user_xui_client_limits(client_payload)
            client_payload = _ensure_xui_client_credentials(client_payload, inbound)
            _xui_request(
                'POST',
                '/panel/api/clients/add',
                json_body={'client': client_payload, 'inboundIds': [inbound_id]},
                config_id=backend_id
            )
            created_remote.append(email)
            inbound = _update_user_xui_inbound_limits(backend_id, inbound_id, data, inbound) or inbound

            display_name = (data.get('display_name') or '').strip()
            if not display_name:
                display_name = f'{user.username}-{inbound.get("remark") or inbound_id}'
            mapping = UserXuiClient(
                user_id=user.id,
                backend_id=backend_id,
                inbound_id=inbound_id,
                inbound_name=inbound.get('remark') or f'Inbound {inbound_id}',
                inbound_protocol=inbound.get('protocol') or '',
                client_email=email,
                sub_id=client_payload.get('subId') or '',
                display_name=display_name,
                comment=comment,
                flow=client_payload.get('flow') or '',
                limit_ip=int(client_payload.get('limitIp') or 0),
                enabled=bool(client_payload.get('enable', True)),
                traffic_limit=int(inbound.get('total') or 0),
                expiry_time=int(inbound.get('expiryTime') or 0),
                raw_client=_json_dump(client_payload),
                raw_inbound=_json_dump(inbound.get('raw') or inbound)
            )
            db.session.add(mapping)
            created_mappings.append(mapping)

        db.session.flush()
        _sync_user_xui_clients(user, raise_errors=False)
        return jsonify({
            'success': True,
            'count': len(created_mappings),
            'clients': [_serialize_user_xui_client(item) for item in created_mappings]
        })
    except XuiApiError as e:
        db.session.rollback()
        for email in created_remote:
            try:
                _xui_request('POST', f'/panel/api/clients/del/{quote_plus(email)}', config_id=backend_id)
            except Exception:
                app.logger.warning("failed to clean up remote 3x-ui client after local error: %s", email)
        return _xui_error_response(e)
    except Exception as e:
        db.session.rollback()
        for email in created_remote:
            try:
                _xui_request('POST', f'/panel/api/clients/del/{quote_plus(email)}', config_id=backend_id)
            except Exception:
                app.logger.warning("failed to clean up remote 3x-ui client after exception: %s", email)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/<int:user_id>/xui-clients/create-inbound', methods=['POST'])
@login_required
def create_user_xui_inbound_client(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}
    created_remote_emails = []
    created_inbound_id = None
    backend_id = None

    try:
        backend_id = _get_xui_backend_id(data)
        backend = _require_xui_config(backend_id)
        backend_id = backend.id
        if not _public_host_from_xui_config(backend):
            raise XuiApiError('请先在 3x-ui 后端配置订阅连接地址', 400)

        inbound_payload = _build_inbound_payload({
            'inbound_payload': data.get('inbound_payload') or data.get('payload'),
            'preserve_clients': False
        })
        normalized_inbound = _normalize_xui_inbound(inbound_payload)
        supported, reason = _xui_inbound_support_status(normalized_inbound)
        if not supported:
            raise XuiApiError(reason, 400)

        before_inbounds = _xui_fetch_inbound_list(backend_id)
        requested_port = int(inbound_payload.get('port') or 0)
        if any(int(item.get('port') or 0) == requested_port for item in before_inbounds):
            raise XuiApiError(f'端口 {requested_port} 已被当前后端入站使用', 400)

        add_response = _xui_request(
            'POST',
            '/panel/api/inbounds/add',
            json_body=inbound_payload,
            config_id=backend_id
        )
        after_inbounds = _xui_fetch_inbound_list(backend_id)
        created_inbound = _find_created_xui_inbound(
            before_inbounds,
            after_inbounds,
            inbound_payload,
            add_response
        )
        created_inbound_id = int(created_inbound.get('id') or 0)
        if created_inbound_id <= 0:
            raise XuiApiError('入站已创建，但新入站 ID 不正确', 502)

        inbound_map, client_map = _xui_fetch_client_state(backend_id)
        created_inbound = inbound_map.get(created_inbound_id, created_inbound)
        mapping, _email = _create_user_xui_client_mapping(
            user,
            backend_id,
            created_inbound,
            data.get('client') or {},
            client_map=client_map,
            created_remote_emails=created_remote_emails
        )
        db.session.flush()
        _sync_user_xui_clients(user, raise_errors=False)

        return jsonify({
            'success': True,
            'message': '入站节点已创建并挂到用户',
            'inbound': created_inbound,
            'client': _serialize_user_xui_client(mapping)
        })
    except XuiApiError as e:
        db.session.rollback()
        for email in created_remote_emails:
            try:
                _xui_request('POST', f'/panel/api/clients/del/{quote_plus(email)}', config_id=backend_id)
            except Exception:
                app.logger.warning("failed to clean up remote 3x-ui client after create-inbound error: %s", email)
        if created_inbound_id:
            try:
                _xui_request('POST', f'/panel/api/inbounds/del/{created_inbound_id}', config_id=backend_id)
            except Exception:
                app.logger.warning("failed to clean up remote 3x-ui inbound after create-inbound error: %s", created_inbound_id)
        return _xui_error_response(e)
    except Exception as e:
        db.session.rollback()
        for email in created_remote_emails:
            try:
                _xui_request('POST', f'/panel/api/clients/del/{quote_plus(email)}', config_id=backend_id)
            except Exception:
                app.logger.warning("failed to clean up remote 3x-ui client after create-inbound exception: %s", email)
        if created_inbound_id:
            try:
                _xui_request('POST', f'/panel/api/inbounds/del/{created_inbound_id}', config_id=backend_id)
            except Exception:
                app.logger.warning("failed to clean up remote 3x-ui inbound after create-inbound exception: %s", created_inbound_id)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/users/<int:user_id>/xui-clients/sync', methods=['POST'])
@login_required
def sync_user_xui_clients(user_id):
    user = User.query.get_or_404(user_id)
    _sync_user_xui_clients(user, raise_errors=False)
    return jsonify({
        'success': True,
        'clients': [_serialize_user_xui_client(item) for item in user.xui_clients]
    })


def _normalize_subscription_endpoint_override(data):
    host = (data.get('subscription_host', data.get('host', '')) or '').strip()
    if len(host) > 255:
        raise XuiApiError('订阅地址不能超过 255 个字符', 400)
    if host and re.search(r'\s', host):
        raise XuiApiError('订阅地址不能包含空格', 400)
    if host and (re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', host) or any(ch in host for ch in '/?#')):
        raise XuiApiError('订阅地址只填写 IP 或域名，不需要协议和路径', 400)

    raw_port = data.get('subscription_port', data.get('port', 0))
    if raw_port in (None, ''):
        port = 0
    else:
        try:
            port = int(raw_port)
        except (TypeError, ValueError):
            raise XuiApiError('订阅端口必须是数字', 400)
        if port != 0 and not (1 <= port <= 65535):
            raise XuiApiError('订阅端口必须在 1-65535 之间', 400)

    return host, port


@app.route('/api/users/<int:user_id>/xui-clients/<int:mapping_id>/subscription-endpoint', methods=['PUT'])
@login_required
def update_user_xui_subscription_endpoint(user_id, mapping_id):
    user = User.query.get_or_404(user_id)
    mapping = UserXuiClient.query.filter_by(id=mapping_id, user_id=user.id).first_or_404()
    data = request.get_json() or {}

    try:
        host, port = _normalize_subscription_endpoint_override(data)
        mapping.subscription_host = host
        mapping.subscription_port = port
        mapping.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify({
            'success': True,
            'client': _serialize_user_xui_client(mapping)
        })
    except XuiApiError as e:
        db.session.rollback()
        return _xui_error_response(e)


@app.route('/api/users/<int:user_id>/xui-clients/<int:mapping_id>', methods=['PUT', 'DELETE'])
@login_required
def update_user_xui_client(user_id, mapping_id):
    user = User.query.get_or_404(user_id)
    mapping = UserXuiClient.query.filter_by(id=mapping_id, user_id=user.id).first_or_404()
    encoded_email = quote_plus(mapping.client_email)

    try:
        if request.method == 'DELETE':
            inbound_id = int(mapping.inbound_id or 0)
            if inbound_id <= 0:
                raise XuiApiError('入站 ID 不正确', 400)
            _xui_request('POST', f'/panel/api/inbounds/del/{inbound_id}', config_id=mapping.backend_id)
            affected_mappings = UserXuiClient.query.filter_by(
                backend_id=mapping.backend_id,
                inbound_id=inbound_id
            ).all()
            affected_users = {
                item.user_id: item.user
                for item in affected_mappings
                if item.user is not None
            }
            for item in affected_mappings:
                db.session.delete(item)
            for affected_user in affected_users.values():
                _recalculate_user_traffic_used(affected_user)
            db.session.commit()
            return jsonify({
                'success': True,
                'deleted_inbound_id': inbound_id,
                'deleted_mappings': len(affected_mappings)
            })

        data = request.get_json() or {}
        current_data = _xui_request('GET', f'/panel/api/clients/get/{encoded_email}', config_id=mapping.backend_id)
        current_obj = _xui_obj(current_data) or {}
        current_client = current_obj.get('client') if isinstance(current_obj, dict) else {}
        raw_inbound = _safe_json_loads(mapping.raw_inbound, {})
        inbound_for_credentials = {
            'protocol': mapping.inbound_protocol,
            'settings': _safe_json_loads(raw_inbound.get('settings'), {})
        }
        remote_inbound = _xui_fetch_inbound_by_id(mapping.backend_id, mapping.inbound_id)
        if remote_inbound and (
            _xui_find_inbound_client(remote_inbound, mapping.client_email)
            or not _xui_find_inbound_client(inbound_for_credentials, mapping.client_email)
        ):
            inbound_for_credentials = remote_inbound

        ignored_client_fields = {'total_gb', 'expiry_time', 'expiry_days', 'reset', 'totalGB', 'total', 'expiryTime'}
        payload_data = {
            key: value
            for key, value in data.items()
            if key not in ignored_client_fields
        }
        payload_data['email'] = mapping.client_email
        if not payload_data.get('sub_id') and mapping.sub_id:
            payload_data['sub_id'] = mapping.sub_id
        payload = _build_client_payload(payload_data, current_client)
        _strip_user_xui_client_limits(payload)
        _ensure_xui_client_credentials(payload, inbound_for_credentials)
        _xui_request('POST', f'/panel/api/clients/update/{encoded_email}', json_body=payload, config_id=mapping.backend_id)
        updated_inbound = _update_user_xui_inbound_limits(mapping.backend_id, mapping.inbound_id, data, remote_inbound)
        if updated_inbound:
            _cache_user_xui_mapping(mapping, inbound=updated_inbound)
        if 'display_name' in data:
            mapping.display_name = (data.get('display_name') or '').strip() or mapping.display_name
        db.session.flush()
        _sync_user_xui_clients(user, raise_errors=True)
        if mapping.last_error:
            raise XuiApiError(mapping.last_error, 502)
        return jsonify({'success': True, 'client': _serialize_user_xui_client(mapping)})
    except XuiApiError as e:
        db.session.rollback()
        return _xui_error_response(e)


@app.route('/api/users/<int:user_id>/nodes', methods=['GET', 'POST'])
@login_required
def manage_user_nodes(user_id):
    """Manage nodes directly assigned to a user, including per-node limits."""
    user = User.query.get_or_404(user_id)

    if request.method == 'GET':
        assignments = sorted(
            user.node_assignments,
            key=lambda item: (
                item.node.order if item.node and item.node.order is not None else 0,
                item.node_id
            )
        )
        return jsonify([_serialize_user_node_assignment(assignment) for assignment in assignments])

    data = request.get_json() or {}
    raw_assignments = data.get('assignments')
    if raw_assignments is None and 'node_ids' in data:
        raw_assignments = [{'node_id': node_id} for node_id in data.get('node_ids') or []]
    if not isinstance(raw_assignments, list):
        return jsonify({'success': False, 'message': 'assignments 必须是数组'}), 400

    normalized = []
    seen_node_ids = set()
    try:
        for item in raw_assignments:
            if not isinstance(item, dict):
                return jsonify({'success': False, 'message': '节点配置格式不正确'}), 400
            node_id = int(item.get('node_id') or 0)
            if node_id <= 0 or node_id in seen_node_ids:
                continue
            seen_node_ids.add(node_id)
            traffic_used = None
            if 'traffic_used_gb' in item:
                traffic_used = _gb_to_bytes(item.get('traffic_used_gb'), 0)
            elif 'traffic_used' in item:
                traffic_used = int(item.get('traffic_used') or 0)
            normalized.append({
                'node_id': node_id,
                'traffic_limit': _gb_to_bytes(item.get('traffic_limit_gb'), item.get('traffic_limit') or 0),
                'traffic_used': max(0, traffic_used) if traffic_used is not None else None,
                'expiry_time': _coerce_ms_timestamp(item.get('expiry_time'), 0)
            })
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': '节点 ID 必须是数字'}), 400
    except XuiApiError as e:
        return jsonify({'success': False, 'message': e.message}), 400

    if normalized:
        found_node_ids = {
            node.id for node in Node.query.filter(Node.id.in_([item['node_id'] for item in normalized])).all()
        }
        missing_node_ids = sorted(seen_node_ids - found_node_ids)
        if missing_node_ids:
            return jsonify({
                'success': False,
                'message': f'节点不存在: {", ".join(map(str, missing_node_ids))}'
            }), 400

    existing_usage = {
        assignment.node_id: assignment.traffic_used or 0
        for assignment in UserNode.query.filter_by(user_id=user.id).all()
    }
    UserNode.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    db.session.flush()

    for item in normalized:
        traffic_used = (
            item['traffic_used']
            if item['traffic_used'] is not None
            else existing_usage.get(item['node_id'], 0)
        )
        db.session.add(UserNode(
            user_id=user.id,
            node_id=item['node_id'],
            traffic_limit=item['traffic_limit'],
            traffic_used=traffic_used,
            expiry_time=item['expiry_time']
        ))

    _recalculate_user_traffic_used(user)
    db.session.commit()

    return jsonify({'success': True, 'count': len(normalized)})


@app.route('/api/users/<int:user_id>/nodes/create', methods=['POST'])
@login_required
def create_user_node(user_id):
    """Create a node from the user modal and assign it to this user."""
    user = User.query.get_or_404(user_id)
    data = request.get_json() or {}

    try:
        proxy = _parse_node_config_input(data.get('url'))
        node = _create_node_from_proxy(proxy, data.get('name') or None, None)
        db.session.flush()

        assignment = UserNode(
            user_id=user.id,
            node_id=node.id,
            traffic_limit=_gb_to_bytes(data.get('traffic_limit_gb'), 0),
            traffic_used=_gb_to_bytes(data.get('traffic_used_gb'), 0),
            expiry_time=_coerce_ms_timestamp(data.get('expiry_time'), 0)
        )
        db.session.add(assignment)
        _recalculate_user_traffic_used(user)
        db.session.commit()
    except XuiApiError as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': e.message}), e.status_code
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

    return jsonify({
        'success': True,
        'node': {
            'id': node.id,
            'name': node.name,
            'protocol': node.protocol,
            'subscription_name': '手动添加'
        },
        'assignment': _serialize_user_node_assignment(assignment)
    })


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
    started_at = time.perf_counter()
    stats = {}

    # 先尝试用custom_slug查找，再用subscription_token查找
    user = User.query.filter_by(custom_slug=token).first()
    if not user:
        user = User.query.filter_by(subscription_token=token).first()
    
    if not user or not user.enabled:
        return "Invalid subscription", 404

    _sync_user_xui_clients_if_stale(user, max_age_seconds=60)

    if user.traffic_limit and _user_traffic_used_bytes(user) >= user.traffic_limit:
        return "Traffic limit exceeded", 403

    use_subscription_cache = not bool(user.node_assignments or user.xui_clients)
    if use_subscription_cache:
        cache_entry = _get_subscription_cache('user', user.id)
        if cache_entry:
            _log_subscription_timing('user', user.username, 'HIT', cache_entry.get('stats', {}), started_at)
            return _make_subscription_response(cache_entry, 'HIT')
    
    # 获取用户的所有订阅下的所有节点，并按排序字段排序
    collect_start = time.perf_counter()
    all_nodes = []
    for subscription in user.subscriptions:
        all_nodes.extend(subscription.nodes)
    direct_assignments = _active_user_node_assignments(user)
    all_nodes.extend([assignment.node for assignment in direct_assignments if assignment.node])
    all_nodes = _dedupe_nodes(all_nodes)
    xui_proxies = _build_xui_subscription_proxies(user)
    stats['collect_ms'] = (time.perf_counter() - collect_start) * 1000
    
    if not all_nodes and not xui_proxies:
        return "No nodes available", 404
    
    # 按order字段排序节点
    all_nodes.sort(key=lambda n: (n.order if hasattr(n, 'order') and n.order is not None else 0, n.id))
    
    # 如果用户设置了模板，使用模板生成
    template_content = None
    if user.template_id:
        template = Template.query.get(user.template_id)
        if template:
            template_content = template.content

    filename = f'clash_{user.username}.yaml'
    cache_entry = _build_subscription_cache_entry(
        'user',
        user.id,
        user.username,
        filename,
        all_nodes,
        f"🚀 {user.username} 专属",
        template_content,
        extra_proxies=xui_proxies
    )
    cache_entry['subscription_userinfo'] = _user_subscription_userinfo(user)
    if not use_subscription_cache:
        _subscription_cache.pop(('user', user.id), None)
    cache_entry['stats']['collect_ms'] = stats['collect_ms']
    _log_subscription_timing('user', user.username, 'MISS', cache_entry['stats'], started_at)

    return _make_subscription_response(cache_entry, 'MISS')


@app.route('/sub/user/<token>/shadowrocket')
def user_shadowrocket_subscription(token):
    """用户 Shadowrocket 订阅接口（Base64 编码的标准分享链接列表）。"""
    started_at = time.perf_counter()

    user = User.query.filter_by(custom_slug=token).first()
    if not user:
        user = User.query.filter_by(subscription_token=token).first()

    if not user or not user.enabled:
        return "Invalid subscription", 404

    _sync_user_xui_clients_if_stale(user, max_age_seconds=60)

    if user.traffic_limit and _user_traffic_used_bytes(user) >= user.traffic_limit:
        return "Traffic limit exceeded", 403

    use_subscription_cache = not bool(user.node_assignments or user.xui_clients)
    if use_subscription_cache:
        cache_entry = _get_subscription_cache('shadowrocket-user', user.id)
        if cache_entry:
            _log_subscription_timing(
                'shadowrocket-user',
                user.username,
                'HIT',
                cache_entry.get('stats', {}),
                started_at
            )
            return _make_shadowrocket_subscription_response(cache_entry, 'HIT')

    collect_start = time.perf_counter()
    all_nodes = []
    for subscription in user.subscriptions:
        all_nodes.extend(subscription.nodes)
    direct_assignments = _active_user_node_assignments(user)
    all_nodes.extend([assignment.node for assignment in direct_assignments if assignment.node])
    all_nodes = _dedupe_nodes(all_nodes)
    all_nodes.sort(key=lambda n: (n.order if hasattr(n, 'order') and n.order is not None else 0, n.id))

    proxy_configs = []
    for node in all_nodes:
        config = node.get_config()
        config['name'] = node.name
        proxy_configs.append(config)
    proxy_configs.extend(_build_xui_subscription_proxies(user))
    collect_ms = (time.perf_counter() - collect_start) * 1000

    if not proxy_configs:
        return "No nodes available", 404

    generate_start = time.perf_counter()
    body, node_count, skipped_count = _build_shadowrocket_subscription_body(proxy_configs)
    generate_ms = (time.perf_counter() - generate_start) * 1000
    if not node_count:
        return "No Shadowrocket-compatible nodes available", 404

    cache_entry = {
        'body': body,
        'etag': hashlib.sha256(body).hexdigest(),
        'filename': f'shadowrocket_{user.username}.txt',
        'name': user.username,
        'yaml_bytes': len(body),
        'shadowrocket_node_count': node_count,
        'shadowrocket_skipped_count': skipped_count,
        'subscription_userinfo': _user_subscription_userinfo(user),
        'stats': {
            'node_count': len(all_nodes),
            'extra_proxy_count': len(proxy_configs) - len(all_nodes),
            'proxy_count': node_count,
            'yaml_bytes': len(body),
            'collect_ms': collect_ms,
            'deps_ms': 0,
            'generate_ms': generate_ms,
            'yaml_ms': 0,
        }
    }

    if use_subscription_cache:
        cache_entry = _store_subscription_cache('shadowrocket-user', user.id, cache_entry)
    else:
        cache_entry['version'] = _subscription_cache_version

    _log_subscription_timing(
        'shadowrocket-user',
        user.username,
        'MISS',
        cache_entry['stats'],
        started_at
    )
    return _make_shadowrocket_subscription_response(cache_entry, 'MISS')


@app.route('/sub/subscription/<token>')
def subscription_access(token):
    """订阅分组访问接口（支持自定义后缀和系统token）"""
    started_at = time.perf_counter()
    stats = {}

    # 先尝试用custom_slug查找，再用subscription_token查找
    subscription = Subscription.query.filter_by(custom_slug=token).first()
    if not subscription:
        subscription = Subscription.query.filter_by(subscription_token=token).first()
    
    if not subscription:
        return "Invalid subscription", 404

    cache_entry = _get_subscription_cache('subscription', subscription.id)
    if cache_entry:
        _log_subscription_timing('subscription', subscription.name, 'HIT', cache_entry.get('stats', {}), started_at)
        return _make_subscription_response(cache_entry, 'HIT')
    
    if not subscription.nodes:
        return "No nodes available", 404
    
    # 按order字段排序节点
    collect_start = time.perf_counter()
    sorted_nodes = sorted(subscription.nodes, key=lambda n: (n.order if hasattr(n, 'order') and n.order is not None else 0, n.id))
    stats['collect_ms'] = (time.perf_counter() - collect_start) * 1000
    
    # 如果订阅分组设置了模板，使用模板生成
    template_content = None
    if subscription.template_id:
        template = Template.query.get(subscription.template_id)
        if template:
            template_content = template.content

    filename = f'clash_{subscription.name}.yaml'
    cache_entry = _build_subscription_cache_entry(
        'subscription',
        subscription.id,
        subscription.name,
        filename,
        sorted_nodes,
        f"📡 {subscription.name}",
        template_content
    )
    cache_entry['stats']['collect_ms'] = stats['collect_ms']
    _log_subscription_timing('subscription', subscription.name, 'MISS', cache_entry['stats'], started_at)

    return _make_subscription_response(cache_entry, 'MISS')


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
        template_content = yaml.dump(
            new_config,
            Dumper=YamlDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False
        )
        
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


# ============ 3x-ui 后端对接 API ============

@app.route('/api/xui/settings', methods=['GET', 'POST'])
@login_required
def xui_settings():
    """兼容旧前端的单后端入口：读取或保存第一条 3x-ui 后端配置。"""
    config = _get_xui_config(create_default=True)

    if request.method == 'GET':
        return jsonify(config.to_public_dict())

    data = request.get_json() or {}
    try:
        data.setdefault('name', config.name or '默认后端')
        _apply_xui_config_data(config, data)
    except XuiApiError as e:
        return _xui_error_response(e)

    db.session.commit()
    return jsonify({'success': True, 'settings': config.to_public_dict()})


@app.route('/api/xui/backends', methods=['GET', 'POST'])
@login_required
def xui_backends():
    """获取或新增 3x-ui 后端配置"""
    if request.method == 'GET':
        backends = XuiConfig.query.order_by(XuiConfig.id.asc()).all()
        return jsonify({
            'success': True,
            'backends': [backend.to_public_dict() for backend in backends]
        })

    data = request.get_json() or {}
    backend = XuiConfig(name=(data.get('name') or '').strip() or '新后端')
    try:
        _apply_xui_config_data(backend, data)
    except XuiApiError as e:
        return _xui_error_response(e)

    db.session.add(backend)
    db.session.commit()
    return jsonify({'success': True, 'backend': backend.to_public_dict()})


@app.route('/api/xui/backends/test-draft', methods=['POST'])
@login_required
def xui_backend_test_draft():
    """测试尚未保存的 3x-ui 后端配置。"""
    data = request.get_json() or {}
    backend_id = data.get('backend_id')
    existing = None
    if backend_id:
        try:
            existing = _get_xui_config(backend_id)
        except XuiApiError as e:
            return _xui_error_response(e)

    backend = XuiConfig(
        name=(existing.name if existing else '测试后端'),
        base_url=(existing.base_url if existing else ''),
        auth_mode=(existing.auth_mode if existing else 'token'),
        username=(existing.username if existing else ''),
        password=(existing.password if existing else None),
        api_token=(existing.api_token if existing else None),
        verify_ssl=(existing.verify_ssl if existing else True),
        timeout=(existing.timeout if existing else 15)
    )

    try:
        _apply_xui_config_data(backend, data)
        status_data = _xui_request_with_config(backend, 'GET', '/panel/api/server/status')
        return jsonify({
            'success': True,
            'online': True,
            'message': '连接成功',
            'status': _xui_obj(status_data)
        })
    except XuiApiError as e:
        return jsonify({
            'success': False,
            'online': False,
            'message': e.message,
            'payload': e.payload
        }), 200


@app.route('/api/xui/backends/<int:backend_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def xui_backend_detail(backend_id):
    """获取、修改或删除一个 3x-ui 后端配置"""
    try:
        backend = _get_xui_config(backend_id)
    except XuiApiError as e:
        return _xui_error_response(e)

    if request.method == 'GET':
        return jsonify({'success': True, 'backend': backend.to_public_dict()})

    if request.method == 'DELETE':
        db.session.delete(backend)
        db.session.commit()
        return jsonify({'success': True})

    data = request.get_json() or {}
    try:
        _apply_xui_config_data(backend, data)
    except XuiApiError as e:
        return _xui_error_response(e)

    db.session.commit()
    return jsonify({'success': True, 'backend': backend.to_public_dict()})


@app.route('/api/xui/backends/<int:backend_id>/test', methods=['POST'])
@login_required
def xui_backend_test_connection(backend_id):
    """测试指定 3x-ui 后端连接"""
    try:
        data = _xui_request('GET', '/panel/api/server/status', config_id=backend_id)
        status = _xui_obj(data)
        backend = _get_xui_config(backend_id)
        return jsonify({
            'success': True,
            'online': True,
            'message': '连接成功',
            'backend': backend.to_public_dict(),
            'status': status
        })
    except XuiApiError as e:
        return jsonify({
            'success': False,
            'online': False,
            'message': e.message,
            'payload': e.payload
        }), 200


@app.route('/api/xui/test', methods=['POST'])
@login_required
def xui_test_connection():
    """测试 3x-ui 连接"""
    try:
        backend_id = _get_xui_backend_id(request.get_json(silent=True) or {})
        data = _xui_request('GET', '/panel/api/server/status', config_id=backend_id)
        status = _xui_obj(data)
        return jsonify({
            'success': True,
            'online': True,
            'message': '连接成功',
            'status': status
        })
    except XuiApiError as e:
        return jsonify({
            'success': False,
            'online': False,
            'message': e.message,
            'payload': e.payload
        }), 200


@app.route('/api/xui/server/status', methods=['GET'])
@login_required
def xui_server_status():
    """获取 3x-ui 服务器状态"""
    try:
        backend_id = _get_xui_backend_id()
        data = _xui_request('GET', '/panel/api/server/status', config_id=backend_id)
        status = _xui_obj(data) or {}
        backend = _get_xui_config(backend_id)
        return jsonify({
            'success': True,
            'online': True,
            'backend': backend.to_public_dict(),
            'status': status,
            'cpu': status.get('cpu'),
            'load': status.get('load') or {},
            'memory': status.get('mem') or {},
            'swap': status.get('swap') or {},
            'disk': status.get('disk') or {},
            'xray': status.get('xray') or {},
            'tcpCount': status.get('tcpCount')
        })
    except XuiApiError as e:
        return jsonify({
            'success': False,
            'online': False,
            'message': e.message,
            'payload': e.payload
        }), 200


@app.route('/api/xui/server/web-cert-files', methods=['GET'])
@login_required
def xui_server_web_cert_files():
    """获取 3x-ui 面板 Web 证书文件路径。"""
    try:
        backend_id = _get_xui_backend_id()
        data = _xui_request('GET', '/panel/api/server/getWebCertFiles', config_id=backend_id)
        return jsonify({
            'success': True,
            'cert': _xui_obj(data) or {},
            'payload': data
        })
    except XuiApiError as e:
        return _xui_error_response(e)


@app.route('/api/xui/server/ech-cert', methods=['POST'])
@login_required
def xui_server_ech_cert():
    """向 3x-ui 请求生成 ECH 证书配置。"""
    try:
        request_data = request.get_json(silent=True) or {}
        backend_id = _get_xui_backend_id(request_data)
        sni = (request_data.get('sni') or request_data.get('serverName') or '').strip()
        if not sni:
            raise XuiApiError('请先填写 SNI', 400)
        data = _xui_request(
            'POST',
            '/panel/api/server/getNewEchCert',
            json_body={'sni': sni, 'serverName': sni, 'domain': sni},
            config_id=backend_id
        )
        return jsonify({
            'success': True,
            'cert': _xui_obj(data) or {},
            'payload': data
        })
    except XuiApiError as e:
        return _xui_error_response(e)


def _xui_server_helper(endpoint, response_key='obj'):
    backend_id = _get_xui_backend_id()
    data = _xui_request('GET', endpoint, config_id=backend_id)
    return jsonify({
        'success': True,
        response_key: _xui_obj(data) or {},
        'payload': data
    })


@app.route('/api/xui/server/x25519-cert', methods=['GET'])
@login_required
def xui_server_x25519_cert():
    """Proxy 3x-ui Reality X25519 keypair generation."""
    try:
        return _xui_server_helper('/panel/api/server/getNewX25519Cert', 'cert')
    except XuiApiError as e:
        return _xui_error_response(e)


@app.route('/api/xui/server/mldsa65', methods=['GET'])
@login_required
def xui_server_mldsa65():
    """Proxy 3x-ui ML-DSA-65 seed generation."""
    try:
        return _xui_server_helper('/panel/api/server/getNewmldsa65', 'seed')
    except XuiApiError as e:
        return _xui_error_response(e)


@app.route('/api/xui/server/mlkem768', methods=['GET'])
@login_required
def xui_server_mlkem768():
    """Proxy 3x-ui ML-KEM-768 keypair generation."""
    try:
        return _xui_server_helper('/panel/api/server/getNewmlkem768', 'kem')
    except XuiApiError as e:
        return _xui_error_response(e)


@app.route('/api/xui/server/vless-auth', methods=['GET'])
@login_required
def xui_server_vless_auth():
    """Proxy 3x-ui VLESS encryption/auth option generation."""
    try:
        return _xui_server_helper('/panel/api/server/getNewVlessEnc', 'auth')
    except XuiApiError as e:
        return _xui_error_response(e)


@app.route('/api/xui/inbounds', methods=['GET', 'POST'])
@login_required
def xui_inbounds():
    """查看或新建 3x-ui 入站节点"""
    try:
        request_data = request.get_json(silent=True) or {}
        backend_id = _get_xui_backend_id(request_data)
        if request.method == 'GET':
            data = _xui_request('GET', '/panel/api/inbounds/list', config_id=backend_id)
            inbounds = _xui_obj(data) or []
            return jsonify({
                'success': True,
                'backend': _get_xui_config(backend_id).to_public_dict(),
                'inbounds': [_normalize_xui_inbound(item) for item in inbounds]
            })

        payload = _build_inbound_payload(request_data)
        data = _xui_request('POST', '/panel/api/inbounds/add', json_body=payload, config_id=backend_id)
        return jsonify({'success': True, 'message': _xui_message(data, '入站节点已创建'), 'payload': data})
    except XuiApiError as e:
        return _xui_error_response(e)


@app.route('/api/xui/inbounds/<int:inbound_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def xui_inbound_detail(inbound_id):
    """获取、修改或删除 3x-ui 入站节点"""
    try:
        request_data = request.get_json(silent=True) or {}
        backend_id = _get_xui_backend_id(request_data)
        if request.method == 'GET':
            data = _xui_request('GET', f'/panel/api/inbounds/get/{inbound_id}', config_id=backend_id)
            inbound = _xui_obj(data) or {}
            return jsonify({'success': True, 'inbound': _normalize_xui_inbound(inbound)})

        if request.method == 'DELETE':
            data = _xui_request('POST', f'/panel/api/inbounds/del/{inbound_id}', config_id=backend_id)
            affected_mappings = UserXuiClient.query.filter_by(
                backend_id=backend_id,
                inbound_id=inbound_id
            ).all()
            affected_users = {
                item.user_id: item.user
                for item in affected_mappings
                if item.user is not None
            }
            for item in affected_mappings:
                db.session.delete(item)
            for affected_user in affected_users.values():
                _recalculate_user_traffic_used(affected_user)
            db.session.commit()
            return jsonify({
                'success': True,
                'message': _xui_message(data, '入站节点已删除'),
                'payload': data,
                'deleted_mappings': len(affected_mappings)
            })

        current_data = _xui_request('GET', f'/panel/api/inbounds/get/{inbound_id}', config_id=backend_id)
        current = _xui_obj(current_data) or {}
        payload = _build_inbound_payload(request_data, current)
        data = _xui_request('POST', f'/panel/api/inbounds/update/{inbound_id}', json_body=payload, config_id=backend_id)
        return jsonify({'success': True, 'message': _xui_message(data, '入站节点已更新'), 'payload': data})
    except XuiApiError as e:
        return _xui_error_response(e)


@app.route('/api/xui/clients', methods=['GET', 'POST'])
@login_required
def xui_clients():
    """查看或新建 3x-ui 客户端"""
    try:
        request_data = request.get_json(silent=True) or {}
        backend_id = _get_xui_backend_id(request_data)
        if request.method == 'GET':
            inbounds_data = _xui_request('GET', '/panel/api/inbounds/options', config_id=backend_id)
            inbound_options = _xui_obj(inbounds_data) or []
            inbound_map = {item.get('id'): item for item in inbound_options if isinstance(item, dict)}

            clients_data = _xui_request('GET', '/panel/api/clients/list', config_id=backend_id)
            clients = _xui_obj(clients_data) or []

            online_emails = set()
            try:
                online_data = _xui_request('POST', '/panel/api/clients/onlines', config_id=backend_id)
                online_obj = _xui_obj(online_data) or []
                if isinstance(online_obj, list):
                    online_emails = set(str(email) for email in online_obj)
            except XuiApiError:
                online_emails = set()

            return jsonify({
                'success': True,
                'backend': _get_xui_config(backend_id).to_public_dict(),
                'clients': [_normalize_xui_client(item, inbound_map, online_emails) for item in clients],
                'inbounds': [_normalize_xui_inbound(item) for item in inbound_options]
            })

        inbound_ids = request_data.get('inbound_ids') or []
        if not inbound_ids:
            raise XuiApiError('请至少选择一个入站节点', 400)

        payload = {
            'client': _build_client_payload(request_data),
            'inboundIds': [int(inbound_id) for inbound_id in inbound_ids]
        }
        response_data = _xui_request('POST', '/panel/api/clients/add', json_body=payload, config_id=backend_id)
        return jsonify({'success': True, 'message': _xui_message(response_data, '客户端已创建'), 'payload': response_data})
    except XuiApiError as e:
        return _xui_error_response(e)


@app.route('/api/xui/clients/<path:email>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def xui_client_detail(email):
    """获取、修改或删除 3x-ui 客户端"""
    encoded_email = quote_plus(email)

    try:
        request_data = request.get_json(silent=True) or {}
        backend_id = _get_xui_backend_id(request_data)
        if request.method == 'GET':
            data = _xui_request('GET', f'/panel/api/clients/get/{encoded_email}', config_id=backend_id)
            return jsonify({'success': True, 'client': _xui_obj(data)})

        if request.method == 'DELETE':
            data = _xui_request('POST', f'/panel/api/clients/del/{encoded_email}', config_id=backend_id)
            return jsonify({'success': True, 'message': _xui_message(data, '客户端已删除'), 'payload': data})

        current_data = _xui_request('GET', f'/panel/api/clients/get/{encoded_email}', config_id=backend_id)
        current_obj = _xui_obj(current_data) or {}
        current_client = current_obj.get('client') if isinstance(current_obj, dict) else {}
        payload = _build_client_payload(request_data, current_client)
        response_data = _xui_request('POST', f'/panel/api/clients/update/{encoded_email}', json_body=payload, config_id=backend_id)

        inbound_ids = request_data.get('inbound_ids')
        if inbound_ids is not None and isinstance(current_obj, dict):
            current_ids = set(current_obj.get('inboundIds') or [])
            requested_ids = set(int(inbound_id) for inbound_id in inbound_ids)
            attach_ids = list(requested_ids - current_ids)
            detach_ids = list(current_ids - requested_ids)
            if attach_ids:
                _xui_request('POST', f'/panel/api/clients/{encoded_email}/attach', json_body={'inboundIds': attach_ids}, config_id=backend_id)
            if detach_ids:
                _xui_request('POST', f'/panel/api/clients/{encoded_email}/detach', json_body={'inboundIds': detach_ids}, config_id=backend_id)

        return jsonify({'success': True, 'message': _xui_message(response_data, '客户端已更新'), 'payload': response_data})
    except XuiApiError as e:
        return _xui_error_response(e)


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

def _ensure_xui_config_schema():
    """为旧数据库补齐多 3x-ui 后端所需字段。"""
    with db.engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(xui_configs)").fetchall()
        if not rows:
            return

        columns = {row[1] for row in rows}
        if 'name' not in columns:
            conn.exec_driver_sql("ALTER TABLE xui_configs ADD COLUMN name VARCHAR(120)")
        if 'created_at' not in columns:
            conn.exec_driver_sql("ALTER TABLE xui_configs ADD COLUMN created_at DATETIME")
        if 'public_host' not in columns:
            conn.exec_driver_sql("ALTER TABLE xui_configs ADD COLUMN public_host VARCHAR(255)")

        conn.exec_driver_sql(
            "UPDATE xui_configs "
            "SET name = '默认后端 ' || id "
            "WHERE name IS NULL OR name = ''"
        )
        conn.exec_driver_sql(
            "UPDATE xui_configs "
            "SET created_at = COALESCE(updated_at, CURRENT_TIMESTAMP) "
            "WHERE created_at IS NULL"
        )
        conn.exec_driver_sql(
            "UPDATE xui_configs "
            "SET public_host = replace(replace(replace(base_url, 'https://', ''), 'http://', ''), '/panel', '') "
            "WHERE (public_host IS NULL OR public_host = '') AND base_url IS NOT NULL AND base_url != ''"
        )


def _ensure_user_limit_schema():
    """为旧数据库补齐用户额度与用户直接节点分配字段。"""
    with db.engine.begin() as conn:
        user_rows = conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()
        if user_rows:
            user_columns = {row[1] for row in user_rows}
            if 'traffic_limit' not in user_columns:
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN traffic_limit BIGINT DEFAULT 0")
            if 'traffic_used' not in user_columns:
                conn.exec_driver_sql("ALTER TABLE users ADD COLUMN traffic_used BIGINT DEFAULT 0")

        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS user_nodes (
                user_id INTEGER NOT NULL,
                node_id INTEGER NOT NULL,
                traffic_limit BIGINT DEFAULT 0,
                traffic_used BIGINT DEFAULT 0,
                expiry_time BIGINT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, node_id),
                FOREIGN KEY(user_id) REFERENCES users (id),
                FOREIGN KEY(node_id) REFERENCES nodes (id)
            )
            """
        )
        node_rows = conn.exec_driver_sql("PRAGMA table_info(user_nodes)").fetchall()
        node_columns = {row[1] for row in node_rows}
        for column_name, ddl in {
            'traffic_limit': 'ALTER TABLE user_nodes ADD COLUMN traffic_limit BIGINT DEFAULT 0',
            'traffic_used': 'ALTER TABLE user_nodes ADD COLUMN traffic_used BIGINT DEFAULT 0',
            'expiry_time': 'ALTER TABLE user_nodes ADD COLUMN expiry_time BIGINT DEFAULT 0',
            'created_at': 'ALTER TABLE user_nodes ADD COLUMN created_at DATETIME',
            'updated_at': 'ALTER TABLE user_nodes ADD COLUMN updated_at DATETIME',
        }.items():
            if column_name not in node_columns:
                conn.exec_driver_sql(ddl)


def _ensure_user_xui_client_schema():
    """Ensure user-to-3x-ui client mappings exist on upgraded databases."""
    with db.engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS user_xui_clients (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                backend_id INTEGER NOT NULL,
                inbound_id INTEGER NOT NULL,
                inbound_name VARCHAR(255),
                inbound_protocol VARCHAR(40),
                client_email VARCHAR(255) NOT NULL,
                sub_id VARCHAR(255),
                display_name VARCHAR(255),
                comment TEXT,
                flow VARCHAR(80),
                limit_ip INTEGER DEFAULT 0,
                enabled BOOLEAN DEFAULT 1,
                online BOOLEAN DEFAULT 0,
                traffic_up BIGINT DEFAULT 0,
                traffic_down BIGINT DEFAULT 0,
                traffic_used BIGINT DEFAULT 0,
                traffic_limit BIGINT DEFAULT 0,
                expiry_time BIGINT DEFAULT 0,
                subscription_host VARCHAR(255) DEFAULT '',
                subscription_port INTEGER DEFAULT 0,
                raw_client TEXT,
                raw_inbound TEXT,
                last_sync_at DATETIME,
                last_error TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users (id),
                FOREIGN KEY(backend_id) REFERENCES xui_configs (id)
            )
            """
        )
        rows = conn.exec_driver_sql("PRAGMA table_info(user_xui_clients)").fetchall()
        columns = {row[1] for row in rows}
        for column_name, ddl in {
            'inbound_name': 'ALTER TABLE user_xui_clients ADD COLUMN inbound_name VARCHAR(255)',
            'inbound_protocol': 'ALTER TABLE user_xui_clients ADD COLUMN inbound_protocol VARCHAR(40)',
            'sub_id': 'ALTER TABLE user_xui_clients ADD COLUMN sub_id VARCHAR(255)',
            'display_name': 'ALTER TABLE user_xui_clients ADD COLUMN display_name VARCHAR(255)',
            'comment': 'ALTER TABLE user_xui_clients ADD COLUMN comment TEXT',
            'flow': 'ALTER TABLE user_xui_clients ADD COLUMN flow VARCHAR(80)',
            'limit_ip': 'ALTER TABLE user_xui_clients ADD COLUMN limit_ip INTEGER DEFAULT 0',
            'enabled': 'ALTER TABLE user_xui_clients ADD COLUMN enabled BOOLEAN DEFAULT 1',
            'online': 'ALTER TABLE user_xui_clients ADD COLUMN online BOOLEAN DEFAULT 0',
            'traffic_up': 'ALTER TABLE user_xui_clients ADD COLUMN traffic_up BIGINT DEFAULT 0',
            'traffic_down': 'ALTER TABLE user_xui_clients ADD COLUMN traffic_down BIGINT DEFAULT 0',
            'traffic_used': 'ALTER TABLE user_xui_clients ADD COLUMN traffic_used BIGINT DEFAULT 0',
            'traffic_limit': 'ALTER TABLE user_xui_clients ADD COLUMN traffic_limit BIGINT DEFAULT 0',
            'expiry_time': 'ALTER TABLE user_xui_clients ADD COLUMN expiry_time BIGINT DEFAULT 0',
            'subscription_host': "ALTER TABLE user_xui_clients ADD COLUMN subscription_host VARCHAR(255) DEFAULT ''",
            'subscription_port': 'ALTER TABLE user_xui_clients ADD COLUMN subscription_port INTEGER DEFAULT 0',
            'raw_client': 'ALTER TABLE user_xui_clients ADD COLUMN raw_client TEXT',
            'raw_inbound': 'ALTER TABLE user_xui_clients ADD COLUMN raw_inbound TEXT',
            'last_sync_at': 'ALTER TABLE user_xui_clients ADD COLUMN last_sync_at DATETIME',
            'last_error': 'ALTER TABLE user_xui_clients ADD COLUMN last_error TEXT',
            'created_at': 'ALTER TABLE user_xui_clients ADD COLUMN created_at DATETIME',
            'updated_at': 'ALTER TABLE user_xui_clients ADD COLUMN updated_at DATETIME',
        }.items():
            if column_name not in columns:
                conn.exec_driver_sql(ddl)

        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_xui_client_backend_email "
            "ON user_xui_clients (backend_id, client_email)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_user_xui_client_user_id "
            "ON user_xui_clients (user_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_user_xui_client_backend_id "
            "ON user_xui_clients (backend_id)"
        )


def init_db():
    """初始化数据库"""
    with app.app_context():
        try:
            db.create_all()
            _ensure_xui_config_schema()
            _ensure_user_limit_schema()
            _ensure_user_xui_client_schema()
            
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
