
import unittest
from pathlib import Path
class V3StaticTests(unittest.TestCase):
 def test_assets_exist(self):
  w=Path(__file__).parent/'webapp'
  for name in ['slots','roulette','dice','blackjack','crash','mines','plinko','keno','wheel','hilo','poker','tower']:
   self.assertTrue((w/'assets'/f'{name}.svg').exists())
   self.assertTrue((w/'sounds'/f'{name}.wav').exists())
  self.assertTrue((w/'sounds'/'credit.wav').exists())
 def test_ui_contains_new_controls(self):
  w=Path(__file__).parent/'webapp';html=(w/'index.html').read_text();js=(w/'app.js').read_text()
  for x in ['game-search','game-categories','round-status','catalog-grid','credit-open']:self.assertIn(x,html)
  self.assertIn('ROUND_WAIT_MS=15000',js)
  self.assertIn('waitForRound()',js)
