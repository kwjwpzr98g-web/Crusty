"""TALON SCALP — quote-driven *paper-only* experiment; never connects to private APIs."""
import asyncio
import json
import math
import os
import tempfile
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import ClientSession, WSMsgType, web
from maker import MakerPaper

SYMS=["BTC/USD","ETH/USD","SOL/USD","BNB/USD","HYPE/USD"]
ENTRY_FEE=0.008   # Entry-tier Kraken Pro taker fee, adjust only after verification.
EXIT_FEE=0.008
SLIPPAGE=0.0002   # Extra adverse execution slippage per side (illustrative).
CAPITAL=10000.0
MAX_NOTIONAL=250.0
TARGET_NET=0.001  # +0.10% target net return on position, after quoted costs.
ENTRY_LOOKBACK=40.0
MAX_HOLD=180.0
COOLDOWN=30.0
DATA_TIMEOUT=5.0
MAX_DAILY_LOSS=0.02
STATE_FILE=Path(os.getenv("TALON_STATE_PATH","/data/talon-scalp.json"))

def utc(t=None):
    return datetime.fromtimestamp(t if t is not None else time.time(), timezone.utc).isoformat(timespec="seconds")

def fill_cost(notional):
    return notional*ENTRY_FEE

def exit_net(entry, bid, qty):
    # Fees are separate. Price slippage must be adverse on both sides.
    received=bid*(1-SLIPPAGE)
    gross=(received-entry)*qty
    close_fee=received*qty*EXIT_FEE
    return gross-close_fee

def roundtrip_hurdle(bid,ask):
    """Required mid-price appreciation (as a fraction) to net TARGET_NET."""
    if ask <= 0 or bid <= 0: return math.inf
    # Entry uses ask+slippage and charges entry taker fee; exit uses bid-slippage.
    # This figure also includes the current observed spread.
    return max(0,(ask*(1+SLIPPAGE)*(1+ENTRY_FEE+TARGET_NET))/
                  (bid*(1-SLIPPAGE)*(1-EXIT_FEE))-1)

