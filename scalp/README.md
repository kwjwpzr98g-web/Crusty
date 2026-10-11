# TALON SCALP (experimental, paper only)

Separate service from the existing hourly TALON simulator. Uses Kraken Spot WebSocket v2 ticker with `event_trigger: bbo` to receive best bid/ask updates as they occur, potentially multiple per second. All positions are simulated LONG spot, 1x, no leverage, no exchange keys or order APIs.

The strategy will **not** make penny moves seem profitable when fees exceed them. Default fee assumption: 0.80% taker **each side** (1.60% round trip) plus 0.02% modeled slippage each side, actual observed spread, and 0.10% desired net return. It waits for a 40-second positive move that exceeds the all-in hurdle. This may result in few or zero trades. Virtual position $250; target net 0.10%; price stop 0.5%; max hold 180 seconds; 30 second cooldown; 2% daily loss lock. Signal is an unvalidated momentum heuristic, **not a proven profitable strategy**.

Run `python app.py` with `pip install -r requirements.txt`, optionally setting `PORT` and `TALON_STATE_PATH`. Point Railway root directory at `/scalp`, attach persistent volume `/data`, use one replica, generate a domain. `/health` and `/api/status` are read-only. Public dashboard is public and has no authorization; no financial secrets or exchange credentials are used.

GitHub Actions' hourly paper bot is unchanged. Use the existing public GitHub Pages dashboard for the hourly strategy; Railway gets a separate scalp dashboard. Running continuously may exceed Railway's free trial/usage credit.
