import base64
import json
import shutil
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import yaml

from app import app, db, _subscription_cache
from models import Node, Subscription, User, UserXuiClient, XuiConfig


def inbound(inbound_id=101, protocol='vless', network='tcp'):
    return {
        'id': inbound_id,
        'remark': f'node-{inbound_id}',
        'protocol': protocol,
        'port': 24000 + inbound_id,
        'enable': True,
        'total': 0,
        'up': 0,
        'down': 0,
        'expiryTime': 0,
        'reset': 0,
        'settings': {
            'clients': [],
            'decryption': 'none',
            'fallbacks': []
        },
        'streamSettings': {
            'network': network,
            'security': 'none'
        },
        'sniffing': {'enabled': True}
    }


def inbound_payload(remark='quick-node', port=31001, protocol='vless', network='tcp'):
    return {
        'enable': True,
        'remark': remark,
        'listen': '',
        'port': port,
        'protocol': protocol,
        'total': 0,
        'expiryTime': 0,
        'settings': {
            'clients': [],
            'decryption': 'none',
            'encryption': 'none',
            'fallbacks': []
        },
        'streamSettings': {
            'network': network,
            'security': 'none'
        },
        'sniffing': {
            'enabled': True,
            'destOverride': ['http', 'tls'],
            'metadataOnly': False,
            'routeOnly': False
        }
    }


class UserXuiClientsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.db_path = Path(app.instance_path) / 'clash_manager.db'
        cls.backup_path = cls.db_path.with_suffix('.db.test-backup')
        cls.db_existed = cls.db_path.exists()
        if cls.db_existed:
            shutil.copy2(cls.db_path, cls.backup_path)

    @classmethod
    def tearDownClass(cls):
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        if cls.db_existed:
            shutil.copy2(cls.backup_path, cls.db_path)
            cls.backup_path.unlink(missing_ok=True)
        else:
            cls.db_path.unlink(missing_ok=True)

    def setUp(self):
        with app.app_context():
            _subscription_cache.clear()
            db.session.remove()
            db.drop_all()
            db.create_all()
            self.backend = XuiConfig(
                name='test-backend',
                base_url='https://panel.example.test',
                public_host='node.example.test',
                auth_mode='token',
                api_token='token'
            )
            self.user = User(
                username='小王',
                subscription_token='user-token',
                enabled=True
            )
            db.session.add_all([self.backend, self.user])
            db.session.commit()
            self.backend_id = self.backend.id
            self.user_id = self.user.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()

    def test_load_user_xui_clients_can_skip_remote_inbounds_for_fast_modal_open(self):
        raw_inbound = inbound(101)
        raw_client = {
            'email': 'user-u1-in101',
            'inboundIds': [101],
            'enable': True
        }
        with app.app_context():
            db.session.add(UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email='user-u1-in101',
                raw_inbound=json.dumps(raw_inbound),
                raw_client=json.dumps(raw_client)
            ))
            db.session.commit()

        def fake_xui_request(*_args, **_kwargs):
            raise AssertionError('remote 3x-ui should not be called for cached modal open')

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.get(f'/api/users/{self.user_id}/xui-clients?sync=0&include_inbounds=0')

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(len(data['clients']), 1)
        self.assertEqual(data['inbounds'], [])
        self.assertFalse(data['include_inbounds'])

    def login(self, client):
        with client.session_transaction() as session:
            session['admin_id'] = 1

    def attach_subscription_nodes(self, configs):
        with app.app_context():
            user = User.query.get(self.user_id)
            subscription = Subscription(
                name='test-subscription',
                subscription_token='test-subscription-token'
            )
            db.session.add(subscription)
            for index, config in enumerate(configs, start=1):
                node = Node(
                    name=config['name'],
                    original_name=config['name'],
                    protocol=config['type'],
                    order=index
                )
                node.set_config(config)
                subscription.nodes.append(node)
            user.subscriptions.append(subscription)
            db.session.commit()

    def test_creates_one_remote_client_per_inbound_and_syncs_traffic(self):
        inbounds = [inbound(101), inbound(102)]
        created = []
        updated_inbounds = []

        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            self.assertEqual(config_id, self.backend_id)
            if path == '/panel/api/inbounds/options':
                return {'success': True, 'obj': inbounds}
            if path.startswith('/panel/api/inbounds/update/'):
                updated_inbounds.append((path, json_body))
                inbound_id = int(path.rsplit('/', 1)[-1])
                for index, item in enumerate(inbounds):
                    if int(item['id']) == inbound_id:
                        inbounds[index] = dict(json_body)
                        break
                return {'success': True, 'msg': 'ok'}
            if path == '/panel/api/clients/list':
                clients = []
                for index, payload in enumerate(created, start=1):
                    client = dict(payload['client'])
                    client['inboundIds'] = payload['inboundIds']
                    client['traffic'] = {'up': index, 'down': index * 10}
                    clients.append(client)
                return {'success': True, 'obj': clients}
            if path == '/panel/api/clients/onlines':
                return {'success': True, 'obj': []}
            if path == '/panel/api/clients/add':
                created.append(json_body)
                return {'success': True, 'msg': 'ok'}
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.post(f'/api/users/{self.user_id}/xui-clients', json={
                    'backend_id': self.backend_id,
                    'inbound_ids': [101, 102],
                    'total_gb': 1,
                    'expiry_time': 1893456000000,
                    'limit_ip': 2,
                    'comment': 'unit-test'
                })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0]['inboundIds'], [101])
        self.assertEqual(created[1]['inboundIds'], [102])
        self.assertTrue(created[0]['client']['email'].endswith(f'-u{self.user_id}-in101'))
        self.assertIn('id', created[0]['client'])
        self.assertNotIn('totalGB', created[0]['client'])
        self.assertNotIn('expiryTime', created[0]['client'])
        self.assertEqual(updated_inbounds[0][1]['total'], 1024 * 1024 * 1024)
        self.assertEqual(updated_inbounds[0][1]['expiryTime'], 1893456000000)

        with app.app_context():
            mappings = UserXuiClient.query.order_by(UserXuiClient.inbound_id).all()
            self.assertEqual(len(mappings), 2)
            self.assertEqual(mappings[0].traffic_used, 11)
            self.assertEqual(mappings[1].traffic_used, 22)
            self.assertEqual(mappings[0].traffic_limit, 1024 * 1024 * 1024)

    def test_delete_remote_success_removes_local_mapping(self):
        with app.app_context():
            other_user = User(username='小李', subscription_token='other-token', enabled=True)
            db.session.add(other_user)
            db.session.flush()
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                client_email='user-u1-in101'
            )
            other_mapping = UserXuiClient(
                user_id=other_user.id,
                backend_id=self.backend_id,
                inbound_id=101,
                client_email='user-u2-in101'
            )
            db.session.add_all([mapping, other_mapping])
            db.session.commit()
            mapping_id = mapping.id
            other_mapping_id = other_mapping.id

        calls = []

        def fake_xui_request(method, path, config_id=None, **_kwargs):
            calls.append((method, path, config_id))
            return {'success': True}

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.delete(f'/api/users/{self.user_id}/xui-clients/{mapping_id}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(calls[0][1], '/panel/api/inbounds/del/101')
        with app.app_context():
            self.assertIsNone(UserXuiClient.query.get(mapping_id))
            self.assertIsNone(UserXuiClient.query.get(other_mapping_id))

    def test_delete_remote_failure_keeps_local_mapping(self):
        with app.app_context():
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                client_email='user-u1-in101'
            )
            db.session.add(mapping)
            db.session.commit()
            mapping_id = mapping.id

        def fake_xui_request(*_args, **_kwargs):
            from app import XuiApiError
            raise XuiApiError('remote failed', 400)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.delete(f'/api/users/{self.user_id}/xui-clients/{mapping_id}')

        self.assertEqual(response.status_code, 400)
        with app.app_context():
            self.assertIsNotNone(UserXuiClient.query.get(mapping_id))

    def test_global_inbound_delete_removes_user_mapping_cache(self):
        with app.app_context():
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                client_email='user-u1-in101'
            )
            db.session.add(mapping)
            db.session.commit()
            mapping_id = mapping.id

        calls = []

        def fake_xui_request(method, path, config_id=None, **_kwargs):
            calls.append((method, path, config_id))
            return {'success': True, 'msg': 'deleted'}

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.delete(f'/api/xui/inbounds/101?backend_id={self.backend_id}')

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(calls[0][1], '/panel/api/inbounds/del/101')
        self.assertEqual(response.get_json()['deleted_mappings'], 1)
        with app.app_context():
            self.assertIsNone(UserXuiClient.query.get(mapping_id))

    def test_update_client_limit_uses_string_uuid_when_remote_get_returns_numeric_id(self):
        client_email = 'user-u1-in101'
        client_uuid = '00000000-0000-4000-8000-000000000123'
        raw_inbound = inbound(101)
        raw_inbound['settings']['clients'] = [{
            'email': client_email,
            'id': client_uuid
        }]
        with app.app_context():
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email=client_email,
                raw_inbound=json.dumps(raw_inbound)
            )
            db.session.add(mapping)
            db.session.commit()
            mapping_id = mapping.id

        updated_payloads = []
        updated_inbounds = []

        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            self.assertEqual(config_id, self.backend_id)
            if path == '/panel/api/clients/get/user-u1-in101':
                return {
                    'success': True,
                    'obj': {
                        'client': {
                            'id': 99,
                            'email': client_email,
                            'inboundIds': [101],
                            'traffic': {'up': 3, 'down': 4},
                            'enable': True
                        }
                    }
                }
            if path == '/panel/api/clients/update/user-u1-in101':
                updated_payloads.append(json_body)
                return {'success': True, 'msg': 'ok'}
            if path == '/panel/api/inbounds/update/101':
                updated_inbounds.append(json_body)
                raw_inbound.update(json_body)
                return {'success': True, 'msg': 'ok'}
            if path == '/panel/api/inbounds/options':
                return {'success': True, 'obj': [raw_inbound]}
            if path == '/panel/api/clients/list':
                client = dict(updated_payloads[-1])
                client['inboundIds'] = [101]
                client['traffic'] = {'up': 3, 'down': 4}
                return {'success': True, 'obj': [client]}
            if path == '/panel/api/clients/onlines':
                return {'success': True, 'obj': []}
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.put(f'/api/users/{self.user_id}/xui-clients/{mapping_id}', json={
                    'total_gb': 2,
                    'limit_ip': 1,
                    'enable': True
                })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(updated_payloads[0]['id'], client_uuid)
        self.assertNotIn('traffic', updated_payloads[0])
        self.assertNotIn('inboundIds', updated_payloads[0])
        self.assertNotIn('totalGB', updated_payloads[0])
        self.assertNotIn('expiryTime', updated_payloads[0])
        self.assertEqual(updated_inbounds[0]['total'], 2 * 1024 * 1024 * 1024)

    def test_update_client_limit_uses_remote_inbound_uuid_when_local_snapshot_is_stale(self):
        client_email = 'user-u1-in101'
        client_uuid = '00000000-0000-4000-8000-000000000456'
        local_inbound = inbound(101)
        remote_inbound = inbound(101)
        remote_inbound['settings']['clients'] = [{
            'email': client_email,
            'id': client_uuid
        }]
        with app.app_context():
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email=client_email,
                raw_inbound=json.dumps(local_inbound)
            )
            db.session.add(mapping)
            db.session.commit()
            mapping_id = mapping.id

        updated_payloads = []
        updated_inbounds = []

        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            self.assertEqual(config_id, self.backend_id)
            if path == '/panel/api/clients/get/user-u1-in101':
                return {
                    'success': True,
                    'obj': {
                        'client': {
                            'id': 88,
                            'email': client_email,
                            'inboundIds': [101],
                            'traffic': {'up': 0, 'down': 0},
                            'enable': True
                        }
                    }
                }
            if path == '/panel/api/inbounds/options':
                return {'success': True, 'obj': [remote_inbound]}
            if path == '/panel/api/clients/update/user-u1-in101':
                updated_payloads.append(json_body)
                return {'success': True, 'msg': 'ok'}
            if path == '/panel/api/inbounds/update/101':
                updated_inbounds.append(json_body)
                remote_inbound.update(json_body)
                return {'success': True, 'msg': 'ok'}
            if path == '/panel/api/clients/list':
                client = dict(updated_payloads[-1])
                client['inboundIds'] = [101]
                client['traffic'] = {'up': 0, 'down': 0}
                return {'success': True, 'obj': [client]}
            if path == '/panel/api/clients/onlines':
                return {'success': True, 'obj': []}
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.put(f'/api/users/{self.user_id}/xui-clients/{mapping_id}', json={
                    'total_gb': 5,
                    'limit_ip': 1,
                    'enable': True
                })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(updated_payloads[0]['id'], client_uuid)
        self.assertNotIn('totalGB', updated_payloads[0])
        self.assertEqual(updated_inbounds[0]['total'], 5 * 1024 * 1024 * 1024)

    def test_update_inbound_limit_fetches_full_inbound_when_options_are_sparse(self):
        client_email = 'user-u1-in101'
        client_uuid = '00000000-0000-4000-8000-000000000789'
        sparse_inbound = inbound(101)
        sparse_inbound.pop('enable', None)
        full_inbound = inbound(101)
        full_inbound['settings']['clients'] = [{
            'email': client_email,
            'id': client_uuid
        }]
        with app.app_context():
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email=client_email,
                raw_inbound=json.dumps(sparse_inbound)
            )
            db.session.add(mapping)
            db.session.commit()
            mapping_id = mapping.id

        updated_inbounds = []

        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            self.assertEqual(config_id, self.backend_id)
            if path == '/panel/api/clients/get/user-u1-in101':
                return {'success': True, 'obj': {'client': {'id': 77, 'email': client_email, 'enable': True}}}
            if path == '/panel/api/inbounds/options':
                return {'success': True, 'obj': [sparse_inbound]}
            if path == '/panel/api/inbounds/get/101':
                return {'success': True, 'obj': full_inbound}
            if path == '/panel/api/clients/update/user-u1-in101':
                self.assertNotIn('totalGB', json_body)
                return {'success': True, 'msg': 'ok'}
            if path == '/panel/api/inbounds/update/101':
                updated_inbounds.append(json_body)
                full_inbound.update(json_body)
                return {'success': True, 'msg': 'ok'}
            if path == '/panel/api/clients/list':
                client = {'id': client_uuid, 'email': client_email, 'inboundIds': [101], 'traffic': {'up': 0, 'down': 0}}
                return {'success': True, 'obj': [client]}
            if path == '/panel/api/clients/onlines':
                return {'success': True, 'obj': []}
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.put(f'/api/users/{self.user_id}/xui-clients/{mapping_id}', json={
                    'total_gb': 3,
                    'limit_ip': 0,
                    'enable': True
                })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(updated_inbounds[0]['enable'], True)
        self.assertEqual(updated_inbounds[0]['total'], 3 * 1024 * 1024 * 1024)
        with app.app_context():
            self.assertEqual(UserXuiClient.query.get(mapping_id).traffic_limit, 3 * 1024 * 1024 * 1024)

    def test_user_subscription_includes_xui_proxy_and_userinfo(self):
        raw_inbound = inbound(101)
        raw_inbound['settings']['clients'] = [{
            'email': 'user-u1-in101',
            'id': '00000000-0000-4000-8000-000000000001'
        }]
        raw_inbound['up'] = 5
        raw_inbound['down'] = 7
        raw_inbound['total'] = 1024
        raw_inbound['expiryTime'] = 1893456000000
        raw_client = raw_inbound['settings']['clients'][0] | {
            'inboundIds': [101],
            'traffic': {'up': 5, 'down': 7},
            'enable': True
        }
        with app.app_context():
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email='user-u1-in101',
                display_name='小王-node-101',
                enabled=True,
                traffic_up=5,
                traffic_down=7,
                traffic_used=12,
                raw_inbound=json.dumps(raw_inbound),
                raw_client=json.dumps(raw_client),
                last_sync_at=datetime.utcnow()
            )
            db.session.add(mapping)
            db.session.commit()

        with app.test_client() as client:
            response = client.get('/sub/user/user-token')

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = yaml.safe_load(response.data.decode('utf-8'))
        proxies = body.get('proxies') or []
        self.assertEqual(proxies[0]['server'], 'node.example.test')
        self.assertEqual(proxies[0]['uuid'], '00000000-0000-4000-8000-000000000001')
        self.assertIn('upload=5; download=7; total=0', response.headers['Subscription-Userinfo'])

    def test_shadowrocket_subscription_exports_supported_protocols_and_keeps_clash_yaml(self):
        self.attach_subscription_nodes([
            {
                'name': '01-ss', 'type': 'ss', 'server': 'ss.example.test', 'port': 1001,
                'cipher': 'aes-256-gcm', 'password': 'ss-password'
            },
            {
                'name': '02-ssr', 'type': 'ssr', 'server': 'ssr.example.test', 'port': 1002,
                'cipher': 'aes-256-cfb', 'password': 'ssr-password',
                'protocol': 'origin', 'obfs': 'plain'
            },
            {
                'name': '03-vmess', 'type': 'vmess', 'server': 'vmess.example.test', 'port': 1003,
                'uuid': '00000000-0000-4000-8000-000000000003', 'alterId': 0, 'cipher': 'auto'
            },
            {
                'name': '04-vless', 'type': 'vless', 'server': 'vless.example.test', 'port': 1004,
                'uuid': '00000000-0000-4000-8000-000000000004'
            },
            {
                'name': '05-trojan', 'type': 'trojan', 'server': 'trojan.example.test', 'port': 1005,
                'password': 'trojan-password'
            },
            {
                'name': '06-hysteria2', 'type': 'hysteria2', 'server': 'hy2.example.test', 'port': 1006,
                'password': 'hy2-password'
            },
        ])

        path = '/sub/user/user-token/shadowrocket'
        with app.test_client() as client:
            response = client.get(path)
            not_modified = client.get(path, headers={'If-None-Match': response.headers.get('ETag')})
            clash_response = client.get('/sub/user/user-token')

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        decoded = base64.b64decode(response.data).decode('utf-8')
        share_urls = decoded.splitlines()
        self.assertEqual(
            [url.split(':', 1)[0] for url in share_urls],
            ['ss', 'ssr', 'vmess', 'vless', 'trojan', 'hysteria2']
        )
        self.assertFalse(decoded.endswith('\n'))
        self.assertEqual(response.headers['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn('shadowrocket_', response.headers['Content-Disposition'])
        self.assertEqual(response.headers['X-Subscription-Format'], 'shadowrocket')
        self.assertEqual(response.headers['X-Shadowrocket-Node-Count'], '6')
        self.assertEqual(response.headers['X-Shadowrocket-Skipped-Count'], '0')
        self.assertIn('upload=0; download=0; total=0', response.headers['Subscription-Userinfo'])
        self.assertEqual(not_modified.status_code, 304)
        self.assertEqual(not_modified.headers['X-Subscription-Cache'], 'NOT_MODIFIED')

        self.assertEqual(clash_response.status_code, 200, clash_response.get_data(as_text=True))
        clash_body = yaml.safe_load(clash_response.data.decode('utf-8'))
        self.assertEqual(len(clash_body.get('proxies') or []), 6)
        self.assertTrue(clash_response.headers['Content-Type'].startswith('text/yaml'))

    def test_shadowrocket_subscription_supports_custom_slug_and_user_access_rules(self):
        self.attach_subscription_nodes([{
            'name': 'custom-vless',
            'type': 'vless',
            'server': 'custom.example.test',
            'port': 443,
            'uuid': '00000000-0000-4000-8000-000000000010'
        }])
        with app.app_context():
            user = User.query.get(self.user_id)
            user.custom_slug = 'custom-user'
            db.session.commit()

        with app.test_client() as client:
            custom_response = client.get('/sub/user/custom-user/shadowrocket')
            invalid_response = client.get('/sub/user/missing-token/shadowrocket')

        self.assertEqual(custom_response.status_code, 200)
        self.assertEqual(invalid_response.status_code, 404)

        with app.app_context():
            user = User.query.get(self.user_id)
            user.enabled = False
            db.session.commit()
        with app.test_client() as client:
            disabled_response = client.get('/sub/user/custom-user/shadowrocket')
        self.assertEqual(disabled_response.status_code, 404)

        with app.app_context():
            user = User.query.get(self.user_id)
            user.enabled = True
            user.traffic_limit = 1
            user.traffic_used = 2
            db.session.commit()
        with app.test_client() as client:
            limited_response = client.get('/sub/user/custom-user/shadowrocket')
        self.assertEqual(limited_response.status_code, 403)

    def test_shadowrocket_subscription_skips_incompatible_nodes(self):
        self.attach_subscription_nodes([
            {
                'name': '01-relay',
                'type': 'relay',
                'proxies': ['front-node', 'back-node']
            },
            {
                'name': '02-vless',
                'type': 'vless',
                'server': 'vless.example.test',
                'port': 443,
                'uuid': '00000000-0000-4000-8000-000000000020'
            },
        ])

        with app.test_client() as client:
            response = client.get('/sub/user/user-token/shadowrocket')

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        share_urls = base64.b64decode(response.data).decode('utf-8').splitlines()
        self.assertEqual(len(share_urls), 1)
        self.assertTrue(share_urls[0].startswith('vless://'))
        self.assertEqual(response.headers['X-Shadowrocket-Node-Count'], '1')
        self.assertEqual(response.headers['X-Shadowrocket-Skipped-Count'], '1')

    def test_shadowrocket_subscription_reports_empty_and_all_incompatible(self):
        with app.test_client() as client:
            empty_response = client.get('/sub/user/user-token/shadowrocket')
        self.assertEqual(empty_response.status_code, 404)
        self.assertEqual(empty_response.get_data(as_text=True), 'No nodes available')

        self.attach_subscription_nodes([{
            'name': 'relay-only',
            'type': 'relay',
            'proxies': ['front-node', 'back-node']
        }])
        with app.test_client() as client:
            incompatible_response = client.get('/sub/user/user-token/shadowrocket')
        self.assertEqual(incompatible_response.status_code, 404)
        self.assertEqual(
            incompatible_response.get_data(as_text=True),
            'No Shadowrocket-compatible nodes available'
        )

    def test_user_api_keeps_user_limit_separate_from_xui_inbound_limit(self):
        raw_inbound = inbound(101)
        raw_inbound['total'] = 1000 * 1024 * 1024 * 1024
        raw_inbound['settings']['clients'] = [{
            'email': 'user-u1-in101',
            'id': '00000000-0000-4000-8000-000000000001'
        }]
        with app.app_context():
            user = User.query.get(self.user_id)
            user.traffic_limit = 2 * 1024 * 1024 * 1024
            db.session.add(UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email='user-u1-in101',
                enabled=True,
                traffic_limit=raw_inbound['total'],
                raw_inbound=json.dumps(raw_inbound),
                raw_client=json.dumps(raw_inbound['settings']['clients'][0]),
                last_sync_at=datetime.utcnow()
            ))
            db.session.commit()

        with app.test_client() as client:
            self.login(client)
            response = client.get('/api/users')

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data[0]['traffic_limit'], 2 * 1024 * 1024 * 1024)
        self.assertEqual(data[0]['traffic_limit_gb'], 2)

    def test_updates_subscription_endpoint_override_without_remote_call(self):
        raw_inbound = inbound(101)
        raw_inbound['settings']['clients'] = [{
            'email': 'user-u1-in101',
            'id': '00000000-0000-4000-8000-000000000001'
        }]
        with app.app_context():
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email='user-u1-in101',
                enabled=True,
                raw_inbound=json.dumps(raw_inbound),
                raw_client=json.dumps(raw_inbound['settings']['clients'][0])
            )
            db.session.add(mapping)
            db.session.commit()
            mapping_id = mapping.id

        def fake_xui_request(*_args, **_kwargs):
            raise AssertionError('subscription endpoint override must be local-only')

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.put(
                    f'/api/users/{self.user_id}/xui-clients/{mapping_id}/subscription-endpoint',
                    json={
                        'subscription_host': 'forward.example.test',
                        'subscription_port': 443
                    }
                )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        data = response.get_json()
        self.assertEqual(data['client']['subscription_host'], 'forward.example.test')
        self.assertEqual(data['client']['subscription_port'], 443)
        self.assertEqual(data['client']['subscription_effective_host'], 'forward.example.test')
        self.assertEqual(data['client']['subscription_effective_port'], 443)
        with app.app_context():
            mapping = UserXuiClient.query.get(mapping_id)
            self.assertEqual(mapping.subscription_host, 'forward.example.test')
            self.assertEqual(mapping.subscription_port, 443)

    def test_user_subscription_uses_endpoint_override_but_keeps_inbound_stats(self):
        raw_inbound = inbound(101)
        raw_inbound['port'] = 24101
        raw_inbound['settings']['clients'] = [{
            'email': 'user-u1-in101',
            'id': '00000000-0000-4000-8000-000000000001'
        }]
        raw_inbound['up'] = 11
        raw_inbound['down'] = 13
        raw_inbound['total'] = 2048
        raw_client = raw_inbound['settings']['clients'][0] | {
            'inboundIds': [101],
            'traffic': {'up': 11, 'down': 13},
            'enable': True
        }
        with app.app_context():
            db.session.add(UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email='user-u1-in101',
                display_name='forwarded-node',
                enabled=True,
                subscription_host='forward.example.test',
                subscription_port=443,
                raw_inbound=json.dumps(raw_inbound),
                raw_client=json.dumps(raw_client),
                last_sync_at=datetime.utcnow()
            ))
            db.session.commit()

        with app.test_client() as client:
            response = client.get('/sub/user/user-token')
            shadowrocket_response = client.get('/sub/user/user-token/shadowrocket')

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = yaml.safe_load(response.data.decode('utf-8'))
        proxies = body.get('proxies') or []
        self.assertEqual(proxies[0]['server'], 'forward.example.test')
        self.assertEqual(proxies[0]['port'], 443)
        self.assertIn('upload=11; download=13; total=0', response.headers['Subscription-Userinfo'])
        self.assertEqual(
            shadowrocket_response.status_code,
            200,
            shadowrocket_response.get_data(as_text=True)
        )
        shadowrocket_urls = base64.b64decode(shadowrocket_response.data).decode('utf-8').splitlines()
        self.assertEqual(len(shadowrocket_urls), 1)
        self.assertTrue(shadowrocket_urls[0].startswith('vless://'))
        self.assertIn('@forward.example.test:443?', shadowrocket_urls[0])
        self.assertIn(
            'upload=11; download=13; total=0',
            shadowrocket_response.headers['Subscription-Userinfo']
        )

    def test_user_subscription_enforces_user_limit_with_xui_clients(self):
        raw_inbound = inbound(101)
        raw_inbound['settings']['clients'] = [{
            'email': 'user-u1-in101',
            'id': '00000000-0000-4000-8000-000000000001'
        }]
        with app.app_context():
            user = User.query.get(self.user_id)
            user.traffic_limit = 10
            db.session.add(UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=101,
                inbound_name='node-101',
                inbound_protocol='vless',
                client_email='user-u1-in101',
                enabled=True,
                traffic_used=11,
                raw_inbound=json.dumps(raw_inbound),
                raw_client=json.dumps(raw_inbound['settings']['clients'][0]),
                last_sync_at=datetime.utcnow()
            ))
            db.session.commit()

        with app.test_client() as client:
            response = client.get('/sub/user/user-token')

        self.assertEqual(response.status_code, 403)

    def test_user_subscription_excludes_inactive_inbound_states(self):
        def add_mapping(inbound_id, email, uuid, **inbound_overrides):
            raw_inbound = inbound(inbound_id)
            raw_inbound['settings']['clients'] = [{'email': email, 'id': uuid}]
            raw_inbound.update(inbound_overrides)
            mapping = UserXuiClient(
                user_id=self.user_id,
                backend_id=self.backend_id,
                inbound_id=inbound_id,
                inbound_name=f'node-{inbound_id}',
                inbound_protocol='vless',
                client_email=email,
                display_name=f'node-{inbound_id}',
                enabled=True,
                raw_inbound=json.dumps(raw_inbound),
                raw_client=json.dumps(raw_inbound['settings']['clients'][0]),
                last_sync_at=datetime.utcnow()
            )
            db.session.add(mapping)

        with app.app_context():
            add_mapping(201, 'user-u1-in201', '00000000-0000-4000-8000-000000000201',
                        up=1, down=2, total=100)
            add_mapping(202, 'user-u1-in202', '00000000-0000-4000-8000-000000000202',
                        enable=False, total=100)
            add_mapping(203, 'user-u1-in203', '00000000-0000-4000-8000-000000000203',
                        expiryTime=1, total=100)
            add_mapping(204, 'user-u1-in204', '00000000-0000-4000-8000-000000000204',
                        up=70, down=30, total=100)
            db.session.commit()

        with app.test_client() as client:
            response = client.get('/sub/user/user-token')

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = yaml.safe_load(response.data.decode('utf-8'))
        proxies = body.get('proxies') or []
        self.assertEqual([proxy['name'] for proxy in proxies], ['node-201'])
        self.assertIn('upload=1; download=2; total=0', response.headers['Subscription-Userinfo'])

    def test_rejects_unsupported_inbound_before_remote_create(self):
        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            if path == '/panel/api/inbounds/options':
                return {'success': True, 'obj': [inbound(101, protocol='wireguard')]}
            if path == '/panel/api/clients/list':
                return {'success': True, 'obj': []}
            if path == '/panel/api/clients/onlines':
                return {'success': True, 'obj': []}
            if path == '/panel/api/clients/add':
                raise AssertionError('remote add should not be called')
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.post(f'/api/users/{self.user_id}/xui-clients', json={
                    'backend_id': self.backend_id,
                    'inbound_ids': [101]
                })

        self.assertEqual(response.status_code, 400)
        with app.app_context():
            self.assertEqual(UserXuiClient.query.count(), 0)

    def test_create_inbound_for_user_uses_returned_inbound_id(self):
        remote_inbounds = []
        created_clients = []
        quick_payload = inbound_payload(remark='quick-node', port=31001)
        quick_payload['total'] = 2 * 1024 * 1024 * 1024
        quick_payload['expiryTime'] = 1893456000000
        quick_payload['reset'] = 3

        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            self.assertEqual(config_id, self.backend_id)
            if path == '/panel/api/inbounds/list':
                return {'success': True, 'obj': remote_inbounds}
            if path == '/panel/api/inbounds/options':
                return {'success': True, 'obj': remote_inbounds}
            if path == '/panel/api/clients/list':
                clients = []
                for payload in created_clients:
                    client = dict(payload['client'])
                    client['inboundIds'] = payload['inboundIds']
                    client['traffic'] = {'up': 2, 'down': 3}
                    clients.append(client)
                return {'success': True, 'obj': clients}
            if path == '/panel/api/clients/onlines':
                return {'success': True, 'obj': []}
            if path == '/panel/api/inbounds/add':
                created = dict(json_body)
                created['id'] = 201
                remote_inbounds.append(created)
                return {'success': True, 'obj': {'id': 201}}
            if path == '/panel/api/clients/add':
                created_clients.append(json_body)
                return {'success': True, 'msg': 'ok'}
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.post(f'/api/users/{self.user_id}/xui-clients/create-inbound', json={
                    'backend_id': self.backend_id,
                    'inbound_payload': quick_payload,
                    'client': {
                        'total_gb': 1,
                        'expiry_time': 1893456000000,
                        'limit_ip': 2,
                        'comment': 'created-from-user-modal'
                    }
                })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(created_clients[0]['inboundIds'], [201])
        self.assertTrue(created_clients[0]['client']['email'].endswith(f'-u{self.user_id}-in201'))
        self.assertIn('id', created_clients[0]['client'])
        self.assertNotIn('totalGB', created_clients[0]['client'])
        self.assertNotIn('expiryTime', created_clients[0]['client'])
        self.assertEqual(remote_inbounds[0]['total'], 2 * 1024 * 1024 * 1024)
        self.assertEqual(remote_inbounds[0]['expiryTime'], 1893456000000)
        self.assertEqual(remote_inbounds[0]['reset'], 3)
        with app.app_context():
            mapping = UserXuiClient.query.one()
            self.assertEqual(mapping.inbound_id, 201)
            self.assertEqual(mapping.traffic_used, 5)
            self.assertEqual(mapping.traffic_limit, 2 * 1024 * 1024 * 1024)
            self.assertEqual(mapping.comment, 'created-from-user-modal')

    def test_create_inbound_for_user_finds_new_inbound_by_diff(self):
        remote_inbounds = [inbound(101)]
        created_clients = []

        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            if path == '/panel/api/inbounds/list':
                return {'success': True, 'obj': remote_inbounds}
            if path == '/panel/api/inbounds/options':
                return {'success': True, 'obj': remote_inbounds}
            if path == '/panel/api/clients/list':
                clients = []
                for payload in created_clients:
                    client = dict(payload['client'])
                    client['inboundIds'] = payload['inboundIds']
                    client['traffic'] = {'up': 0, 'down': 0}
                    clients.append(client)
                return {'success': True, 'obj': clients}
            if path == '/panel/api/clients/onlines':
                return {'success': True, 'obj': []}
            if path == '/panel/api/inbounds/add':
                created = dict(json_body)
                created['id'] = 202
                remote_inbounds.append(created)
                return {'success': True, 'msg': 'ok'}
            if path == '/panel/api/clients/add':
                created_clients.append(json_body)
                return {'success': True, 'msg': 'ok'}
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.post(f'/api/users/{self.user_id}/xui-clients/create-inbound', json={
                    'backend_id': self.backend_id,
                    'inbound_payload': inbound_payload(remark='diff-node', port=32002),
                    'client': {}
                })

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(created_clients[0]['inboundIds'], [202])
        with app.app_context():
            self.assertEqual(UserXuiClient.query.one().inbound_id, 202)

    def test_create_inbound_for_user_cleans_up_inbound_when_client_create_fails(self):
        from app import XuiApiError

        remote_inbounds = []
        calls = []

        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            calls.append((method, path))
            if path == '/panel/api/inbounds/list':
                return {'success': True, 'obj': remote_inbounds}
            if path == '/panel/api/inbounds/options':
                return {'success': True, 'obj': remote_inbounds}
            if path == '/panel/api/clients/list':
                return {'success': True, 'obj': []}
            if path == '/panel/api/clients/onlines':
                return {'success': True, 'obj': []}
            if path == '/panel/api/inbounds/add':
                created = dict(json_body)
                created['id'] = 203
                remote_inbounds.append(created)
                return {'success': True, 'obj': {'id': 203}}
            if path == '/panel/api/clients/add':
                raise XuiApiError('client failed', 400)
            if path == '/panel/api/inbounds/del/203':
                remote_inbounds.clear()
                return {'success': True}
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.post(f'/api/users/{self.user_id}/xui-clients/create-inbound', json={
                    'backend_id': self.backend_id,
                    'inbound_payload': inbound_payload(remark='cleanup-node', port=33003),
                    'client': {}
                })

        self.assertEqual(response.status_code, 400)
        self.assertIn(('POST', '/panel/api/inbounds/del/203'), calls)
        self.assertEqual(remote_inbounds, [])
        with app.app_context():
            self.assertEqual(UserXuiClient.query.count(), 0)

    def test_create_inbound_for_user_rejects_unsupported_protocol_or_network_before_remote_create(self):
        cases = [
            inbound_payload(remark='bad-protocol', port=34004, protocol='wireguard', network='tcp'),
            inbound_payload(remark='bad-network', port=34005, protocol='vless', network='kcp'),
        ]

        def fake_xui_request(*_args, **_kwargs):
            raise AssertionError('remote call should not happen')

        for payload in cases:
            with self.subTest(payload=payload['remark']):
                with app.test_client() as client:
                    self.login(client)
                    with patch('app._xui_request', side_effect=fake_xui_request):
                        response = client.post(f'/api/users/{self.user_id}/xui-clients/create-inbound', json={
                            'backend_id': self.backend_id,
                            'inbound_payload': payload,
                            'client': {}
                        })

                self.assertEqual(response.status_code, 400)
                with app.app_context():
                    self.assertEqual(UserXuiClient.query.count(), 0)

    def test_create_inbound_for_user_rejects_port_conflict_before_remote_create(self):
        remote_inbounds = [inbound(101)]
        remote_inbounds[0]['port'] = 35005

        def fake_xui_request(method, path, json_body=None, config_id=None, **_kwargs):
            if path == '/panel/api/inbounds/list':
                return {'success': True, 'obj': remote_inbounds}
            if path == '/panel/api/inbounds/add':
                raise AssertionError('remote add should not happen')
            raise AssertionError(path)

        with app.test_client() as client:
            self.login(client)
            with patch('app._xui_request', side_effect=fake_xui_request):
                response = client.post(f'/api/users/{self.user_id}/xui-clients/create-inbound', json={
                    'backend_id': self.backend_id,
                    'inbound_payload': inbound_payload(remark='conflict-node', port=35005),
                    'client': {}
                })

        self.assertEqual(response.status_code, 400)
        with app.app_context():
            self.assertEqual(UserXuiClient.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
