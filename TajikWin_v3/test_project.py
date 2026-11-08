"""Run: python -m unittest -v test_project.py"""
import os,tempfile,unittest,json,hmac,hashlib,time
from urllib.parse import urlencode
from fastapi.testclient import TestClient

class TajikWinTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory()
  os.environ['DB_PATH']=cls.tmp.name+'/test.sqlite'
  import db,server
  cls.db=db;cls.server=server;db.init_db();server.set_bot_token('test-token')
  cls.client=TestClient(server.app)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def token(self,uid):
  values={'auth_date':str(int(time.time())),'user':json.dumps({'id':uid,'username':'player'+str(uid)},separators=(',',':'))}
  check='\n'.join(f'{k}={v}' for k,v in sorted(values.items()))
  secret=hmac.new(b'WebAppData',b'test-token',hashlib.sha256).digest()
  values['hash']=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
  return urlencode(values)
 def post(self,path,uid,**payload):return self.client.post(path,json={'initData':self.token(uid),**payload})
 def me(self,uid):return self.client.get('/api/me',params={'initData':self.token(uid)}).json()
 def test_auth_stakes_and_all_twelve_games(self):
  self.assertEqual(self.client.get('/api/me',params={'initData':'bad'}).status_code,401)
  uid=711;self.me(uid)
  for stake in (0,2999,1000001):self.assertEqual(self.post('/api/slots',uid,stake=stake).status_code,400)
  for path,opts in [('/api/slots',{}),('/api/roulette',{'bet_type':'color','bet_value':'red'}),('/api/dice',{'guess':4}),('/api/plinko',{'choice':'low'}),('/api/keno',{'numbers':[1,3,5,7,9]}),('/api/wheel',{}),('/api/hilo',{'choice':'higher'}),('/api/poker',{}),('/api/tower',{'level':2})]:
   res=self.post(path,uid,stake=3000,**opts)
   self.assertEqual(res.status_code,200,(path,res.text))
   self.assertGreaterEqual(res.json()['balance'],0)
  r=self.post('/api/blackjack/start',uid,stake=3000);self.assertEqual(r.status_code,200,r.text)
  r=self.post('/api/blackjack/stand',uid);self.assertEqual(r.status_code,200,r.text)
  r=self.post('/api/mines/start',uid,stake=3000,mines_count=3);self.assertEqual(r.status_code,200,r.text)
  for i in range(25):
   r=self.post('/api/mines/reveal',uid,tile_index=i)
   self.assertEqual(r.status_code,200,r.text)
   if r.json().get('busted') or r.json().get('cleared_all'):break
  r=self.post('/api/crash/start',uid,stake=3000);self.assertEqual(r.status_code,200,r.text)
  r=self.post('/api/crash/cashout',uid);self.assertEqual(r.status_code,200,r.text)
  self.assertGreaterEqual(len(self.client.get('/api/history',params={'initData':self.token(uid)}).json()),12)
 def test_credit_requests_idempotence(self):
  uid=712;before=self.me(uid)['balance']
  r=self.post('/api/credits/request',uid,amount=120000);self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(self.post('/api/credits/request',uid,amount=120000).status_code,400)
  request_id=r.json()['request_id'];r=self.db.decide_credit_request(request_id,True)
  self.assertEqual(r['balance'],before+120000)
  with self.assertRaises(ValueError):self.db.decide_credit_request(request_id,True)
  self.assertEqual(self.me(uid)['balance'],before+120000)
 def test_promo_preferences_history_and_support(self):
  uid=713;self.me(uid)
  self.db.create_promo('GO3',30000,1)
  self.assertEqual(self.post('/api/promo/redeem',uid,code='GO3').status_code,200)
  self.assertEqual(self.post('/api/promo/redeem',uid,code='GO3').status_code,400)
  p=self.post('/api/preferences',uid,lang='en',avatar='♦',currency='RUB',nickname='Lucky',sound=0)
  self.assertEqual(p.status_code,200,p.text)
  self.assertEqual(self.me(uid)['preferences']['currency'],'RUB')
  self.assertEqual(self.post('/api/support',uid,text='Help').status_code,200)
  self.assertEqual(len(self.client.get('/api/support',params={'initData':self.token(uid)}).json()),1)
  self.post('/api/dice',uid,stake=3000,guess=2)
  history=self.client.get('/api/history',params={'initData':self.token(uid)}).json()
  self.assertTrue(history)
  self.assertEqual(self.post('/api/history/action',uid,bet_id=history[0]['id'],action='pin').status_code,200)
  self.assertEqual(self.post('/api/history/action',uid,bet_id=history[0]['id'],action='hide').status_code,200)
  self.assertEqual(self.post('/api/history/action',714,bet_id=history[0]['id'],action='hide').status_code,400)
 def test_health_and_rate_response(self):
  self.assertEqual(self.client.get('/health').json()['ok'],True)
  self.assertEqual(self.client.get('/').status_code,200)
  self.assertEqual(self.client.get('/static/app.js').status_code,200)
if __name__=='__main__':unittest.main()
