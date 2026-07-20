import shutil
import unittest
from pathlib import Path

from app import app, db, _subscription_cache
from models import Node


class DialerProxyChainSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True)
        cls.db_path = Path(app.instance_path) / 'clash_manager.db'
        cls.backup_path = cls.db_path.with_suffix('.db.chain-test-backup')
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

            self.front = self.add_node({
                'name': 'front',
                'type': 'ss',
                'server': 'front.example.test',
                'port': 1001,
                'cipher': 'aes-128-gcm',
                'password': 'front-password'
            }, protocol='ss', order=1)
            self.back = self.add_node({
                'name': 'back',
                'type': 'vless',
                'server': 'old-back.example.test',
                'port': 2001,
                'uuid': 'old-back-uuid',
                'udp': True
            }, protocol='vless', order=2)
            self.chain = self.add_node({
                'name': 'chain',
                'type': 'vless',
                'server': 'old-back.example.test',
                'port': 2001,
                'uuid': 'old-back-uuid',
                'disable-udp': True,
                'dialer-proxy': 'front',
                '__chain_dependencies': ['front', 'back']
            }, protocol='vless', order=3)
            self.grandchild = self.add_node({
                'name': 'grandchild',
                'type': 'vless',
                'server': 'old-back.example.test',
                'port': 2001,
                'uuid': 'old-back-uuid',
                'disable-udp': True,
                'dialer-proxy': 'front',
                '__chain_dependencies': ['front', 'chain']
            }, protocol='vless', order=4)
            db.session.commit()
            self.front_id = self.front.id
            self.back_id = self.back.id
            self.chain_id = self.chain.id
            self.grandchild_id = self.grandchild.id

    def tearDown(self):
        with app.app_context():
            db.session.remove()

    @staticmethod
    def add_node(config, protocol, order):
        node = Node(
            name=config['name'],
            original_name=config['name'],
            protocol=protocol,
            order=order
        )
        node.set_config(config)
        db.session.add(node)
        db.session.flush()
        return node

    @staticmethod
    def login(client):
        with client.session_transaction() as session:
            session['admin_id'] = 1

    def test_back_node_config_update_propagates_through_multiple_chain_levels(self):
        updated_config = {
            'name': 'back',
            'type': 'vless',
            'server': 'new-back.example.test',
            'port': 2443,
            'uuid': 'new-back-uuid',
            'udp': True
        }

        with app.test_client() as client:
            self.login(client)
            response = client.put(
                f'/api/nodes/{self.back_id}/config',
                json={'config': updated_config}
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with app.app_context():
            chain = db.session.get(Node, self.chain_id)
            grandchild = db.session.get(Node, self.grandchild_id)
            for node in (chain, grandchild):
                config = node.get_config()
                self.assertEqual(config['server'], 'new-back.example.test')
                self.assertEqual(config['port'], 2443)
                self.assertEqual(config['uuid'], 'new-back-uuid')
                self.assertEqual(config['name'], node.name)
                self.assertEqual(config['dialer-proxy'], 'front')
                self.assertIn('disable-udp', config)
                self.assertNotIn('udp', config)

    def test_renaming_front_and_back_updates_chain_references(self):
        with app.test_client() as client:
            self.login(client)
            response = client.put(
                f'/api/nodes/{self.front_id}',
                json={'name': 'front-new'}
            )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

            response = client.put(
                f'/api/nodes/{self.back_id}',
                json={'name': 'back-new'}
            )
            self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

        with app.app_context():
            chain = db.session.get(Node, self.chain_id)
            grandchild = db.session.get(Node, self.grandchild_id)
            chain_config = chain.get_config()
            grandchild_config = grandchild.get_config()

            self.assertEqual(chain_config['dialer-proxy'], 'front-new')
            self.assertEqual(chain_config['__chain_dependencies'], ['front-new', 'back-new'])
            self.assertEqual(grandchild_config['dialer-proxy'], 'front-new')
            self.assertEqual(grandchild_config['__chain_dependencies'], ['front-new', 'chain'])


if __name__ == '__main__':
    unittest.main()
