import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import PaperScalper, roundtrip_hurdle, exit_net, CAPITAL

class TestPaperScalp(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.bot=PaperScalper(path=Path(self.temp.name)/"state.json")
    def tearDown(self):
        self.temp.cleanup()
    def test_paper_only_and_initialization(self):
        self.assertEqual(self.bot.cash,CAPITAL)
        self.assertEqual(self.bot.status()["trades"],[])
        self.assertEqual(self.bot.status()["status"],"WAITING FOR QUOTES")
    def test_roundtrip_fee_hurdle(self):
        self.assertGreater(roundtrip_hurdle(100,100.01),0.016)
        self.assertGreater(roundtrip_hurdle(100,101),roundtrip_hurdle(100,100.01))
    def test_roundtrip_cost_realism(self):
        entry=100.02
        qty=2.5
        close_value=exit_net(entry,100.01,qty)-(entry*qty)*0.008
        self.assertLess(close_value,0)
    def test_invalid_quote_rejected(self):
        self.bot.tick("BTC/USD",100,99)
        self.assertEqual(self.bot.seen,0)
        self.bot.tick("BTC/USD",-1,3)
        self.assertEqual(self.bot.seen,0)
    def test_no_trade_without_warmup(self):
        self.bot.tick("BTC/USD",100,101)
        self.assertIsNone(self.bot.position)
        self.assertEqual(self.bot.seen,1)
    def test_save_and_reload(self):
        self.bot.tick("ETH/USD",100,101)
        self.bot.save()
        newer=PaperScalper(self.bot.path)
        self.assertEqual(newer.cash,CAPITAL)
        self.assertEqual(newer.seen,1)
    def test_restore_nonpaper_forbidden(self):
        self.bot.path.write_text('{"mode":"LIVE"}')
        with self.assertRaises(RuntimeError):
            PaperScalper(self.bot.path)
    def test_exit_fee_included(self):
        self.bot.enter("ETH/USD",{"bid":99.9,"ask":100.0})
        self.assertIsNotNone(self.bot.position)
        self.bot.close({"bid":100.0,"ask":100.1},"TEST")
        self.assertLess(self.bot.trades[0]["pnl"],0)
        self.assertGreater(self.bot.trades[0]["fees"],3.9)
        self.assertIsNone(self.bot.position)

if __name__=="__main__":
    unittest.main()
