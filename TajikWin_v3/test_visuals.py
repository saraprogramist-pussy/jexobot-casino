"""Asset smoke tests for original Tajik Win v2 visual pack."""
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
import math

from fastapi.testclient import TestClient
import server
import games
import games_extra

ROOT=Path(__file__).parent
GAME_IDS='slots roulette dice blackjack crash mines plinko keno wheel hilo poker tower'.split()

class VisualAndMathTests(unittest.TestCase):
 def test_asset_manifest_and_xml(self):
  for game in GAME_IDS:
   with self.subTest(game=game):
    asset=ROOT/'webapp'/'assets'/f'{game}.svg'
    self.assertTrue(asset.is_file())
    self.assertEqual(ET.parse(asset).getroot().tag,'{http://www.w3.org/2000/svg}svg')
  ET.parse(ROOT/'webapp'/'assets'/'brand.svg')
 def test_assets_served_by_fastapi(self):
  with TestClient(server.app) as client:
   for game in GAME_IDS:
    response=client.get(f'/static/assets/{game}.svg')
    self.assertEqual(response.status_code,200,game)
    self.assertIn('<svg',response.text)
   self.assertEqual(client.get('/static/premium.css').status_code,200)
   self.assertIn('premium.css',client.get('/').text)
 def test_slot_return_calculated(self):
  probs=[w/sum(games.SLOT_WEIGHTS) for w in games.SLOT_WEIGHTS]
  total=sum(3*p*p*(1-p) for p in probs)+sum(p**3*m for p,m in zip(probs,[7,7,10,20,30,70]))
  self.assertTrue(0.92<total<0.94,total)
 def test_plinko_all_risks_house_edge(self):
  tables={'low':[4,2,1.4,1.1,.9,.75,.9,1.1,1.4,2,4],
          'medium':[16,6,2,1,.45,.25,.45,1,2,6,16],
          'high':[55,14,4,.7,.07,0,.07,.7,4,14,55]}
  for table in tables.values():
   rtp=sum(math.comb(10,i)/1024*v for i,v in enumerate(table))
   self.assertLess(rtp,1)
 def test_roulette_zero_color_return(self):
  # Force zero outcome to verify special green payout.
  old=games.spin_roulette
  try:
   games.spin_roulette=lambda:(0,'green')
   self.assertEqual(games.resolve_roulette_bet('color','green',3000)[2],108000)
  finally:
   games.spin_roulette=old

if __name__=='__main__':unittest.main()
