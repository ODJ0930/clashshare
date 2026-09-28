"""
协议解析器模块
支持 SS, SSR, VMess, VLESS, Hysteria2, AnyTLS 等协议的解析
"""

import base64
import ipaddress
import json
import re
import urllib.parse
from typing import Dict, List, Optional, Any


class ProxyParser:
    """代理协议解析器基类"""

    @staticmethod
    def _get_first_param(params: Dict[str, List[str]], *names: str, default: Any = None) -> Any:
        for name in names:
            values = params.get(name)
            if values:
                return values[0]
        return default

    @staticmethod
    def _parse_bool(value: Any) -> Optional[bool]:
        if value is None:
            return None

        normalized = str(value).strip().lower()
        if normalized in {'1', 'true', 'yes', 'y', 'on'}:
            return True
        if normalized in {'0', 'false', 'no', 'n', 'off'}:
            return False
        return None

    @staticmethod
    def _parse_duration_seconds(value: Any) -> Optional[int]:
        if value is None:
            return None

        text = str(value).strip().lower()
        if not text:
            return None

        match = re.fullmatch(r'(\d+)(ms|s|m|h)?', text)
        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2) or 's'

        if unit == 'ms':
            return max(1, amount // 1000)
        if unit == 's':
            return amount
        if unit == 'm':
            return amount * 60
        if unit == 'h':
            return amount * 3600
        return None

    @staticmethod
    def _is_ip_literal(value: str) -> bool:
        try:
            ipaddress.ip_address(value.strip('[]'))
            return True
        except ValueError:
            return False

    @staticmethod
    def _b64_encode(value: str, urlsafe: bool = False) -> str:
        data = str(value).encode('utf-8')
        encoder = base64.urlsafe_b64encode if urlsafe else base64.b64encode
        return encoder(data).decode('utf-8').rstrip('=')

    @staticmethod
    def _format_host(host: Any) -> str:
        host_text = str(host or '').strip()
        if ':' in host_text and not host_text.startswith('[') and not host_text.endswith(']'):
            return f'[{host_text}]'
        return host_text

    @staticmethod
    def _append_param(params: List[tuple], key: str, value: Any):
        if value is None or value == '':
            return
        params.append((key, str(value)))

    @staticmethod
    def _append_bool_param(params: List[tuple], key: str, value: Any, true_value: str = '1'):
        parsed = ProxyParser._parse_bool(value)
        if parsed is True:
            params.append((key, true_value))

    @staticmethod
    def _build_query(params: List[tuple]) -> str:
        return urllib.parse.urlencode(params, doseq=False, safe=',:/')

    @staticmethod
    def _append_fragment(link: str, name: Any) -> str:
        if not name:
            return link
        return f'{link}#{urllib.parse.quote(str(name), safe="")}'

    @staticmethod
    def _require_fields(proxy: Dict[str, Any], *fields: str):
        missing = [field for field in fields if proxy.get(field) in (None, '')]
        if missing:
            raise ValueError(f"节点缺少导出分享链接所需字段: {', '.join(missing)}")

    @staticmethod
    def to_share_url(proxy: Dict[str, Any]) -> str:
        """将节点配置导出为可被常见客户端导入的分享链接。"""
        if not isinstance(proxy, dict):
            raise ValueError("节点配置无效")

        proxy_type = str(proxy.get('type', '')).lower()
        exporters = {
            'ss': ProxyParser._to_ss_url,
            'ssr': ProxyParser._to_ssr_url,
            'vmess': ProxyParser._to_vmess_url,
            'vless': ProxyParser._to_vless_url,
            'trojan': ProxyParser._to_trojan_url,
            'hysteria2': ProxyParser._to_hysteria2_url,
            'hy2': ProxyParser._to_hysteria2_url,
            'anytls': ProxyParser._to_anytls_url,
            'http': ProxyParser._to_http_url,
            'socks4': ProxyParser._to_socks_url,
            'socks5': ProxyParser._to_socks_url,
        }

        exporter = exporters.get(proxy_type)
        if not exporter:
            raise ValueError(f"{proxy_type or '未知'} 类型没有标准分享链接格式")

        return exporter(proxy)

    @staticmethod
    def _to_ss_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port', 'cipher', 'password')
        host = ProxyParser._format_host(proxy['server'])
        userinfo = ProxyParser._b64_encode(f"{proxy['cipher']}:{proxy['password']}", urlsafe=True)
        params = []

        ProxyParser._append_bool_param(params, 'udp', proxy.get('udp'), true_value='true')
        ProxyParser._append_bool_param(params, 'uot', proxy.get('udp-over-tcp'), true_value='true')

        plugin = proxy.get('plugin')
        plugin_opts = proxy.get('plugin-opts') if isinstance(proxy.get('plugin-opts'), dict) else {}
        if plugin:
            plugin_parts = [str(plugin)]
            plugin_key_map = {
                'mode': 'mode',
                'host': 'host',
                'path': 'path',
                'tls': 'tls',
                'mux': 'mux',
                'skip-cert-verify': 'skip-cert-verify',
                'password': 'password',
                'version': 'version',
                'version-hint': 'version-hint',
                'restls-script': 'restls-script',
            }
            for opt_key, plugin_key in plugin_key_map.items():
                if opt_key in plugin_opts and plugin_opts[opt_key] not in (None, ''):
                    plugin_parts.append(f"{plugin_key}={plugin_opts[opt_key]}")
            params.append(('plugin', ';'.join(plugin_parts)))

        link = f"ss://{userinfo}@{host}:{proxy['port']}"
        query = ProxyParser._build_query(params)
        if query:
            link = f'{link}?{query}'
        return ProxyParser._append_fragment(link, proxy.get('name'))

    @staticmethod
    def _to_ssr_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port', 'cipher', 'password', 'protocol', 'obfs')
        password_b64 = ProxyParser._b64_encode(proxy['password'], urlsafe=True)
        params = [
            ('remarks', ProxyParser._b64_encode(proxy.get('name', ''), urlsafe=True)),
        ]
        if proxy.get('obfs-param'):
            params.append(('obfsparam', ProxyParser._b64_encode(proxy['obfs-param'], urlsafe=True)))
        if proxy.get('protocol-param'):
            params.append(('protoparam', ProxyParser._b64_encode(proxy['protocol-param'], urlsafe=True)))

        main = (
            f"{proxy['server']}:{proxy['port']}:{proxy['protocol']}:"
            f"{proxy['cipher']}:{proxy['obfs']}:{password_b64}/?{ProxyParser._build_query(params)}"
        )
        return f"ssr://{ProxyParser._b64_encode(main, urlsafe=True)}"

    @staticmethod
    def _to_vmess_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port', 'uuid')
        network = proxy.get('network', 'tcp')
        config = {
            'v': '2',
            'ps': proxy.get('name', ''),
            'add': proxy.get('server', ''),
            'port': str(proxy.get('port', '')),
            'id': proxy.get('uuid', ''),
            'aid': str(proxy.get('alterId', 0)),
            'scy': proxy.get('cipher', 'auto'),
            'net': network,
            'type': 'none',
            'host': '',
            'path': '',
            'tls': 'tls' if proxy.get('tls') else '',
        }

        servername = proxy.get('servername') or proxy.get('sni')
        if servername:
            config['sni'] = servername

        if network == 'ws':
            ws_opts = proxy.get('ws-opts') if isinstance(proxy.get('ws-opts'), dict) else {}
            config['path'] = ws_opts.get('path', '/')
            headers = ws_opts.get('headers') if isinstance(ws_opts.get('headers'), dict) else {}
            config['host'] = headers.get('Host', '')
        elif network == 'grpc':
            grpc_opts = proxy.get('grpc-opts') if isinstance(proxy.get('grpc-opts'), dict) else {}
            config['path'] = grpc_opts.get('grpc-service-name', '')
        elif network == 'h2':
            h2_opts = proxy.get('h2-opts') if isinstance(proxy.get('h2-opts'), dict) else {}
            config['path'] = h2_opts.get('path', '/')
            h2_host = h2_opts.get('host') if isinstance(h2_opts.get('host'), list) else []
            config['host'] = h2_host[0] if h2_host else ''

        return f"vmess://{ProxyParser._b64_encode(json.dumps(config, ensure_ascii=False, separators=(',', ':')))}"

    @staticmethod
    def _to_vless_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port', 'uuid')
        host = ProxyParser._format_host(proxy['server'])
        params = [('encryption', proxy.get('encryption') or 'none')]

        network = proxy.get('network') or 'tcp'
        if network == 'http':
            params.append(('type', 'tcp'))
            params.append(('headerType', 'http'))
        else:
            params.append(('type', network))

        ProxyParser._append_param(params, 'flow', proxy.get('flow'))

        reality_opts = proxy.get('reality-opts') if isinstance(proxy.get('reality-opts'), dict) else {}
        if reality_opts:
            params.append(('security', 'reality'))
        elif proxy.get('tls'):
            params.append(('security', 'tls'))

        servername = proxy.get('servername') or proxy.get('sni')
        ProxyParser._append_param(params, 'sni', servername)
        ProxyParser._append_bool_param(params, 'allowInsecure', proxy.get('skip-cert-verify'))
        ProxyParser._append_param(params, 'fp', proxy.get('client-fingerprint'))
        ProxyParser._append_param(params, 'pbk', reality_opts.get('public-key'))
        ProxyParser._append_param(params, 'sid', reality_opts.get('short-id'))

        if network == 'ws':
            ws_opts = proxy.get('ws-opts') if isinstance(proxy.get('ws-opts'), dict) else {}
            ProxyParser._append_param(params, 'path', ws_opts.get('path'))
            headers = ws_opts.get('headers') if isinstance(ws_opts.get('headers'), dict) else {}
            ProxyParser._append_param(params, 'host', headers.get('Host'))
        elif network == 'grpc':
            grpc_opts = proxy.get('grpc-opts') if isinstance(proxy.get('grpc-opts'), dict) else {}
            ProxyParser._append_param(params, 'serviceName', grpc_opts.get('grpc-service-name'))
        elif network in {'h2', 'http'}:
            opts_key = 'h2-opts' if network == 'h2' else 'http-opts'
            opts = proxy.get(opts_key) if isinstance(proxy.get(opts_key), dict) else {}
            path_value = opts.get('path')
            if isinstance(path_value, list):
                path_value = path_value[0] if path_value else None
            ProxyParser._append_param(params, 'path', path_value)

        query = ProxyParser._build_query(params)
        link = f"vless://{urllib.parse.quote(str(proxy['uuid']), safe='')}@{host}:{proxy['port']}?{query}"
        return ProxyParser._append_fragment(link, proxy.get('name'))

    @staticmethod
    def _to_trojan_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port', 'password')
        host = ProxyParser._format_host(proxy['server'])
        params = []

        reality_opts = proxy.get('reality-opts') if isinstance(proxy.get('reality-opts'), dict) else {}
        if reality_opts:
            params.append(('security', 'reality'))

        ProxyParser._append_param(params, 'sni', proxy.get('sni') or proxy.get('servername'))
        if isinstance(proxy.get('alpn'), list) and proxy['alpn']:
            params.append(('alpn', ','.join(proxy['alpn'])))
        ProxyParser._append_param(params, 'fp', proxy.get('client-fingerprint'))
        ProxyParser._append_param(params, 'fingerprint', proxy.get('fingerprint'))
        ProxyParser._append_bool_param(params, 'allowInsecure', proxy.get('skip-cert-verify'))
        ProxyParser._append_bool_param(params, 'udp', proxy.get('udp'))
        ProxyParser._append_param(params, 'pbk', reality_opts.get('public-key'))
        ProxyParser._append_param(params, 'sid', reality_opts.get('short-id'))

        network = proxy.get('network')
        if network:
            params.append(('type', network))
            if network == 'ws':
                ws_opts = proxy.get('ws-opts') if isinstance(proxy.get('ws-opts'), dict) else {}
                ProxyParser._append_param(params, 'path', ws_opts.get('path'))
                headers = ws_opts.get('headers') if isinstance(ws_opts.get('headers'), dict) else {}
                ProxyParser._append_param(params, 'host', headers.get('Host'))
            elif network == 'grpc':
                grpc_opts = proxy.get('grpc-opts') if isinstance(proxy.get('grpc-opts'), dict) else {}
                ProxyParser._append_param(params, 'serviceName', grpc_opts.get('grpc-service-name'))

        link = f"trojan://{urllib.parse.quote(str(proxy['password']), safe='')}@{host}:{proxy['port']}"
        query = ProxyParser._build_query(params)
        if query:
            link = f'{link}?{query}'
        return ProxyParser._append_fragment(link, proxy.get('name'))

    @staticmethod
    def _to_hysteria2_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port', 'password')
        host = ProxyParser._format_host(proxy['server'])
        params = []

        ProxyParser._append_param(params, 'sni', proxy.get('sni'))
        ProxyParser._append_bool_param(params, 'insecure', proxy.get('skip-cert-verify'))
        ProxyParser._append_param(params, 'obfs', proxy.get('obfs'))
        ProxyParser._append_param(params, 'obfs-password', proxy.get('obfs-password'))
        ProxyParser._append_param(params, 'pinSHA256', proxy.get('pinSHA256') or proxy.get('fingerprint'))
        if isinstance(proxy.get('alpn'), list) and proxy['alpn']:
            params.append(('alpn', ','.join(proxy['alpn'])))
        ProxyParser._append_param(params, 'upmbps', proxy.get('up'))
        ProxyParser._append_param(params, 'downmbps', proxy.get('down'))

        link = f"hysteria2://{urllib.parse.quote(str(proxy['password']), safe='')}@{host}:{proxy['port']}/"
        query = ProxyParser._build_query(params)
        if query:
            link = f'{link}?{query}'
        return ProxyParser._append_fragment(link, proxy.get('name'))

    @staticmethod
    def _to_anytls_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port', 'password')
        host = ProxyParser._format_host(proxy['server'])
        params = []

        ProxyParser._append_param(params, 'sni', proxy.get('sni'))
        ProxyParser._append_bool_param(params, 'insecure', proxy.get('skip-cert-verify'))
        ProxyParser._append_param(params, 'fp', proxy.get('client-fingerprint'))
        if isinstance(proxy.get('alpn'), list) and proxy['alpn']:
            params.append(('alpn', ','.join(proxy['alpn'])))
        ProxyParser._append_param(params, 'idle-session-check-interval', proxy.get('idle-session-check-interval'))
        ProxyParser._append_param(params, 'idle-session-timeout', proxy.get('idle-session-timeout'))
        ProxyParser._append_param(params, 'min-idle-session', proxy.get('min-idle-session'))
        ProxyParser._append_bool_param(params, 'udp', proxy.get('udp'))
        ProxyParser._append_bool_param(params, 'tfo', proxy.get('tfo'))

        link = f"anytls://{urllib.parse.quote(str(proxy['password']), safe='')}@{host}:{proxy['port']}/"
        query = ProxyParser._build_query(params)
        if query:
            link = f'{link}?{query}'
        return ProxyParser._append_fragment(link, proxy.get('name'))

    @staticmethod
    def _to_http_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port')
        scheme = 'https' if proxy.get('tls') else 'http'
        host = ProxyParser._format_host(proxy['server'])
        auth = ''
        if proxy.get('username') or proxy.get('password'):
            auth = urllib.parse.quote(str(proxy.get('username', '')), safe='')
            if proxy.get('password') is not None:
                auth += f":{urllib.parse.quote(str(proxy.get('password', '')), safe='')}"
            auth += '@'
        link = f"{scheme}://{auth}{host}:{proxy['port']}"
        return ProxyParser._append_fragment(link, proxy.get('name'))

    @staticmethod
    def _to_socks_url(proxy: Dict[str, Any]) -> str:
        ProxyParser._require_fields(proxy, 'name', 'server', 'port')
        scheme = str(proxy.get('type') or 'socks5').lower()
        host = ProxyParser._format_host(proxy['server'])
        auth = ''
        if proxy.get('username') or proxy.get('password'):
            auth = urllib.parse.quote(str(proxy.get('username', '')), safe='')
            if proxy.get('password') is not None:
                auth += f":{urllib.parse.quote(str(proxy.get('password', '')), safe='')}"
            auth += '@'
        link = f"{scheme}://{auth}{host}:{proxy['port']}"
        return ProxyParser._append_fragment(link, proxy.get('name'))
    
    @staticmethod
    def parse_ss(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 Shadowsocks 链接
        支持格式:
        - ss://base64(method:password)@server:port#name
        - ss://base64(method:password@server:port)#name
        - ss://base64(method:password)@server:port?params#name (SIP002)
        - ss://method:password@server:port?params#name (明文 userinfo)
        - 支持 Shadowsocks 2022 (2022-blake3-aes-256-gcm 等)
        """
        try:
            url = url.strip()
            if url.startswith(r'ss\://'):
                url = 'ss://' + url[6:]
            if not url.startswith('ss://'):
                return None
            
            url = url[5:]  # 移除 ss://
            
            # 分离备注名称
            name = "SS节点"
            if '#' in url:
                url, name = url.split('#', 1)
                name = urllib.parse.unquote(name) or 'SS节点'
            
            # 分离 URL 参数 (SIP002 格式)
            params = {}
            if '?' in url:
                url, params_str = url.split('?', 1)
                params = urllib.parse.parse_qs(params_str)
            
            # 明文 userinfo 只拆分第一个冒号，保留 SS 2022 的多段密钥。
            if '@' in url:
                userinfo, server_port = url.rsplit('@', 1)
                # 兼容复制时对分隔符 @ 添加的反斜杠。
                if userinfo.endswith('\\'):
                    userinfo = userinfo[:-1]
                userinfo = urllib.parse.unquote(userinfo)
                if ':' not in userinfo:
                    userinfo = base64.b64decode(
                        userinfo + '=' * (-len(userinfo) % 4),
                        altchars=b'-_', validate=True
                    ).decode('utf-8')
            else:
                # 旧格式: 全部base64编码
                encoded = urllib.parse.unquote(url)
                decoded = base64.b64decode(
                    encoded + '=' * (-len(encoded) % 4),
                    altchars=b'-_', validate=True
                ).decode('utf-8')
                if '@' not in decoded:
                    return None
                userinfo, server_port = decoded.rsplit('@', 1)

            method, password = userinfo.split(':', 1)
            endpoint = urllib.parse.urlsplit('ss://' + server_port)
            server, port = endpoint.hostname, endpoint.port
            if (not method.strip() or not password or not server or not port
                    or endpoint.path not in ('', '/')):
                return None
            
            node = {
                'name': name,
                'type': 'ss',
                'server': server,
                'port': port,
                'cipher': method.strip(),
                'password': password,
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
            print(f"解析 SS 链接失败: {e}")
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
                if encryption and encryption != 'none':
                    node['encryption'] = encryption
                
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
            server_port = server_port.rstrip('/')
            server, port = server_port.rsplit(':', 1)
            port = port.rstrip('/')
            
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
    def parse_anytls(url: str) -> Optional[Dict[str, Any]]:
        """
        解析 AnyTLS 链接
        最新官方 URI 格式: anytls://[auth@]hostname[:port]/?[key=value]&[key=value]...
        """
        try:
            if not url.startswith('anytls://'):
                return None

            parsed = urllib.parse.urlsplit(url)
            server = parsed.hostname
            if not server:
                return None

            try:
                port = parsed.port or 443
            except ValueError:
                return None

            params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
            userinfo = parsed.netloc.rsplit('@', 1)[0] if '@' in parsed.netloc else None
            password = userinfo or ProxyParser._get_first_param(params, 'password', 'auth')
            if not password:
                return None

            password = urllib.parse.unquote(password)
            name = urllib.parse.unquote(parsed.fragment) if parsed.fragment else 'AnyTLS节点'

            node = {
                'name': name,
                'type': 'anytls',
                'server': server,
                'port': int(port),
                'password': password,
            }

            sni = ProxyParser._get_first_param(params, 'sni', 'peer')
            if sni and not ProxyParser._is_ip_literal(sni):
                node['sni'] = sni

            insecure = ProxyParser._get_first_param(
                params,
                'insecure',
                'allowInsecure',
                'skipCertVerify',
                'skip-cert-verify'
            )
            skip_cert_verify = ProxyParser._parse_bool(insecure)
            if skip_cert_verify is not None:
                node['skip-cert-verify'] = skip_cert_verify

            udp = ProxyParser._get_first_param(params, 'udp')
            udp_enabled = ProxyParser._parse_bool(udp)
            if udp_enabled is not None:
                node['udp'] = udp_enabled

            tfo = ProxyParser._get_first_param(params, 'tfo')
            tfo_enabled = ProxyParser._parse_bool(tfo)
            if tfo_enabled is not None:
                node['tfo'] = tfo_enabled

            client_fingerprint = ProxyParser._get_first_param(
                params,
                'fp',
                'client-fingerprint',
                'clientFingerprint'
            )
            if client_fingerprint:
                node['client-fingerprint'] = client_fingerprint

            fingerprint = ProxyParser._get_first_param(params, 'fingerprint')
            if fingerprint:
                node['fingerprint'] = fingerprint

            alpn_values = []
            for value in params.get('alpn', []):
                alpn_values.extend([item.strip() for item in value.split(',') if item.strip()])
            if alpn_values:
                node['alpn'] = alpn_values

            idle_check = ProxyParser._get_first_param(
                params,
                'idle-session-check-interval',
                'idle_session_check_interval',
                'idleSessionCheckInterval'
            )
            idle_check_seconds = ProxyParser._parse_duration_seconds(idle_check)
            if idle_check_seconds is not None:
                node['idle-session-check-interval'] = idle_check_seconds

            idle_timeout = ProxyParser._get_first_param(
                params,
                'idle-session-timeout',
                'idle_session_timeout',
                'idleSessionTimeout'
            )
            idle_timeout_seconds = ProxyParser._parse_duration_seconds(idle_timeout)
            if idle_timeout_seconds is not None:
                node['idle-session-timeout'] = idle_timeout_seconds

            min_idle_session = ProxyParser._get_first_param(
                params,
                'min-idle-session',
                'min_idle_session',
                'minIdleSession'
            )
            if min_idle_session is not None and str(min_idle_session).isdigit():
                node['min-idle-session'] = int(min_idle_session)

            return node
        except Exception as e:
            print(f"解析 AnyTLS 链接失败: {e}")
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
        
        if url.startswith(('ss://', r'ss\://')):
            return ProxyParser.parse_ss(url)
        elif url.startswith('ssr://'):
            return ProxyParser.parse_ssr(url)
        elif url.startswith('vmess://'):
            return ProxyParser.parse_vmess(url)
        elif url.startswith('vless://'):
            return ProxyParser.parse_vless(url)
        elif url.startswith('hysteria2://') or url.startswith('hy2://'):
            return ProxyParser.parse_hysteria2(url)
        elif url.startswith('anytls://'):
            return ProxyParser.parse_anytls(url)
        elif url.startswith('trojan://'):
            return ProxyParser.parse_trojan(url)
        elif url.startswith('http://') or url.startswith('https://'):
            return ProxyParser.parse_http(url)
        elif url.startswith('socks4://') or url.startswith('socks5://'):
            return ProxyParser.parse_socks(url)
        else:
            return None
    
    @staticmethod
    def parse_yaml_proxies(content: str) -> List[Dict[str, Any]]:
        """
        解析 YAML 格式的 Clash 配置，提取 proxies 节点
        支持格式：
        - YAML 完整配置（包含 proxies 字段）
        - YAML 数组格式（直接是节点列表）
        """
        try:
            import yaml
            
            # 解析 YAML
            try:
                config = yaml.safe_load(content)
            except yaml.YAMLError:
                return []
            
            proxies = []
            
            # 情况1: 完整 Clash 配置，包含 proxies 字段
            if isinstance(config, dict) and 'proxies' in config:
                proxy_list = config['proxies']
                if isinstance(proxy_list, list):
                    proxies = proxy_list
            
            # 情况2: 直接是节点列表（数组）
            elif isinstance(config, list):
                proxies = config
            
            # 简单验证：只要有 name 和 type 就接受，完全保持原样
            validated_proxies = []
            for idx, proxy in enumerate(proxies):
                if not isinstance(proxy, dict):
                    print(f"节点 {idx+1} 不是字典类型，跳过")
                    continue
                
                # 只验证必须包含 name 和 type
                if 'name' not in proxy:
                    print(f"节点 {idx+1} 缺少 name 字段，跳过")
                    continue
                    
                if 'type' not in proxy:
                    print(f"节点 {idx+1} ({proxy.get('name')}) 缺少 type 字段，跳过")
                    continue
                
                # 原样保存，完全不做修改
                print(f"节点 {idx+1}: {proxy.get('name')} [{proxy.get('type')}]")
                validated_proxies.append(proxy)
            
            print(f"成功导入 {len(validated_proxies)}/{len(proxies)} 个节点")
            return validated_proxies
        
        except ImportError:
            print("警告: yaml 模块未安装，无法解析 YAML 格式")
            return []
        except Exception as e:
            print(f"解析 YAML 配置失败: {e}")
            return []
    
    @staticmethod
    def parse_subscription(content: str) -> List[Dict[str, Any]]:
        """解析订阅内容，返回节点列表"""
        proxies = []
        
        # 检测内容格式
        content_stripped = content.strip()
        
        # 1. 尝试解析为 YAML 格式（Clash 原生配置）
        # 检测 YAML 特征：包含 "proxies:" 或 以 "- {" 或 "- name:" 开头
        is_yaml = False
        if ('proxies:' in content_stripped or 
            content_stripped.startswith('- {') or 
            content_stripped.startswith('- name:') or
            'type: trojan' in content_stripped or
            'type: vmess' in content_stripped or
            'type: vless' in content_stripped or
            'type: anytls' in content_stripped or
            'type: ss' in content_stripped):
            is_yaml = True
        
        if is_yaml:
            print("检测到 YAML 格式订阅，正在解析...")
            proxies = ProxyParser.parse_yaml_proxies(content)
            if proxies:
                print(f"从 YAML 格式解析到 {len(proxies)} 个节点")
                return proxies
            else:
                print("YAML 解析失败，尝试其他格式...")
        
        # 2. 尝试 base64 解码（传统订阅格式）
        try:
            decoded = base64.b64decode(content + '=' * (4 - len(content) % 4)).decode('utf-8')
            lines = decoded.strip().split('\n')
            print("检测到 Base64 编码订阅")
        except:
            # 如果不是 base64，直接按行分割
            lines = content.strip().split('\n')
            print("检测到纯文本订阅")
        
        # 3. 逐行解析节点链接
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            proxy = ProxyParser.parse_proxy(line)
            if proxy:
                proxies.append(proxy)
        
        return proxies
