import tempfile
import time
import unittest
from pathlib import Path
from maker import MakerPaper, MAKER_FEE, TAKER_FEE, maker_required_change, MIN_MOMENTUM_BPS

class MakerShadowTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/"maker.json"
        self.bot=MakerPaper(path=self.path)
    def tearDown(self):
        self.folder.cleanup()
    def test_fee_hurdle_includes_both_sides(self):
        self.assertGreater(maker_required_change(),2*MAKER_FEE)
        self.assertGreater(maker_required_change(),0.008)
    def test_paper_only(self):
        self.assertEqual(self.bot.status()["mode"],"PAPER ONLY MAKER SHADOW")
        self.assertEqual(len(self.bot.trades),0)
    def test_quote_entry_without_instant_fill(self):
        t=time.time()
        for i in range(12):
            # 2 bps/s upward momentum, fresh quote per second
            price=100+i*.02
            self.bot.observe("BTC/USD",price,price+0.01,now=t+i)
        self.assertGreaterEqual(self.bot.counts["quoted"],1)
        self.assertIsNotNone(self.bot.order)
        self.assertIsNone(self.bot.position)
    def test_quote_expires_without_fill(self):
        t=time.time()
        for i in range(12):
            price=100+i*.02
            self.bot.observe("ETH/USD",price,price+0.01,now=t+i)
        self.assertIsNotNone(self.bot.order)
        self.bot.observe("ETH/USD",101,101.01,now=t+40)
        self.assertIsNone(self.bot.order)
        self.assertGreaterEqual(self.bot.counts["expired"],1)
    def test_forced_exit_costs_are_not_omitted(self):
        t=time.time()
        self.bot.position={"symbol":"SOL/USD","entry":100.0,"qty":1.0,
                           "entry_fee":100*MAKER_FEE,"at":t-50}
        self.bot.cash-=100.4
        self.bot.close(t,99.95,TAKER_FEE,"TAKER STOP")
        self.assertLess(self.bot.trades[0]["pnl"],-1)
        self.assertGreater(self.bot.trades[0]["fees"],1)
    def test_persistence(self):
        t=time.time()
        for i in range(12):self.bot.observe("SOL/USD",100+i*.02,100+i*.02+.01,now=t+i)
        self.bot.save()
        other=MakerPaper(path=self.path)
        self.assertEqual(other.counts,self.bot.counts)
        self.assertEqual(other.status()["mode"],"PAPER ONLY MAKER SHADOW")
    def test_forged_live_state_rejected(self):
        self.path.write_text('{"mode":"LIVE"}')
        with self.assertRaises(RuntimeError):
            MakerPaper(path=self.path)

if __name__=="__main__":unittest.main()
