import base64
import unittest
from urllib.parse import quote

from parsers import ProxyParser


class ShadowsocksParserTest(unittest.TestCase):
    cipher = '2022-blake3-aes-256-gcm'
    password = base64.b64encode(bytes(range(32))).decode() + ':' + base64.b64encode(bytes(range(224, 256))).decode()

    @classmethod
    def share_url(cls):
        return f'ss://{cls.cipher}:{quote(cls.password, safe=":")}@ss.example.test:33803?type=tcp#'

    def assert_ss2022(self, node):
        self.assertIsNotNone(node)
        self.assertEqual(node['type'], 'ss')
        self.assertEqual(node['cipher'], self.cipher)
        self.assertEqual(node['password'], self.password)
        self.assertEqual(node['server'], 'ss.example.test')
        self.assertEqual(node['port'], 33803)
        self.assertEqual(node['name'], 'SS节点')

    def test_plain_ss2022_multikey_with_empty_fragment(self):
        self.assert_ss2022(ProxyParser.parse_proxy(self.share_url()))

    def test_escaped_scheme_and_separator(self):
        for scheme, separator in [('ss\\://', '@'), ('ss://', '\\@'), ('ss\\://', '\\@')]:
            with self.subTest(scheme=scheme, separator=separator):
                url = self.share_url().replace('ss://', scheme).replace('@', separator)
                self.assert_ss2022(ProxyParser.parse_proxy(url))
                self.assert_ss2022(ProxyParser.parse_ss(url))

    def test_percent_encoded_cipher_and_password(self):
        url = f'ss://{quote(self.cipher).replace("-", "%2D")}:{quote(self.password, safe="")}@ss.example.test:33803'
        self.assert_ss2022(ProxyParser.parse_proxy(url))

    def test_plain_password_is_decoded_once_without_losing_spaces_or_plus(self):
        password = ' a+b:/@?#%2F '
        url = f'ss://aes-128-gcm:{quote(password, safe="")}@ss.example.test:443#test'
        node = ProxyParser.parse_proxy(url)
        self.assertEqual(node['password'], password)

    def test_standard_and_urlsafe_base64_userinfo(self):
        userinfo = 'aes-256-gcm:password:with:colons?~'
        for encoder in (base64.b64encode, base64.urlsafe_b64encode):
            for padded in (True, False):
                with self.subTest(encoder=encoder.__name__, padded=padded):
                    encoded = encoder(userinfo.encode()).decode()
                    if not padded:
                        encoded = encoded.rstrip('=')
                    url = f'ss://{quote(encoded, safe="")}@ss.example.test:443#test%20node'
                    node = ProxyParser.parse_proxy(url)
                    self.assertEqual(node['cipher'], 'aes-256-gcm')
                    self.assertEqual(node['password'], 'password:with:colons?~')
                    self.assertEqual(node['name'], 'test node')

    def test_legacy_whole_url_base64(self):
        encoded = base64.b64encode(b'aes-128-gcm:pass:word@ss.example.test:443').decode().rstrip('=')
        node = ProxyParser.parse_proxy(f'ss://{encoded}#legacy')
        self.assertEqual(node['password'], 'pass:word')
        self.assertEqual(node['server'], 'ss.example.test')
        self.assertEqual(node['port'], 443)

    def test_ipv6_and_optional_slash_with_plugin(self):
        url = 'ss://aes-128-gcm:password@[2001:db8::1]:443/?plugin=obfs-local%3Bobfs%3Dhttp%3Bobfs-host%3Dexample.test&udp=1&uot=true#ipv6'
        node = ProxyParser.parse_proxy(url)
        self.assertEqual(node['server'], '2001:db8::1')
        self.assertEqual(node['port'], 443)
        self.assertEqual(node['plugin'], 'obfs')
        self.assertEqual(node['plugin-opts'], {'mode': 'http', 'host': 'example.test'})
        self.assertTrue(node['udp'])
        self.assertTrue(node['udp-over-tcp'])

    def test_subscription_plain_and_base64(self):
        content = self.share_url()
        for subscription in (content, base64.b64encode(content.encode()).decode()):
            with self.subTest(encoded=subscription != content):
                nodes = ProxyParser.parse_subscription(subscription)
                self.assertEqual(len(nodes), 1)
                self.assert_ss2022(nodes[0])

    def test_share_url_round_trip(self):
        node = ProxyParser.parse_proxy(self.share_url())
        self.assertEqual(ProxyParser.parse_proxy(ProxyParser.to_share_url(node)), node)

    def test_invalid_links_are_rejected(self):
        for url in (
            'ss://not-base64@ss.example.test:443',
            'ss://aes-128-gcm:@ss.example.test:443',
            'ss://:password@ss.example.test:443',
            'ss://aes-128-gcm:password@:443',
            'ss://aes-128-gcm:password@ss.example.test',
            'ss://aes-128-gcm:password@ss.example.test:0',
            'ss://aes-128-gcm:password@ss.example.test:65536',
            'ss://aes-128-gcm:password@ss.example.test:abc',
            'ss://aes-128-gcm:password@ss.example.test:443/invalid',
        ):
            with self.subTest(url=url):
                self.assertIsNone(ProxyParser.parse_proxy(url))


class ShadowsocksImportTest(unittest.TestCase):
    def test_import_saves_decoded_multikey_password(self):
        from flask import Flask
        from app import manage_nodes
        from models import db, Node

        test_app = Flask(__name__)
        test_app.config.update(TESTING=True, SECRET_KEY='ss-parser-test', SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(test_app)
        test_app.add_url_rule('/api/nodes', view_func=manage_nodes, methods=['POST'])

        with test_app.app_context():
            db.create_all()
            try:
                with test_app.test_client() as client:
                    with client.session_transaction() as session:
                        session['admin_id'] = 1
                    for escaped in (False, True):
                        url = ShadowsocksParserTest.share_url()
                        if escaped:
                            url = url.replace('ss://', 'ss\\://').replace('@', '\\@')
                        response = client.post('/api/nodes', json={'url': url})
                        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
                        node = db.session.get(Node, response.get_json()['id'])
                        self.assertEqual(node.name, 'SS节点')
                        self.assertEqual(node.get_config()['password'], ShadowsocksParserTest.password)
                        self.assertEqual(node.get_config()['cipher'], ShadowsocksParserTest.cipher)
            finally:
                db.session.remove()
                db.drop_all()
                db.engine.dispose()


if __name__ == '__main__':
    unittest.main()
