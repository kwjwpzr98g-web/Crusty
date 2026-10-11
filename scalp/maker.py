"""Independent maker-style shadow experiment. PAPER ONLY.

Uses BBO quote trade-through as a *proxy* for queue fills. Real maker orders
might never fill. Separate virtual book from the taker strategy.
"""
from collections import deque
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import time

MAKER_FEE = 0.004     # Kraken Pro Tier 1, 40 basis points EACH side
TAKER_FEE = 0.008     # Forced exit modeled at 80 bps
NET_TARGET = 0.0008   # 8 bps intended net return after two maker fees
MIN_MOMENTUM_BPS = 1.2
MAX_SPREAD_BPS = 10.0
ORDER_TTL = 12.0
MAX_HOLD = 150.0
MIN_QUEUE_WAIT = 2.0
THROUGH_BPS = 1.0
COOLDOWN = 5.0
STOP_BPS = 28.0
NOTIONAL = 100.0
MAX_NEW_ORDERS_DAY = 160
MAX_LOSS_DAY = 100.0
SYMS = ["BTC/USD", "ETH/USD", "SOL/USD", "BNB/USD", "HYPE/USD"]

def stamp(ts):
    return datetime.fromtimestamp(ts,timezone.utc).isoformat(timespec="seconds")

def maker_required_change():
    return (1 + MAKER_FEE) * (1 + NET_TARGET) / (1 - MAKER_FEE) - 1

