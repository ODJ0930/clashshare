"""
协议解析器模块
支持 SS, SSR, VMess, VLESS, Hysteria2 等协议的解析
"""

import base64
import json
import re
import urllib.parse
from typing import Dict, List, Optional, Any


class ProxyParser:
    """代理协议解析器基类"""
    
    @staticmethod
    def parse_ss(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 Shadowsocks 链接
        支持格式:
        - ss://base64(method:password)@server:port#name
        - ss://base64(method:password@server:port)#name
        - ss://base64(method:password)@server:port?params#name (SIP002)
        - 支持 Shadowsocks 2022 (2022-blake3-aes-256-gcm 等)
        """
        try:
            if not url.startswith('ss://'):
                return None
            
            url = url[5:]  # 移除 ss://
            
            # 分离备注名称
            name = "SS节点"
            if '#' in url:
                url, name = url.split('#', 1)
                name = urllib.parse.unquote(name)
            
            # 分离 URL 参数 (SIP002 格式)
            params = {}
            if '?' in url:
                url, params_str = url.split('?', 1)
                params = urllib.parse.parse_qs(params_str)
            
            # 解码 base64
            if '@' in url:
                # 新格式: base64部分@server:port
                parts = url.split('@', 1)
                if len(parts) == 2:
                    base64_part = parts[0]
                    server_port = parts[1]
                    
                    # URL 解码（处理 %3D 等编码字符）
                    base64_part = urllib.parse.unquote(base64_part)
                    
                    # 添加 padding 并解码
                    padding = '=' * (4 - len(base64_part) % 4)
                    if padding == '====':
                        padding = ''
                    
                    try:
                        decoded = base64.b64decode(base64_part + padding).decode('utf-8')
                    except:
                        # 尝试 URL-safe base64
                        try:
                            decoded = base64.urlsafe_b64decode(base64_part + padding).decode('utf-8')
                        except:
                            # 如果仍然失败，可能不需要 padding
                            try:
                                decoded = base64.b64decode(base64_part).decode('utf-8')
                            except:
                                decoded = base64.urlsafe_b64decode(base64_part).decode('utf-8')
                    
                    # 解析 method:password
                    if ':' in decoded:
                        method, password = decoded.split(':', 1)
                    else:
                        return None
                    
                    # 解析 server:port
                    if ':' in server_port:
                        server, port = server_port.rsplit(':', 1)
                    else:
                        return None
                else:
                    # 旧格式: 全部base64编码
                    padding = '=' * (4 - len(url) % 4)
                    if padding == '====':
                        padding = ''
                    
                    decoded = base64.b64decode(url + padding).decode('utf-8')
                    if '@' not in decoded:
                        return None
                    method_password, server_port = decoded.split('@', 1)
                    method, password = method_password.split(':', 1)
                    server, port = server_port.rsplit(':', 1)
            else:
                # 旧格式: 全部base64编码
                padding = '=' * (4 - len(url) % 4)
                if padding == '====':
                    padding = ''
                    
                decoded = base64.b64decode(url + padding).decode('utf-8')
                if '@' not in decoded:
                    return None
                method_password, server_port = decoded.split('@', 1)
                method, password = method_password.split(':', 1)
                server, port = server_port.rsplit(':', 1)
            
            node = {
                'name': name,
                'type': 'ss',
                'server': server.strip(),
                'port': int(port.strip()),
                'cipher': method.strip(),
                'password': password.strip(),
            }
            
            # 处理 URL 参数 (SIP002 格式)
            if params:
                # UDP 支持
                if 'udp' in params:
                    node['udp'] = params['udp'][0] == 'true' or params['udp'][0] == '1'
                
                # udp-over-tcp
                if 'uot' in params:
                    node['udp-over-tcp'] = params['uot'][0] == 'true' or params['uot'][0] == '1'
                
                # plugin 参数 (SIP002 格式: plugin=name;opt1=val1;opt2=val2)
                if 'plugin' in params:
                    plugin_str = params['plugin'][0]
                    plugin_parts = plugin_str.split(';')
                    
                    if plugin_parts:
                        plugin_name = plugin_parts[0]
                        plugin_opts = {}
                        
                        # 解析插件选项
                        for part in plugin_parts[1:]:
                            if '=' in part:
                                key, value = part.split('=', 1)
                                plugin_opts[key] = value
                        
                        # 识别插件类型并转换为 Clash 格式
                        if 'obfs' in plugin_name:
                            # obfs-local 插件
                            node['plugin'] = 'obfs'
                            node['plugin-opts'] = {}
                            if 'obfs' in plugin_opts:
                                node['plugin-opts']['mode'] = plugin_opts['obfs']
                            if 'obfs-host' in plugin_opts:
                                node['plugin-opts']['host'] = plugin_opts['obfs-host']
                        
                        elif 'v2ray' in plugin_name:
                            # v2ray-plugin
                            node['plugin'] = 'v2ray-plugin'
                            node['plugin-opts'] = {}
                            if 'mode' in plugin_opts or 'transport' in plugin_opts:
                                mode = plugin_opts.get('mode') or plugin_opts.get('transport', 'websocket')
                                node['plugin-opts']['mode'] = mode
                            if 'tls' in plugin_opts:
                                node['plugin-opts']['tls'] = plugin_opts['tls'] == 'true' or plugin_opts['tls'] == '1'
                            if 'host' in plugin_opts:
                                node['plugin-opts']['host'] = plugin_opts['host']
                            if 'path' in plugin_opts:
                                node['plugin-opts']['path'] = plugin_opts['path']
                            if 'mux' in plugin_opts:
                                node['plugin-opts']['mux'] = plugin_opts['mux'] == 'true' or plugin_opts['mux'] == '1'
                            if 'skip-cert-verify' in plugin_opts:
                                node['plugin-opts']['skip-cert-verify'] = plugin_opts['skip-cert-verify'] == 'true'
                        
                        elif 'gost' in plugin_name:
                            # gost-plugin
                            node['plugin'] = 'gost-plugin'
                            node['plugin-opts'] = {}
                            if 'mode' in plugin_opts:
                                node['plugin-opts']['mode'] = plugin_opts['mode']
                            if 'host' in plugin_opts:
                                node['plugin-opts']['host'] = plugin_opts['host']
                            if 'path' in plugin_opts:
                                node['plugin-opts']['path'] = plugin_opts['path']
                        
                        elif 'shadow-tls' in plugin_name or 'shadowtls' in plugin_name:
                            # shadow-tls
                            node['plugin'] = 'shadow-tls'
                            node['plugin-opts'] = {}
                            if 'host' in plugin_opts:
                                node['plugin-opts']['host'] = plugin_opts['host']
                            if 'password' in plugin_opts:
                                node['plugin-opts']['password'] = plugin_opts['password']
                            if 'version' in plugin_opts:
                                node['plugin-opts']['version'] = int(plugin_opts['version'])
                            if 'client-fingerprint' in plugin_opts or 'fp' in plugin_opts:
                                fp = plugin_opts.get('client-fingerprint') or plugin_opts.get('fp')
                                node['client-fingerprint'] = fp
                        
                        elif 'restls' in plugin_name:
                            # restls
                            node['plugin'] = 'restls'
                            node['plugin-opts'] = {}
                            if 'host' in plugin_opts:
                                node['plugin-opts']['host'] = plugin_opts['host']
                            if 'password' in plugin_opts:
                                node['plugin-opts']['password'] = plugin_opts['password']
                            if 'version-hint' in plugin_opts:
                                node['plugin-opts']['version-hint'] = plugin_opts['version-hint']
                            if 'restls-script' in plugin_opts:
                                node['plugin-opts']['restls-script'] = plugin_opts['restls-script']
                            if 'client-fingerprint' in plugin_opts or 'fp' in plugin_opts:
                                fp = plugin_opts.get('client-fingerprint') or plugin_opts.get('fp')
                                node['client-fingerprint'] = fp
                        
                        elif 'kcptun' in plugin_name:
                            # kcptun
                            node['plugin'] = 'kcptun'
                            node['plugin-opts'] = {}
                            # kcptun 有很多参数，按需解析
                            for key in ['key', 'crypt', 'mode', 'mtu', 'sndwnd', 'rcvwnd', 
                                       'datashard', 'parityshard', 'dscp', 'nocomp']:
                                if key in plugin_opts:
                                    if key in ['nocomp']:
                                        node['plugin-opts'][key] = plugin_opts[key] == 'true'
                                    elif key in ['mtu', 'sndwnd', 'rcvwnd', 'datashard', 'parityshard', 'dscp']:
                                        node['plugin-opts'][key] = int(plugin_opts[key])
                                    else:
                                        node['plugin-opts'][key] = plugin_opts[key]
            
            return node
        except Exception as e:
            print(f"解析 SS 链接失败: {e}, URL: {url[:100]}")
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    def parse_ssr(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 ShadowsocksR 链接
        格式: ssr://base64(server:port:protocol:method:obfs:password_base64/?params)
        """
        try:
            if not url.startswith('ssr://'):
                return None
            
            url = url[6:]  # 移除 ssr://
            decoded = base64.b64decode(url + '=' * (4 - len(url) % 4)).decode('utf-8')
            
            # 分离主体和参数
            main_part, _, params_part = decoded.partition('/?')
            
            # 解析主体
            parts = main_part.split(':')
            if len(parts) != 6:
                return None
            
            server, port, protocol, method, obfs, password_b64 = parts
            password = base64.b64decode(password_b64 + '=' * (4 - len(password_b64) % 4)).decode('utf-8')
            
            # 解析参数
            params = urllib.parse.parse_qs(params_part)
            name = base64.b64decode(params.get('remarks', [b''])[0] + b'=' * 4).decode('utf-8') if params.get('remarks') else 'SSR节点'
            obfs_param = base64.b64decode(params.get('obfsparam', [b''])[0] + b'=' * 4).decode('utf-8') if params.get('obfsparam') else ''
            protocol_param = base64.b64decode(params.get('protoparam', [b''])[0] + b'=' * 4).decode('utf-8') if params.get('protoparam') else ''
            
            return {
                'name': name,
                'type': 'ssr',
                'server': server,
                'port': int(port),
                'cipher': method,
                'password': password,
                'protocol': protocol,
                'obfs': obfs,
                'protocol-param': protocol_param,
                'obfs-param': obfs_param,
            }
        except Exception as e:
            print(f"解析 SSR 链接失败: {e}")
            return None
    
    @staticmethod
    def parse_vmess(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 VMess 链接
        格式: vmess://base64(json)
        """
        try:
            if not url.startswith('vmess://'):
                return None
            
            url = url[8:]  # 移除 vmess://
            decoded = base64.b64decode(url + '=' * (4 - len(url) % 4)).decode('utf-8')
            config = json.loads(decoded)
            
            node = {
                'name': config.get('ps', 'VMess节点'),
                'type': 'vmess',
                'server': config.get('add', ''),
                'port': int(config.get('port', 443)),
                'uuid': config.get('id', ''),
                'alterId': int(config.get('aid', 0)),
                'cipher': config.get('scy', 'auto'),
            }
            
            # 传输协议
            net = config.get('net', 'tcp')
            node['network'] = net
            
            # TLS
            tls = config.get('tls', '')
            if tls == 'tls':
                node['tls'] = True
                if config.get('sni'):
                    node['servername'] = config['sni']
            
            # WebSocket 配置
            if net == 'ws':
                node['ws-opts'] = {
                    'path': config.get('path', '/'),
                }
                if config.get('host'):
                    node['ws-opts']['headers'] = {'Host': config['host']}
            
            # gRPC 配置
            elif net == 'grpc':
                node['grpc-opts'] = {
                    'grpc-service-name': config.get('path', ''),
                }
            
            # HTTP/2 配置
            elif net == 'h2':
                node['h2-opts'] = {
                    'path': config.get('path', '/'),
                }
                if config.get('host'):
                    node['h2-opts']['host'] = [config['host']]
            
            return node
        except Exception as e:
            print(f"解析 VMess 链接失败: {e}")
            return None
    
    @staticmethod
    def parse_vless(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 VLESS 链接
        格式: vless://uuid@server:port?params#name
        """
        try:
            if not url.startswith('vless://'):
                return None
            
            url = url[8:]  # 移除 vless://
            
            # 分离名称
            name = "VLESS节点"
            if '#' in url:
                url, name = url.split('#', 1)
                name = urllib.parse.unquote(name)
            
            # 分离参数
            main_part, _, params_part = url.partition('?')
            
            # 解析主体: uuid@server:port
            uuid, server_port = main_part.split('@', 1)
            server, port = server_port.rsplit(':', 1)
            
            node = {
                'name': name,
                'type': 'vless',
                'server': server,
                'port': int(port),
                'uuid': uuid,
            }
            
            # 解析参数
            if params_part:
                params = urllib.parse.parse_qs(params_part)
                
                # 加密方式
                encryption = params.get('encryption', ['none'])[0]
                
                # 传输协议
                network = params.get('type', ['tcp'])[0]
                node['network'] = network
                
                # 流控 (flow)
                if params.get('flow'):
                    node['flow'] = params['flow'][0]
                
                # TLS/Reality
                security = params.get('security', [''])[0]
                if security == 'tls':
                    node['tls'] = True
                    if params.get('sni'):
                        node['servername'] = params['sni'][0]
                    # 跳过证书验证
                    if params.get('allowInsecure'):
                        node['skip-cert-verify'] = params['allowInsecure'][0] == '1'
                    # 客户端指纹
                    if params.get('fp'):
                        node['client-fingerprint'] = params['fp'][0]
                elif security == 'reality':
                    node['tls'] = True
                    node['reality-opts'] = {}
                    if params.get('pbk'):
                        node['reality-opts']['public-key'] = params['pbk'][0]
                    if params.get('sid'):
                        node['reality-opts']['short-id'] = params['sid'][0]
                    if params.get('sni'):
                        node['servername'] = params['sni'][0]
                    # 跳过证书验证
                    if params.get('allowInsecure'):
                        node['skip-cert-verify'] = params['allowInsecure'][0] == '1'
                    # 客户端指纹
                    if params.get('fp'):
                        node['client-fingerprint'] = params['fp'][0]
                
                # TCP Fast Open
                if params.get('tfo'):
                    node['tfo'] = params['tfo'][0] == '1'
                
                # WebSocket 配置
                if network == 'ws':
                    node['ws-opts'] = {}
                    if params.get('path'):
                        node['ws-opts']['path'] = params['path'][0]
                    if params.get('host'):
                        node['ws-opts']['headers'] = {'Host': params['host'][0]}
                
                # gRPC 配置
                elif network == 'grpc':
                    node['grpc-opts'] = {}
                    if params.get('serviceName'):
                        node['grpc-opts']['grpc-service-name'] = params['serviceName'][0]
                
                # TCP 配置
                elif network == 'tcp':
                    if params.get('headerType', [''])[0] == 'http':
                        node['network'] = 'http'
                        if params.get('path'):
                            node['http-opts'] = {'path': [params['path'][0]]}
            
            return node
        except Exception as e:
            print(f"解析 VLESS 链接失败: {e}")
            return None
    
    @staticmethod
    def parse_hysteria2(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 Hysteria2 链接
        格式: hysteria2://password@server:port?params#name
        或: hy2://password@server:port?params#name
        """
        try:
            if url.startswith('hysteria2://'):
                url = url[12:]
            elif url.startswith('hy2://'):
                url = url[6:]
            else:
                return None
            
            # 分离名称
            name = "Hysteria2节点"
            if '#' in url:
                url, name = url.split('#', 1)
                name = urllib.parse.unquote(name)
            
            # 分离参数
            main_part, _, params_part = url.partition('?')
            
            # 解析主体: password@server:port
            password, server_port = main_part.split('@', 1)
            password = urllib.parse.unquote(password)
            server, port = server_port.rsplit(':', 1)
            
            node = {
                'name': name,
                'type': 'hysteria2',
                'server': server,
                'port': int(port),
                'password': password,
            }
            
            # 解析参数
            if params_part:
                params = urllib.parse.parse_qs(params_part)
                
                # SNI
                if params.get('sni'):
                    node['sni'] = params['sni'][0]
                
                # 跳过证书验证
                if params.get('insecure', [''])[0] == '1':
                    node['skip-cert-verify'] = True
                
                # 混淆
                if params.get('obfs'):
                    node['obfs'] = params['obfs'][0]
                if params.get('obfs-password'):
                    node['obfs-password'] = params['obfs-password'][0]
            
            return node
        except Exception as e:
            print(f"解析 Hysteria2 链接失败: {e}")
            return None
    
    @staticmethod
    def parse_trojan(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 Trojan 链接
        格式: trojan://password@server:port?params#name
        支持 Reality
        """
        try:
            if not url.startswith('trojan://'):
                return None
            
            url = url[9:]  # 移除 trojan://
            
            # 分离名称
            name = "Trojan节点"
            if '#' in url:
                url, name = url.split('#', 1)
                name = urllib.parse.unquote(name)
            
            # 分离参数
            main_part, _, params_part = url.partition('?')
            
            # 解析主体: password@server:port
            password, server_port = main_part.split('@', 1)
            password = urllib.parse.unquote(password)
            server, port = server_port.rsplit(':', 1)
            
            node = {
                'name': name,
                'type': 'trojan',
                'server': server,
                'port': int(port),
                'password': password,
            }
            
            # 解析参数
            if params_part:
                params = urllib.parse.parse_qs(params_part)
                
                # SNI
                if params.get('sni'):
                    node['sni'] = params['sni'][0]
                
                # ALPN
                if params.get('alpn'):
                    node['alpn'] = params['alpn'][0].split(',')
                
                # 客户端指纹
                if params.get('fp'):
                    node['client-fingerprint'] = params['fp'][0]
                
                # fingerprint (证书指纹)
                if params.get('fingerprint'):
                    node['fingerprint'] = params['fingerprint'][0]
                
                # 跳过证书验证
                if params.get('allowInsecure', [''])[0] == '1' or params.get('skipCertVerify', [''])[0] == '1':
                    node['skip-cert-verify'] = True
                
                # UDP 支持
                if params.get('udp'):
                    node['udp'] = params['udp'][0] == 'true' or params['udp'][0] == '1'
                
                # 安全协议 (Reality)
                security = params.get('security', [''])[0]
                if security == 'reality':
                    node['reality-opts'] = {}
                    if params.get('pbk'):
                        node['reality-opts']['public-key'] = params['pbk'][0]
                    if params.get('sid'):
                        node['reality-opts']['short-id'] = params['sid'][0]
                
                # 传输协议
                if params.get('type'):
                    network = params['type'][0]
                    node['network'] = network
                    
                    if network == 'ws':
                        node['ws-opts'] = {}
                        if params.get('path'):
                            node['ws-opts']['path'] = params['path'][0]
                        if params.get('host'):
                            node['ws-opts']['headers'] = {'Host': params['host'][0]}
                    
                    elif network == 'grpc':
                        node['grpc-opts'] = {}
                        if params.get('serviceName'):
                            node['grpc-opts']['grpc-service-name'] = params['serviceName'][0]
            
            return node
        except Exception as e:
            print(f"解析 Trojan 链接失败: {e}")
            return None
    
    @staticmethod
    def parse_http(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 HTTP/HTTPS 代理链接
        格式: http://[username:password@]server:port#name
        或: https://[username:password@]server:port#name
        """
        try:
            is_https = url.startswith('https://')
            is_http = url.startswith('http://')
            
            if not (is_http or is_https):
                return None
            
            # 移除协议前缀
            if is_https:
                url = url[8:]
            else:
                url = url[7:]
            
            # 移除末尾的斜杠（如果有）
            url = url.rstrip('/')
            
            # 分离名称
            name = "HTTPS节点" if is_https else "HTTP节点"
            if '#' in url:
                url, name = url.split('#', 1)
                name = urllib.parse.unquote(name)
            
            # 解析用户名密码
            username = None
            password = None
            
            if '@' in url:
                auth_part, server_port = url.rsplit('@', 1)
                if ':' in auth_part:
                    username, password = auth_part.split(':', 1)
                    username = urllib.parse.unquote(username)
                    password = urllib.parse.unquote(password)
            else:
                server_port = url
            
            # 解析服务器和端口
            if ':' in server_port:
                server, port = server_port.rsplit(':', 1)
            else:
                server = server_port
                port = '443' if is_https else '80'
            
            # 移除端口号中可能残留的斜杠或其他字符
            port = port.strip().rstrip('/')
            
            node = {
                'name': name,
                'type': 'http',
                'server': server.strip(),
                'port': int(port),
            }
            
            if username:
                node['username'] = username
            if password:
                node['password'] = password
            
            # HTTPS 代理添加 TLS 标记
            if is_https:
                node['tls'] = True
            
            return node
        except Exception as e:
            print(f"解析 HTTP/HTTPS 链接失败: {e}")
            return None
    
    @staticmethod
    def parse_socks(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 SOCKS 代理链接
        格式: socks5://[username:password@]server:port#name
        或: socks4://[username:password@]server:port#name
        """
        try:
            is_socks5 = url.startswith('socks5://')
            is_socks4 = url.startswith('socks4://')
            
            if not (is_socks5 or is_socks4):
                return None
            
            # 移除协议前缀
            if is_socks5:
                url = url[9:]
                socks_type = 'socks5'
            else:
                url = url[9:]
                socks_type = 'socks4'
            
            # 移除末尾的斜杠（如果有）
            url = url.rstrip('/')
            
            # 分离名称
            name = f"{socks_type.upper()}节点"
            if '#' in url:
                url, name = url.split('#', 1)
                name = urllib.parse.unquote(name)
            
            # 解析用户名密码
            username = None
            password = None
            
            if '@' in url:
                auth_part, server_port = url.rsplit('@', 1)
                if ':' in auth_part:
                    username, password = auth_part.split(':', 1)
                    username = urllib.parse.unquote(username)
                    password = urllib.parse.unquote(password)
            else:
                server_port = url
            
            # 解析服务器和端口
            if ':' in server_port:
                server, port = server_port.rsplit(':', 1)
            else:
                server = server_port
                port = '1080'
            
            # 移除端口号中可能残留的斜杠或其他字符
            port = port.strip().rstrip('/')
            
            node = {
                'name': name,
                'type': socks_type,
                'server': server.strip(),
                'port': int(port),
            }
            
            if username:
                node['username'] = username
            if password:
                node['password'] = password
            
            return node
        except Exception as e:
            print(f"解析 SOCKS 链接失败: {e}")
            return None
    
    @staticmethod
    def parse_proxy(url: str) -> Optional[Dict[str, Any]]:
        """解析代理链接，自动识别协议类型"""
        url = url.strip()
        
        if url.startswith('ss://'):
            return ProxyParser.parse_ss(url)
        elif url.startswith('ssr://'):
            return ProxyParser.parse_ssr(url)
        elif url.startswith('vmess://'):
            return ProxyParser.parse_vmess(url)
        elif url.startswith('vless://'):
            return ProxyParser.parse_vless(url)
        elif url.startswith('hysteria2://') or url.startswith('hy2://'):
            return ProxyParser.parse_hysteria2(url)
        elif url.startswith('trojan://'):
            return ProxyParser.parse_trojan(url)
        elif url.startswith('http://') or url.startswith('https://'):
            return ProxyParser.parse_http(url)
        elif url.startswith('socks4://') or url.startswith('socks5://'):
            return ProxyParser.parse_socks(url)
        else:
            return None
    
    @staticmethod
    def parse_subscription(content: str) -> List[Dict[str, Any]]:
        """解析订阅内容，返回节点列表"""
        proxies = []
        
        # 尝试 base64 解码
        try:
            decoded = base64.b64decode(content + '=' * (4 - len(content) % 4)).decode('utf-8')
            lines = decoded.strip().split('\n')
        except:
            # 如果不是 base64，直接按行分割
            lines = content.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            proxy = ProxyParser.parse_proxy(line)
            if proxy:
                proxies.append(proxy)
        
        return proxies

