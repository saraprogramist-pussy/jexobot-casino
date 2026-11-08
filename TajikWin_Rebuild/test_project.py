"""Run: python -m unittest -v test_project"""
import os,tempfile,unittest,sys,json,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import storage,engine
class GameTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();storage.DB=str(Path(self.tmp.name)/'test.sqlite3');storage.init();storage.user(1,'tester');storage.admin_credit(1,10_000_000,'seed')
 def tearDown(self):self.tmp.cleanup()
 def test_new_player_zero(self):
  u=storage.user(42,'new');self.assertEqual(u['balance'],0)
 def test_all_six_instant(self):
  opts={'slots':{},'roulette':{'type':'color','value':'red'},'dice':{'guess':'seven'},'plinko':{'risk':'medium'},'keno':{'numbers':[1,2,3,4,5]},'wheel':{}}
  for i,(game,params) in enumerate(opts.items()):
   with self.subTest(game=game):
    r=storage.instant_bet(1,game,10000,params,'bet'+str(i)+'-unique-123456789')
    self.assertGreaterEqual(r['payout'],0);self.assertIn('result',r)
    same=storage.instant_bet(1,game,10000,params,r['bet_id']);self.assertEqual(r,same)
 def test_five_sessions(self):
  for game in ('blackjack','mines','hilo','poker','tower'):
   with self.subTest(game=game):
    params={'mines':3} if game=='mines' else {}
    r=storage.start_session(1,game,10000,params,'s-'+game)
    self.assertEqual(r['status'],'active')
    if game=='blackjack':out=storage.session_move(1,'stand',{})
    elif game=='mines':out=storage.session_move(1,'open',{'index':next(x for x in range(25) if x not in r['mines'])});out=storage.session_move(1,'cashout',{})
    elif game=='hilo':
     # Find losing move if possible, otherwise cashout after first win.
     guess='lower' if engine.rank(r['current'])==2 else 'higher' if engine.rank(r['current'])==14 else 'higher'
     out=storage.session_move(1,guess,{})
     if out['payout'] is None:out=storage.session_move(1,'cashout',{})
    elif game=='poker':out=storage.session_move(1,'draw',{'hold':[0,2]})
    elif game=='tower':out=storage.session_move(1,'pick',{'index':(r['safe'][0]+1)%3})
    self.assertIsNotNone(out['payout']);self.assertEqual(out['result']['status'],'finished');self.assertIsNone(storage.session(1))
 def test_bounds(self):
  for v in [0,2999,1000001,-4,1.5,True]:
   with self.assertRaises(ValueError):engine.validate_stake(v)
 def test_promo_once(self):
  storage.create_promo('START50',50000,1);self.assertEqual(storage.redeem(1,'START50'),50000)
  with self.assertRaises(ValueError):storage.redeem(1,'START50')
 def test_approval_once(self):
  rid=storage.create_request(1,100000)
  before=storage.get_user(1)['balance']
  self.assertTrue(storage.review_request(rid,True)['changed'])
  self.assertFalse(storage.review_request(rid,True)['changed'])
  self.assertEqual(storage.get_user(1)['balance'],before+100000)
 def test_no_negative_balance(self):
  storage.user(777,'empty')
  with self.assertRaises(ValueError):storage.instant_bet(777,'slots',3000,{},'firsttestbet')
 def test_crash_model(self):
  pts=[engine.crash_point() for _ in range(10000)]
  self.assertTrue(all(1<=p<=21 for p in pts))
  self.assertTrue(any(p==21 for p in pts));self.assertTrue(any(p<=1.05 for p in pts))
 def test_crash_bet_finish(self):
  rid=storage.crash_create_round(7)
  start=storage.get_user(1)['balance']
  b=storage.crash_place(1,10000,2.0)
  storage.crash_start(rid,3.0)
  storage.crash_finish(rid)
  self.assertEqual(storage.get_user(1)['balance'],start+10000)
  storage.crash_finish(rid)
  self.assertEqual(storage.get_user(1)['balance'],start+10000)
 def test_crash_auto_and_abort(self):
  rid=storage.crash_create_round(7);before=storage.get_user(1)['balance']
  storage.crash_place(1,10000,2.0);storage.crash_start(rid,2.5)
  self.assertEqual(storage.crash_auto_cashout(rid,2.01),1)
  self.assertEqual(storage.crash_auto_cashout(rid,2.2),0)
  storage.crash_finish(rid)
  self.assertEqual(storage.get_user(1)['balance'],before+10000)
  rid2=storage.crash_create_round(7);before=storage.get_user(1)['balance']
  storage.crash_place(1,10000,None)
  storage.crash_abort_round(rid2)
  self.assertEqual(storage.get_user(1)['balance'],before)
 def test_keno_1_to_10_picks(self):
  for n in range(1,11):
   r,p=engine.instant('keno',10000,{'numbers':list(range(1,n+1))})
   self.assertEqual(len(r['picks']),n);self.assertGreaterEqual(p,0)
 def test_payout_model(self):
  import math
  self.assertAlmostEqual(sum(engine.WHEEL_SECTORS)/20,.95,places=3)
  for table in engine.PLINKO_TABLES.values():
   expected=sum(math.comb(10,i)/1024*v for i,v in enumerate(table))
   self.assertTrue(.94<expected<.98,expected)
 def test_assets(self):
  root=Path(__file__).parent/'webapp'
  for game in ['slots','roulette','dice','blackjack','crash','mines','plinko','keno','wheel','hilo','poker','tower']:
   import xml.etree.ElementTree as ET
   ET.parse(root/'assets'/f'{game}.svg')
  for file in ['credit','roulette','dice','bet','shuffle','jackpot','chips']:
   self.assertTrue((root/'sounds'/f'{file}.mp3').stat().st_size>1000)
if __name__=='__main__':unittest.main()
