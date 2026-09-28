"""节点排序与真实订阅输出回归测试；使用独立内存数据库。"""
import base64
import unittest
from unittest.mock import patch
from urllib.parse import unquote

import yaml
from flask import Flask

import app as app_module
from models import db, Node, Subscription, User, UserNode


class NodeOrderTest(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite://')
        db.init_app(self.app)
        for rule in app_module.app.url_map.iter_rules():
            if rule.endpoint != 'static':
                self.app.add_url_rule(rule.rule, rule.endpoint,
                                      app_module.app.view_functions[rule.endpoint], methods=rule.methods)
        self.app.after_request(app_module.clear_subscription_cache_after_api_write)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        app_module._subscription_cache.clear()
        nodes = []
        for name in ['first', 'second', 'third']:
            node = Node(name=name, original_name=name, protocol='ss', order=0)
            node.set_config({'name': name, 'type': 'ss', 'server': 'example.test',
                             'port': 443, 'cipher': 'aes-128-gcm', 'password': 'test'})
            nodes.append(node)
        group = Subscription(name='group', subscription_token='group-token', nodes=nodes[:2])
        user = User(username='user', subscription_token='user-token', subscriptions=[group])
        direct_user = User(username='direct', subscription_token='direct-token', subscriptions=[group])
        db.session.add_all(nodes + [group, user, direct_user])
        db.session.flush()
        db.session.add(UserNode(user_id=direct_user.id, node_id=nodes[2].id))
        db.session.commit()
        self.ids = [node.id for node in nodes]
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['admin_id'] = 1

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()
        app_module._subscription_cache.clear()

    def reorder(self, ids):
        return self.client.put('/api/nodes/reorder', json={'node_ids': ids})

    def names(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        config = yaml.safe_load(response.data)
        names = [proxy['name'] for proxy in config['proxies']]
        self.assertEqual([name for name in config['proxy-groups'][0]['proxies'] if name in names], names)
        return names

    def test_order_persists_and_updates_cached_subscriptions(self):
        group_path = '/sub/subscription/group-token'
        user_path = '/sub/user/user-token'
        self.assertEqual(self.names(group_path), ['first', 'second'])
        self.assertEqual(self.names(user_path), ['first', 'second'])
        self.assertTrue(app_module._subscription_cache)
        self.assertEqual(self.reorder(self.ids[::-1]).status_code, 200)
        self.assertFalse(app_module._subscription_cache)
        self.assertEqual([(n['id'], n['order']) for n in self.client.get('/api/nodes').json],
                         list(zip(self.ids[::-1], range(3))))
        self.assertEqual(self.names(group_path), ['second', 'first'])
        self.assertEqual(self.names(user_path), ['second', 'first'])
        self.assertEqual(self.names('/sub/user/direct-token'), ['third', 'second', 'first'])
        response = self.client.get('/sub/user/direct-token/shadowrocket')
        self.assertEqual(response.status_code, 200)
        links = base64.b64decode(response.data).decode().splitlines()
        self.assertEqual([unquote(link.split('#')[1]) for link in links], ['third', 'second', 'first'])

    def test_invalid_input_does_not_modify_order(self):
        for payload in [None, [], {}, {'node_ids': '1'}, {'node_ids': [True]},
                        {'node_ids': ['1']}, {'node_ids': [1.0]}, {'node_ids': [-1]},
                        {'node_ids': self.ids + self.ids}]:
            with self.subTest(payload=payload):
                response = self.client.put('/api/nodes/reorder', json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual([n.order for n in Node.query.order_by(Node.id)], [0, 0, 0])

    def test_stale_list_is_rejected(self):
        for ids in [[], self.ids[:-1], self.ids + [999], [999, *self.ids[1:]]]:
            self.assertEqual(self.reorder(ids).status_code, 409)
        self.assertEqual([n.order for n in Node.query.order_by(Node.id)], [0, 0, 0])

    def test_requires_login(self):
        response = self.app.test_client().put('/api/nodes/reorder', json={'node_ids': self.ids})
        self.assertEqual(response.status_code, 302)

    def test_commit_failure_rolls_back(self):
        with patch.object(db.session, 'commit', side_effect=RuntimeError('test failure')):
            self.assertEqual(self.reorder(self.ids[::-1]).status_code, 500)
        self.assertEqual([n.order for n in Node.query.order_by(Node.id)], [0, 0, 0])


if __name__ == '__main__':
    unittest.main()