class PaperScalper:
    def __init__(self,path=STATE_FILE):
        self.path=Path(path)
        self.cash=CAPITAL
        self.equity=CAPITAL
        self.peak=CAPITAL
        self.day_start=CAPITAL
        self.day=datetime.now(timezone.utc).date().isoformat()
        self.position=None
        self.trades=[]
        self.events=[]
        self.locked=False
        self.paused=False
        self.last_exit=0.0
        self.quotes={}
        self.points={sym:deque(maxlen=300) for sym in SYMS}
        # Downsampled, bounded time series for drill-down plots. Persist across redeploys.
        self.price_history={sym:deque(maxlen=9000) for sym in SYMS}
        self.equity_history=deque(maxlen=6000)
        self.filter_reasons={"warmup":0,"fees_exceed_move":0,"spread_too_wide":0,"cooldown":0,"risk_lock":0,"paused":0,"already_in_trade":0,"signal_qualified":0}
        self.connection="CONNECTING"
        self.connected_at=None
        self.seen=0
        self.rejected=0
        self.load()

    def load(self):
        if not self.path.exists(): return
        saved=json.loads(self.path.read_text())
        if saved.get("mode")!="PAPER ONLY": raise RuntimeError("Refusing non-paper state")
        for key in ("cash","equity","peak","day_start","day","position","trades",
                    "events","locked","paused","last_exit","seen","rejected"):
            if key in saved: setattr(self,key,saved[key])
        for sym, samples in saved.get("price_history",{}).items():
            if sym in self.price_history and isinstance(samples,list):
                self.price_history[sym]=deque(samples[-9000:],maxlen=9000)
        self.equity_history=deque(saved.get("equity_history",[])[-6000:],maxlen=6000)
        self.filter_reasons.update({key:int(max(0,value)) for key,value in saved.get("filter_reasons",{}).items() if key in self.filter_reasons and isinstance(value,(int,float))})

    def save(self):
        data={k:getattr(self,k) for k in ("cash","equity","peak","day_start","day",
              "position","trades","events","locked","paused","last_exit","seen","rejected")}
        data["mode"]="PAPER ONLY"
        data["price_history"]={s:list(h) for s,h in self.price_history.items()}
        data["equity_history"]=list(self.equity_history)
        data["filter_reasons"]=self.filter_reasons
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(dir=str(self.path.parent),prefix=".scalp-")
        try:
            with os.fdopen(fd,"w") as f:
                json.dump(data,f,allow_nan=False)
                f.flush();os.fsync(f.fileno())
            os.replace(tmp,self.path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)

    def mark(self):
        p=self.position
        if not p: return self.cash
        q=self.quotes.get(p["symbol"])
        return self.cash+(p["qty"]*q["bid"]*(1-SLIPPAGE)*(1-EXIT_FEE)) if q else self.cash+p["qty"]*p["entry"]

    def log(self,msg):
        self.events=([{"at":utc(),"message":msg}]+self.events)[:80]

    def enter(self,sym,q):
        if self.position or self.locked or self.paused:return
        notional=min(MAX_NOTIONAL,self.cash/(1+ENTRY_FEE))
        if notional<10:return
        entry=q["ask"]*(1+SLIPPAGE)
        qty=notional/entry
        fee=notional*ENTRY_FEE
        self.cash-=notional+fee
        self.position={"symbol":sym,"entry":entry,"qty":qty,"fee":fee,
                       "t":time.time(),"at":utc(),"entry_bid":q["bid"],
                       "hurdle_bps":round(roundtrip_hurdle(q["bid"],q["ask"])*10000,1)}
        self.log("PAPER BUY "+sym+"; fee/spread modeled")
        self.save()

    def close(self,q,reason):
        p=self.position
        if not p:return
        actual_bid=q["bid"]*(1-SLIPPAGE)
        proceeds=actual_bid*p["qty"]
        exit_fee=proceeds*EXIT_FEE
        gross=(actual_bid-p["entry"])*p["qty"]
        pnl=gross-p["fee"]-exit_fee
        self.cash+=proceeds-exit_fee
        self.trades=([{"symbol":p["symbol"],"entered":p["at"],"exited":utc(),
                       "hold_s":round(time.time()-p["t"],1),
                       "entry":round(p["entry"],8),"exit":round(actual_bid,8),
                       "gross":round(gross,4),"fees":round(p["fee"]+exit_fee,4),
                       "pnl":round(pnl,4),"reason":reason}]+self.trades)[:800]
        self.position=None
        self.last_exit=time.time()
        self.equity=self.cash
        self.log("PAPER EXIT "+p["symbol"]+" "+reason+"; net "+format(pnl,".2f"))
        self.save()

    def tick(self,sym,bid,ask,ts=None):
        now=time.time() if ts is None else ts
        if sym not in SYMS or min(bid,ask)<=0 or bid>ask:return
        if not (math.isfinite(bid) and math.isfinite(ask)):return
        # Timestamp is local reception, not an assertion of exchange execution speed.
        self.quotes[sym]={"bid":bid,"ask":ask,"mid":(bid+ask)/2,
                          "at":utc(now),"t":now,
                          "spread_bps":round((ask/bid-1)*10000,2)}
        hist=self.points[sym]
        if not hist or now-hist[-1][0]>=0.8: hist.append((now,(bid+ask)/2))
        prices=self.price_history[sym]
        if not prices or now-prices[-1][0]>=10:
            prices.append([round(now,1),round((bid+ask)/2,9),round(bid,9),round(ask,9)])
        self.seen+=1
        if self.position and self.position["symbol"]==sym:
            p=self.position
            # Price move needed for profit after both fees and slippage, using executable bid.
            net=exit_net(p["entry"],bid,p["qty"])-p["fee"]
            if net >= (p["entry"]*p["qty"])*TARGET_NET:
                self.close(self.quotes[sym],"NET TARGET")
            elif bid <= p["entry"]*(1-0.005):
                self.close(self.quotes[sym],"PRICE STOP")
            elif now-p["t"]>=MAX_HOLD:
                self.close(self.quotes[sym],"TIME LIMIT")
        self.equity=self.mark()
        self.peak=max(self.peak,self.equity)
        day=datetime.fromtimestamp(now,timezone.utc).date().isoformat()
        if day != self.day:
            self.day=day;self.day_start=self.equity
        if not self.locked and self.equity < self.day_start*(1-MAX_DAILY_LOSS):
            self.locked=True
            self.log("Daily drawdown circuit breaker triggered")
            if self.position and self.position["symbol"]==sym:
                self.close(self.quotes[sym],"RISK LOCK")
        # Sample net liquidation equity even when waiting or in a position.
        if not self.equity_history or now-self.equity_history[-1][0]>=15:
            self.equity_history.append([round(now,1),round(self.equity,4)])
        if self.position:
            self.filter_reasons["already_in_trade"]+=1;return
        if self.locked:
            self.filter_reasons["risk_lock"]+=1;return
        if self.paused:
            self.filter_reasons["paused"]+=1;return
        if now-self.last_exit<COOLDOWN:
            self.filter_reasons["cooldown"]+=1;return
        self.rejected+=1
        if len(hist)<20:
            self.filter_reasons["warmup"]+=1;return
        anchor=next(((t,mid) for t,mid in hist if t>=now-ENTRY_LOOKBACK),None)
        if not anchor or now-anchor[0]<ENTRY_LOOKBACK*0.6:
            self.filter_reasons["warmup"]+=1;return
        change=(hist[-1][1]/anchor[1]-1)
        hurdle=roundtrip_hurdle(bid,ask)
        # Demand recent positive move above *entire* modeled cost hurdle.
        # Often rejects all signals at retail taker fees; this is intentional.
        if self.quotes[sym]["spread_bps"]>=20:
            self.filter_reasons["spread_too_wide"]+=1
        elif change>hurdle and change<0.08:
            self.filter_reasons["signal_qualified"]+=1
            self.enter(sym,self.quotes[sym])
        else:
            self.filter_reasons["fees_exceed_move"]+=1

    def series(self,symbol="BTC/USD",window="1h"):
        durations={"5m":300,"15m":900,"1h":3600,"4h":14400,"24h":86400}
        if symbol not in SYMS: raise ValueError("Unknown symbol")
        if window not in durations: raise ValueError("Invalid range")
        cutoff=time.time()-durations[window]
        def bounded(data):
            filtered=[point for point in data if point[0]>=cutoff]
            if len(filtered)<=400:return filtered
            step=math.ceil(len(filtered)/399)
            out=filtered[::step]
            if out[-1]!=filtered[-1]:out.append(filtered[-1])
            return out
        return {"symbol":symbol,"range":window,"price":bounded(self.price_history[symbol]),
                "equity":bounded(self.equity_history),
                "trades":[trade for trade in self.trades if
                          (trade["symbol"]==symbol and
                           trade.get("exited","")>=utc(cutoff))][:50],
                "timestamp":utc(),"mode":"PAPER ONLY"}

    def status(self):
        now=time.time()
        active=sum(1 for q in self.quotes.values() if now-q["t"]<DATA_TIMEOUT)
        mark=self.mark()
        return {"name":"TALON SCALP","mode":"PAPER ONLY",
                "feed":self.connection,"active_markets":active,
                "status":"RISK LOCK" if self.locked else ("PAUSED" if self.paused else
                         "STREAMING" if active>0 else "WAITING FOR QUOTES"),
                "cash":round(self.cash,2),"equity":round(mark,2),
                "pnl":round(mark-CAPITAL,2),
                "drawdown_pct":round((1-mark/max(self.peak,1))*100,3),
                "position":self.position,"trades":self.trades[:80],
                "seen":self.seen,"rejected":self.rejected,"events":self.events[:30],
                "markets":{s:({k:v for k,v in q.items() if k!="t"}|
                            {"fresh":now-q["t"]<DATA_TIMEOUT,
                             "fee_hurdle_bps":round(roundtrip_hurdle(q["bid"],q["ask"])*10000,1)})
                           for s,q in self.quotes.items()},
                "filter_reasons":self.filter_reasons,
                "stats":{"wins":sum(t["pnl"]>0 for t in self.trades),
                         "losses":sum(t["pnl"]<0 for t in self.trades),
                         "gross":round(sum(t["gross"] for t in self.trades),3),
                         "fees":round(sum(t["fees"] for t in self.trades),3),
                         "net":round(sum(t["pnl"] for t in self.trades),3),
                         "avg_win":round(sum(t["pnl"] for t in self.trades if t["pnl"]>0)/max(1,sum(t["pnl"]>0 for t in self.trades)),3),
                         "avg_loss":round(sum(t["pnl"] for t in self.trades if t["pnl"]<0)/max(1,sum(t["pnl"]<0 for t in self.trades)),3)},
                "fee_bps_per_side":ENTRY_FEE*10000,
                "target_net_bps":TARGET_NET*10000,
                "timestamp":utc()}

