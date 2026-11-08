"""Run with: python -m unittest test_project.py"""
import hashlib
import hmac
import importlib
import json
import os
import tempfile
import time
import unittest
from urllib.parse import urlencode
from fastapi.testclient import TestClient

class CasinoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        os.environ['DB_PATH']=os.path.join(cls.tmp.name,'test.db')
        import db,server
        cls.db=importlib.reload(db)
        cls.server=importlib.reload(server)
        cls.db.init_db()
        cls.server.set_bot_token('test-token-123')
        cls.client=TestClient(cls.server.app)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def data(self, user_id):
        d={'user':json.dumps({'id':user_id,'username':f'tester{user_id}'}, separators=(',',':')),'auth_date':str(int(time.time())),'query_id':'test'}
        check='\n'.join(f'{k}={v}' for k,v in sorted(d.items()))
        secret=hmac.new(b'WebAppData',b'test-token-123',hashlib.sha256).digest()
        d['hash']=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        return urlencode(d)

    def post(self, path,uid,**data):return self.client.post(path,json={'initData':self.data(uid),**data})
    def me(self, uid):return self.client.get('/api/me',params={'initData':self.data(uid)}).json()

    def test_games_and_promos(self):
        uid=9001
        self.assertEqual(self.me(uid)['balance'],100000)
        self.assertEqual(self.post('/api/bonus',uid).status_code,404)
        for path,extra in [('/api/slots',{}),('/api/roulette',{'bet_type':'color','bet_value':'red'}),('/api/dice',{'guess':3})]:
            r=self.post(path,uid,stake=100,**extra)
            self.assertEqual(r.status_code,200,r.text)
            self.assertIn('balance',r.json())
        b=self.me(uid)['balance']
        self.db.create_promo('HELLO',500,2)
        self.assertEqual(self.post('/api/promo/redeem',uid,code='hello').json()['balance'],b+500)
        self.assertEqual(self.post('/api/promo/redeem',uid,code='hello').status_code,400)
        self.assertEqual(self.post('/api/promo/redeem',9002,code='HELLO').status_code,200)
        self.assertEqual(self.post('/api/promo/redeem',9003,code='HELLO').status_code,400)

    def test_blackjack_sessions(self):
        uid=9101
        self.me(uid)
        r=self.post('/api/blackjack/start',uid,stake=200)
        self.assertEqual(r.status_code,200,r.text)
        sess=self.me(uid)['active_session']
        self.assertEqual(len(sess['state']['dealer']),2)
        self.assertEqual(sess['state']['dealer'][1],'🂠')
        self.assertEqual(self.post('/api/blackjack/start',uid,stake=200).status_code,400)
        self.assertEqual(self.post('/api/slots',uid,stake=10).status_code,400)
        r=self.post('/api/blackjack/stand',uid)
        self.assertEqual(r.status_code,200,r.text)
        self.assertTrue(r.json()['finished'])
        self.assertIsNone(self.me(uid)['active_session'])
        self.assertEqual(self.post('/api/blackjack/stand',uid).status_code,400)

    def test_crash_and_mines(self):
        uid=9201
        self.me(uid)
        r=self.post('/api/crash/start',uid,stake=100)
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.me(uid)['active_session']['state'],{})
        self.assertEqual(self.client.get('/api/crash/status',params={'initData':self.data(uid)}).status_code,200)
        self.assertEqual(self.post('/api/crash/cashout',uid).status_code,200)
        self.assertEqual(self.post('/api/crash/cashout',uid).status_code,400)
        r=self.post('/api/mines/start',uid,stake=200,mines_count=2)
        self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('mine_positions',self.me(uid)['active_session']['state'])
        self.assertEqual(self.post('/api/mines/reveal',uid,tile_index=25).status_code,400)
        self.assertEqual(self.post('/api/mines/cashout',uid).status_code,400)
        for idx in range(25):
            response=self.post('/api/mines/reveal',uid,tile_index=idx)
            self.assertEqual(response.status_code,200,response.text)
            if response.json().get('busted') or response.json().get('cleared_all'):
                break
        else:
            r=self.post('/api/mines/cashout',uid)
            self.assertEqual(r.status_code,200,r.text)
        self.assertIsNone(self.me(uid)['active_session'])

    def test_auth_and_stake(self):
        self.assertEqual(self.client.get('/api/me',params={'initData':'wrong'}).status_code,401)
        self.me(9301)
        for stake in [0,-1,1000000001,100001]:
            self.assertEqual(self.post('/api/slots',9301,stake=stake).status_code,400)
        self.assertEqual(self.me(9301)['balance'],100000)

if __name__ == '__main__':unittest.main()
