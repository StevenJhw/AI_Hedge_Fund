"""Simple runner — bypasses the interactive CLI.

Usage:
  python run.py                          # Groq (free), default tickers
  python run.py AAPL MSFT NVDA          # Groq, custom tickers
  python run.py --deepseek              # DeepSeek V4 Flash (paid, better quality)
  python run.py --deepseek AAPL MSFT    # DeepSeek, custom tickers
  python run.py --deepseek --pro        # DeepSeek V4 Pro (best quality, slower)
"""
import sys
import argparse
sys.path.insert(0, ".")

from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv()

from src.main import run_hedge_fund
from src.utils.display import print_trading_output
from src.utils.sanitize import sanitize_decisions

# ── CLI flags ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--deepseek", action="store_true", help="Use DeepSeek instead of Groq")
parser.add_argument("--pro",      action="store_true", help="Use DeepSeek V4 Pro (default: Flash)")
args, remaining = parser.parse_known_args()

if args.deepseek:
    MODEL_NAME     = "deepseek-v4-pro" if args.pro else "deepseek-v4-flash"
    MODEL_PROVIDER = "DeepSeek"
else:
    MODEL_NAME     = "llama-3.3-70b-versatile"
    MODEL_PROVIDER = "Groq"

TICKERS = [
    # "TMF",
     "MU",
    # "AMZN",
    # "VST",
    # "NFLX",
   # "ADBE",
   # "MSFT",
]

END_DATE   = str(date.today())
START_DATE = str(date.today() - timedelta(days=365))
CASH       = 100_000.0

portfolio = {
    "cash": CASH,
    "margin_requirement": 0.0,
    "margin_used": 0.0,
    "signal_only": True,
    "positions": {t: {"long": 0, "short": 0, "long_cost_basis": 0.0,
                      "short_cost_basis": 0.0, "short_margin_used": 0.0} for t in TICKERS},
    "realized_gains": {t: {"long": 0.0, "short": 0.0} for t in TICKERS},
}

ALL_ANALYSTS = [
    # ── No LLM required (pure computation) ────────────────────────────────────
    "fundamentals_analyst",
    "technical_analyst",
    "sentiment_analyst",
    "valuation_analyst",
    # ── LLM-based investors ────────────────────────────────────────────────────
    "warren_buffett",
    "charlie_munger",
    "ben_graham",
    "peter_lynch",
    "phil_fisher",
    "bill_ackman",
    "cathie_wood",
    "michael_burry",
    "mohnish_pabrai",
    "nassim_taleb",
    "stanley_druckenmiller",
    "rakesh_jhunjhunwala",
    "aswath_damodaran",
    "market_signals_analyst",
    "macro_analyst",
    "earnings_analyst",
    "industry_analyst",
]

print(f"\n  Provider : {MODEL_PROVIDER}  |  Model : {MODEL_NAME}\n")

result = run_hedge_fund(
    tickers=TICKERS,
    start_date=START_DATE,
    end_date=END_DATE,
    portfolio=portfolio,
    show_reasoning=True,
    selected_analysts=ALL_ANALYSTS,
    model_name=MODEL_NAME,
    model_provider=MODEL_PROVIDER,
)

print_trading_output(sanitize_decisions(result))
