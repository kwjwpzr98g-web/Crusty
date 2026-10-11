# TALON | paper-only hourly scanner

Scans public Kraken USD spot-market hourly candles for BTC, ETH, SOL, BNB, and HYPE. Market pairs not offered on Kraken are explicitly marked unavailable. Uses a 20-hour breakout + 1.35x volume + 20/50 EMA check, one virtual position at a time, and virtual 1x long/short exposure. Virtual trades include estimated 0.4% fees and 0.1% slippage **per side**. No exchange API keys or real-money trading code.

## Controls
In GitHub, open **Actions → TALON paper scanner → Run workflow** and select scan, pause or resume. Scheduled scans occur hourly, best effort. Each run commits state to `talon/state.json` and the web report to `docs/`.

## Dashboard
The repository is currently private. Public GitHub Pages on personal GitHub Free requires a public repository. The generated HTML remains in `docs/index.html`, but will not have a public URL until Pages is separately enabled after confirming repository visibility. You can download the dashboard from workflow artifacts while private.

The first successful scan **initializes** candles and never backdates trades. Virtual stop/target fills are derived from hourly OHLC and are not real protective orders. Fees, slippage and data outages make actual trading results different. Historical or hypothetical results are not evidence of profitability.