class MakerPaper:
    def __init__(self, path=None):
        self.path=Path(path or os.environ.get("TALON_MAKER_PATH","/data/maker-paper.json"))
        self.cash=10000.0
        self.position=None
        self.order=None
        self.quotes={}
        self.points={s:deque(maxlen=200) for s in SYMS}
        self.counts={"quoted":0,"expired":0,"filled":0,"maker_exits":0,"forced_exits":0}
        self.trades=[]
        self.events=[]
        self.last_action=0.0
        self.day=datetime.now(timezone.utc).date().isoformat()
        self.day_start=self.cash
        self.today_orders=0
        self.locked=False
        self.equity_history=deque(maxlen=3600)
        self.load()

    def load(self):
        if not self.path.exists():
            return
        saved=json.loads(self.path.read_text())
        if saved.get("mode")!="PAPER ONLY MAKER SHADOW":
            raise RuntimeError("Refusing non-paper maker state")
        for key in ("cash","position","order","counts","trades","events","last_action",
                    "day","day_start","today_orders","locked"):
            if key in saved:
                setattr(self,key,saved[key])
        self.equity_history=deque(saved.get("equity_history",[])[-3600:],maxlen=3600)

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        d={k:getattr(self,k) for k in ("cash","position","order","counts","trades",
             "events","last_action","day","day_start","today_orders","locked")}
        d["mode"]="PAPER ONLY MAKER SHADOW"
        d["equity_history"]=list(self.equity_history)
        fd,name=tempfile.mkstemp(dir=self.path.parent,prefix=".maker-")
        try:
            with os.fdopen(fd,"w") as h:
                json.dump(d,h,allow_nan=False)
            os.replace(name,self.path)
        finally:
            if os.path.exists(name):os.unlink(name)

    def note(self,at,msg):
        self.events=([{"at":stamp(at),"message":msg}]+self.events)[:50]

    def marked(self):
        if not self.position:
            return self.cash
        p=self.position
        q=self.quotes.get(p["symbol"])
        if not q:return self.cash+p["qty"]*p["entry"]*(1-MAKER_FEE)
        return self.cash+p["qty"]*q["bid"]*(1-TAKER_FEE)

    def close(self,now,price,fee,kind):
        p=self.position
        qty=p["qty"]
        exit_fee=price*qty*fee
        gross=qty*(price-p["entry"])
        net=gross-p["entry_fee"]-exit_fee
        self.cash+=price*qty-exit_fee
        self.trades=([{"symbol":p["symbol"],"side":"LONG",
            "entered":stamp(p["at"]),"exited":stamp(now),"hold_s":round(now-p["at"],1),
            "entry":round(p["entry"],8),"exit":round(price,8),
            "gross":round(gross,4),"fees":round(p["entry_fee"]+exit_fee,4),
            "pnl":round(net,4),"reason":kind}]+self.trades)[:1000]
        self.position=None
        self.last_action=now
        if kind=="POSTED LIMIT TARGET":self.counts["maker_exits"]+=1
        else:self.counts["forced_exits"]+=1
        self.note(now,"PAPER maker shadow exit "+kind+", net $"+format(net,".2f"))

    def observe(self,symbol,bid,ask,now=None):
        now=now if now is not None else time.time()
        if symbol not in SYMS or not (0 < bid <= ask and
                                      math.isfinite(bid) and math.isfinite(ask)):
            return
        current_day=datetime.fromtimestamp(now,timezone.utc).date().isoformat()
        if current_day!=self.day:
            self.day=current_day
            self.day_start=self.marked()
            self.today_orders=0
            # A risk lock does not reset automatically.
        self.quotes[symbol]={"bid":bid,"ask":ask,"at":now}
        mid=(bid+ask)/2
        hist=self.points[symbol]
        if not hist or now-hist[-1][0]>=0.7:
            hist.append((now,mid))
        while len(hist)>2 and hist[0][0]<now-25:
            hist.popleft()

        if self.order and self.order["symbol"]==symbol:
            o=self.order
            if now-o["at"]>=ORDER_TTL:
                self.counts["expired"]+=1
                self.note(now,"PAPER maker quote expired "+symbol)
                self.order=None
                self.last_action=now
            elif (now-o["at"]>=MIN_QUEUE_WAIT and
                  ask<=o["price"]*(1-THROUGH_BPS/10000)):
                entry=o["price"]
                q=NOTIONAL/entry
                entry_fee=NOTIONAL*MAKER_FEE
                if self.cash>=NOTIONAL+entry_fee:
                    self.cash-=NOTIONAL+entry_fee
                    self.position={"symbol":symbol,"entry":entry,
                                   "qty":q,"entry_fee":entry_fee,"at":now}
                    self.counts["filled"]+=1
                    self.note(now,"SIMULATED maker fill proxy "+symbol+" (queue unverified)")
                self.order=None

        if self.position and self.position["symbol"]==symbol:
            p=self.position
            expected_target=p["entry"]*(1+maker_required_change())
            if (now-p["at"]>=MIN_QUEUE_WAIT and
                bid>=expected_target*(1+THROUGH_BPS/10000)):
                self.close(now,expected_target,MAKER_FEE,"POSTED LIMIT TARGET")
            elif bid<=p["entry"]*(1-STOP_BPS/10000):
                self.close(now,bid,TAKER_FEE,"TAKER STOP")
            elif now-p["at"]>=MAX_HOLD:
                self.close(now,bid,TAKER_FEE,"TAKER TIMEOUT")

        if not self.equity_history or now-self.equity_history[-1][0]>=15:
            self.equity_history.append([round(now,1),round(self.marked(),4)])
        if self.marked()<self.day_start-MAX_LOSS_DAY:
            self.locked=True
            self.note(now,"MAKER SHADOW locked: daily virtual loss limit")
        if self.locked or self.position or self.order or self.today_orders>=MAX_NEW_ORDERS_DAY:
            return
        if now-self.last_action<COOLDOWN:return
        if (ask/bid-1)*10000>MAX_SPREAD_BPS:return
        anchor=next((p for p in hist if p[0]>=now-10),None)
        if not anchor or now-anchor[0]<5:return
        momentum=(mid/anchor[1]-1)*10000
        if MIN_MOMENTUM_BPS <= momentum <= 60:
            self.order={"symbol":symbol,"price":bid,"at":now}
            self.last_action=now
            self.today_orders+=1
            self.counts["quoted"]+=1
            self.note(now,"PAPER post-only buy quote "+symbol+"; waiting for trade-through")

    def status(self):
        marked=self.marked()
        return {"mode":"PAPER ONLY MAKER SHADOW","equity":round(marked,2),
          "pnl":round(marked-10000,2),"counts":self.counts,
          "order":self.order,"position":self.position,
          "today_orders":self.today_orders,"max_new_orders_day":MAX_NEW_ORDERS_DAY,
          "locked":self.locked,"trades":self.trades[:30],"events":self.events[:20],
          "history":list(self.equity_history)[-150:],
          "fee_maker_bps":MAKER_FEE*10000,"fee_forced_exit_bps":TAKER_FEE*10000,
          "net_target_bps":NET_TARGET*10000,
          "round_trip_hurdle_bps":round(maker_required_change()*10000,1),
          "fill_warning":"Trade-through is only a queue-fill proxy; passive orders may never actually fill."}