BOT=PaperScalper()
MAKER=MakerPaper()
async def stream():
    while True:
        try:
            BOT.connection="CONNECTING"
            timeout=30
            async with ClientSession() as session:
                async with session.ws_connect("wss://ws.kraken.com/v2",heartbeat=20,timeout=timeout,
                                              max_msg_size=4*1024*1024) as ws:
                    BOT.connection="CONNECTED"
                    BOT.connected_at=utc()
                    await ws.send_json({"method":"subscribe","params":{
                        "channel":"ticker","symbol":SYMS,
                        "event_trigger":"bbo","snapshot":True}})
                    async for msg in ws:
                        if msg.type==WSMsgType.TEXT:
                            j=json.loads(msg.data)
                            if j.get("method")=="subscribe" and not j.get("success",True):
                                BOT.log("Subscription warning: "+str(j.get("error","unknown"))[:100])
                            if j.get("channel")=="ticker":
                                for quote in j.get("data",[]):
                                    try:
                                        sym=quote["symbol"];bid=float(quote["bid"]);ask=float(quote["ask"])
                                        BOT.tick(sym,bid,ask)
                                        MAKER.observe(sym,bid,ask)
                                    except (ValueError,TypeError,KeyError):pass
                        elif msg.type in (WSMsgType.ERROR,WSMsgType.CLOSE,WSMsgType.CLOSED):break
        except asyncio.CancelledError:
            raise
        except Exception as e:
            BOT.log("Feed reconnect: "+str(e)[:100])
        BOT.connection="DISCONNECTED"
        BOT.save()
        MAKER.save()
        await asyncio.sleep(5)

