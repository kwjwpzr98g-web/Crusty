#!/usr/bin/env python3
"""TALON - paper-only closed-candle market simulator. No exchange order capability."""
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/"talon"/"state.json"
CONFIG=ROOT/"talon"/"config.json"
DATA=ROOT/"docs"/"data.json"

def stamp(t=None):
    return datetime.fromtimestamp(time.time() if t is None else t,timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def initial(cfg):
    n=float(cfg["starting_equity"])
    return dict(mode="PAPER ONLY",cash=n,equity=n,peak=n,initial=n,day_start=n,
                day=None,last_ts=None,position=None,trades=[],history=[],events=[],
                markets={},errors={},paused=False,locked=False,lock_reason=None,
                last_scan=None,last_data=None)

def request(url):
    req=urllib.request.Request(url,headers={"User-Agent":"TALON-PaperBot/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=20) as response:
        result=json.load(response)
    if result.get("error"):
        raise RuntimeError("; ".join(map(str,result["error"])))
    return result["result"]

def pairs_for(symbols):
    results=request("https://api.kraken.com/0/public/AssetPairs")
    choices={}
    for code,meta in results.items():
        if not isinstance(meta,dict):
            continue
        ws=str(meta.get("wsname","")).upper()
        if not ws.endswith("/USD") or ".d" in code:
            continue
        asset=ws.split("/")[0]
        for sym in symbols:
            if asset in (("BTC","XBT") if sym=="BTC" else (sym,)):
                choices[sym]=code
    return choices

def candles(pair):
    url="https://api.kraken.com/0/public/OHLC?"+urllib.parse.urlencode({"pair":pair,"interval":60})
    results=request(url)
    key=next((k for k in results if k!="last"),None)
    if key is None:
        raise ValueError("No OHLC pair result")
    now=int(time.time())
    out=[]
    for r in results[key]:
        ts=int(r[0])
        if ts+3600>now:  # The open/incomplete current hourly candle is never used.
            continue
        o,h,l,c,v=map(float,(r[1],r[2],r[3],r[4],r[6]))
        if min(o,h,l,c)<=0 or v<0 or h<max(o,c,l) or l>min(o,c,h):
            continue
        out.append(dict(t=ts,o=o,h=h,l=l,c=c,v=v))
    return sorted({b["t"]:b for b in out}.values(),key=lambda x:x["t"])

def ema(vals,n):
    if len(vals)<n:
        return None
    x=sum(vals[:n])/n
    for v in vals[n:]:
        x=v*2/(n+1)+x*(n-1)/(n+1)
    return x

def signal(rows,cfg):
    k=int(cfg["breakout_bars"])
    if len(rows)<max(60,k+16):
        return None
    current=rows[-1]
    prior=rows[:-1]
    avg=sum(x["v"] for x in prior[-k:])/k
    if avg<=0 or current["v"]<avg*cfg["volume_multiple"]:
        return None
    p20=ema([x["c"] for x in prior],20)
    p50=ema([x["c"] for x in prior],50)
    if p20 is None or p50 is None:
        return None
    high=max(x["h"] for x in prior[-k:])
    low=min(x["l"] for x in prior[-k:])
    c=current["c"]
    if c>high and c>p20>p50:
        side="LONG"
    elif c<low and c<p20<p50:
        side="SHORT" # Synthetic 1x directional paper exposure, not a spot-market short.
    else:
        return None
    recent=prior[-15:]
    ranges=[]
    for prev,cur in zip(recent[:-1],recent[1:]):
        ranges.append(max(cur["h"]-cur["l"],abs(cur["h"]-prev["c"]),abs(cur["l"]-prev["c"])))
    volatility=sum(ranges)/len(ranges)
    return dict(side=side,close=c,gap=max(0.008*c,volatility*cfg["stop_atr"]),
                ratio=current["v"]/avg)

def event(s,t,kind,message):
    s["events"]=(s["events"]+[dict(at=stamp(t),kind=kind,message=message)])[-60:]

def marked(s,price):
    p=s["position"]
    if not p:
        return s["cash"]
    sign=1 if p["side"]=="LONG" else -1
    return s["cash"]+p["margin"]+sign*(price-p["entry"])*p["qty"]

def enter(s,sym,sgn,ts,cfg):
    if s["paused"] or s["locked"] or s["position"]:
        return
    sign=1 if sgn["side"]=="LONG" else -1
    entry=sgn["close"]*(1+sign*cfg["slippage"])
    if entry-sign*sgn["gap"]<=0:
        return
    cost_per_unit=sgn["gap"]+entry*2*(cfg["fee"]+cfg["slippage"])
    qty=min(s["equity"]*cfg["risk_per_trade"]/cost_per_unit,
            s["equity"]*cfg["position_cap"]/entry,
            s["cash"]/(entry*(1+cfg["fee"])))
    if qty<=0:
        return
    margin=qty*entry
    entry_fee=margin*cfg["fee"]
    s["cash"]-=margin+entry_fee
    s["position"]=dict(symbol=sym,side=sgn["side"],entry=entry,qty=qty,
                       stop=entry-sign*sgn["gap"],target=entry+sign*sgn["gap"]*cfg["reward_risk"],
                       margin=margin,entry_fee=entry_fee,at=stamp(ts+3600),
                       entry_t=ts,bars=0)
    s["equity"]=marked(s,sgn["close"])
    event(s,ts+3600,"ENTRY","PAPER "+sgn["side"]+" "+sym)

def exit_trade(s,raw,ts,reason,cfg):
    p=s["position"]
    if not p:
        return
    sign=1 if p["side"]=="LONG" else -1
    px=raw*(1-sign*cfg["slippage"])
    gross=sign*(px-p["entry"])*p["qty"]
    exit_fee=px*p["qty"]*cfg["fee"]
    net=gross-p["entry_fee"]-exit_fee
    s["cash"]+=p["margin"]+gross-exit_fee
    s["trades"]=(s["trades"]+[dict(symbol=p["symbol"],side=p["side"],entry=p["entry"],
        exit=px,qty=p["qty"],entered=p["at"],exited=stamp(ts+3600),
        pnl=round(net,4),reason=reason)])[-2000:]
    s["position"]=None
    s["equity"]=s["cash"]
    event(s,ts+3600,"EXIT","PAPER "+p["side"]+" "+p["symbol"]+" "+reason)

def process_bar(s,history,ts,cfg):
    available={sym:next((b for b in reversed(rows) if b["t"]==ts),None)
               for sym,rows in history.items()}
    available={sym:b for sym,b in available.items() if b is not None}
    if not available:
        return
    day=datetime.fromtimestamp(ts,timezone.utc).date().isoformat()
    if day!=s["day"]:
        s["day"]=day
        s["day_start"]=s["equity"]
    p=s["position"]
    if p:
        if p["symbol"] not in available:
            raise RuntimeError("Missing candle for active position; simulation frozen")
        b=available[p["symbol"]]
        if ts>p["entry_t"]:
            p["bars"]+=1
            if p["side"]=="LONG":
                if b["l"]<=p["stop"]:
                    exit_trade(s,min(b["o"],p["stop"]),ts,"STOP",cfg)
                elif b["h"]>=p["target"]:
                    exit_trade(s,p["target"],ts,"TARGET",cfg)
            else:
                if b["h"]>=p["stop"]:
                    exit_trade(s,max(b["o"],p["stop"]),ts,"STOP",cfg)
                elif b["l"]<=p["target"]:
                    exit_trade(s,p["target"],ts,"TARGET",cfg)
            if s["position"] and p["bars"]>=cfg["max_hold_bars"]:
                exit_trade(s,b["c"],ts,"TIME",cfg)
    p=s["position"]
    s["equity"]=marked(s,available[p["symbol"]]["c"]) if p else s["cash"]
    s["peak"]=max(s["peak"],s["equity"])
    if not s["locked"]:
        draw=1-s["equity"]/max(0.01,s["peak"])
        daily=1-s["equity"]/max(0.01,s["day_start"])
        if draw>=cfg["total_drawdown_limit"] or daily>=cfg["daily_loss_limit"]:
            s["locked"]=True
            s["lock_reason"]="DRAWDOWN" if draw>=cfg["total_drawdown_limit"] else "DAILY LOSS"
            if s["position"]:
                pp=s["position"]
                exit_trade(s,available[pp["symbol"]]["c"],ts,"RISK LOCK",cfg)
            event(s,ts+3600,"RISK","Risk lock: "+s["lock_reason"])
    if not s["position"] and not s["paused"] and not s["locked"]:
        candidates=[]
        for sym,rows in history.items():
            if sym not in available:
                continue
            closed=[b for b in rows if b["t"]<=ts]
            sg=signal(closed,cfg)
            if sg:
                candidates.append((sg["ratio"],sym,sg))
        if candidates:
            candidates.sort(key=lambda x:(-x[0],x[1]))
            _,sym,sg=candidates[0]
            enter(s,sym,sg,ts,cfg)
    p=s["position"]
    s["equity"]=marked(s,available[p["symbol"]]["c"]) if p else s["cash"]
    s["peak"]=max(s["peak"],s["equity"])
    if not s["history"] or s["history"][-1]["t"]!=ts:
        s["history"]=(s["history"]+[dict(t=ts,equity=round(s["equity"],4))])[-2160:]
    s["last_ts"]=ts

def scan(s,cfg):
    s["last_scan"]=stamp()
    try:
        pair_names=pairs_for(cfg["symbols"])
    except Exception as e:
        s["errors"]={"API":str(e)[:250]}
        return
    history={}
    errors={}
    for sym in cfg["symbols"]:
        if sym not in pair_names:
            errors[sym]="USD market not listed on Kraken"
            continue
        try:
            b=candles(pair_names[sym])
            if len(b)<60:
                errors[sym]="Not enough completed candles"
            else:
                history[sym]=b
        except Exception as e:
            errors[sym]=str(e)[:250]
    s["errors"]=errors
    s["markets"]={}
    for sym in cfg["symbols"]:
        if sym in history:
            latest=history[sym]
            s["markets"][sym]=dict(status="READY",price=latest[-1]["c"],
                candle=stamp(latest[-1]["t"]+3600),
                signal=(signal(latest,cfg) or {}).get("side","WAIT"))
        else:
            s["markets"][sym]=dict(status="UNAVAILABLE",reason=errors.get(sym,""))
    if not history:
        return
    if s["position"] and s["position"]["symbol"] not in history:
        s["errors"]["POSITION"]="Active market missing. Simulation frozen."
        return
    latest_ts=max(rows[-1]["t"] for rows in history.values())
    s["last_data"]=stamp(latest_ts+3600)
    if s["last_ts"] is None:
        s["last_ts"]=latest_ts
        s["history"].append(dict(t=latest_ts,equity=s["equity"]))
        event(s,latest_ts+3600,"START","Initialized; no hindsight trades")
        return
    pending=sorted({b["t"] for rows in history.values() for b in rows if b["t"]>s["last_ts"]})
    if len(pending)>24:
        s["locked"]=True
        s["lock_reason"]="DATA GAP OVER 24 HOURS"
        event(s,latest_ts+3600,"RISK",s["lock_reason"])
        return
    for ts in pending:
        if s["position"] and not any(b["t"]==ts for b in history[s["position"]["symbol"]]):
            s["errors"]["POSITION"]="Active candle gap: simulation frozen"
            break
        process_bar(s,history,ts,cfg)

def save(s,cfg):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    DATA.parent.mkdir(parents=True,exist_ok=True)
    STATE.write_text(json.dumps(s,indent=2,allow_nan=False)+"\n")
    report=dict(name="TALON",mode="PAPER ONLY",status=("RISK LOCK" if s["locked"] else
        "PAUSED" if s["paused"] else "SCANNING" if s["last_ts"] is not None else "NOT STARTED"),
        updated=s["last_scan"],last_data=s["last_data"],equity=round(s["equity"],2),
        pnl=round(s["equity"]-s["initial"],2),cash=round(s["cash"],2),
        drawdown=round(100*(1-s["equity"]/max(s["peak"],0.01)),2),
        completed=len(s["trades"]),position=s["position"],markets=s["markets"],
        trades=s["trades"][-100:][::-1],history=s["history"][-500:],
        errors=s["errors"],events=s["events"][-30:][::-1],
        lock_reason=s["lock_reason"],paused=s["paused"],settings=cfg)
    DATA.write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")

def main():
    cfg=json.loads(CONFIG.read_text())
    if (STATE.exists()):
        s=json.loads(STATE.read_text())
        if s.get("mode")!="PAPER ONLY":
            raise ValueError("Refusing non-paper state")
    else:
        s=initial(cfg)
    action=sys.argv[1] if len(sys.argv)>1 else "scan"
    if action=="scan":
        scan(s,cfg)
    elif action=="pause":
        s["paused"]=True
        event(s,time.time(),"CONTROL","New entries paused")
    elif action=="resume":
        if s["locked"]:
            raise RuntimeError("Risk lock cannot be bypassed through resume")
        s["paused"]=False
        event(s,time.time(),"CONTROL","New entries resumed")
    else:
        raise ValueError("Supported: scan, pause, resume")
    save(s,cfg)
    print(json.dumps({"status":"PAPER ONLY","equity":round(s["equity"],2),
        "trades":len(s["trades"]),"errors":s["errors"],"locked":s["locked"]}))

if __name__=="__main__":
    main()