async def persist():
    while True:
        await asyncio.sleep(15)
        BOT.save()
        MAKER.save()

async def api_history(request):
    try:
        return web.json_response(BOT.series(
            request.query.get("symbol","BTC/USD"),request.query.get("range","1h")),
            headers={"Cache-Control":"no-store"})
    except ValueError as error:
        raise web.HTTPBadRequest(text=str(error))

async def api_status(request):
    result=BOT.status()
    result["maker_shadow"]=MAKER.status()
    result["sparklines"]={sym:list(BOT.price_history[sym])[-110:] for sym in SYMS}
    result["equity_sparkline"]=list(BOT.equity_history)[-150:]
    return web.json_response(result,headers={"Cache-Control":"no-store"})
async def health(request):
    # HTTP ready does not imply market feed healthy; API exposes feed separately.
    return web.json_response({"service":"talon-scalp","alive":True,
                              "feed":BOT.connection,"mode":"PAPER ONLY"})
async def index(request):
    p=Path(__file__).with_name("index.html")
    return web.Response(text=p.read_text(),content_type="text/html")
async def startup(app):
    app["workers"]=[asyncio.create_task(stream()),asyncio.create_task(persist())]
async def shutdown(app):
    for worker in app["workers"]:worker.cancel()
    await asyncio.gather(*app["workers"],return_exceptions=True)
    BOT.save()
    MAKER.save()

app=web.Application()
app.router.add_get("/",index)
app.router.add_get("/api/status",api_status)
app.router.add_get("/api/history",api_history)
app.router.add_get("/health",health)
app.on_startup.append(startup)
app.on_cleanup.append(shutdown)

if __name__=="__main__":
    web.run_app(app,host="0.0.0.0",port=int(os.getenv("PORT","8080")))
