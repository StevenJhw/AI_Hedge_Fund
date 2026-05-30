"""Robinhood portfolio analysis — fetches real holdings and gives AI recommendations.

Usage:
  python run_rh.py              # Groq (free)
  python run_rh.py --deepseek   # DeepSeek V4 Flash (paid, better quality)
  python run_rh.py --deepseek --pro  # DeepSeek V4 Pro
"""
import sys
import argparse
sys.path.insert(0, ".")

import os
from datetime import date, timedelta
from dotenv import load_dotenv
load_dotenv()

import textwrap
import robin_stocks.robinhood as rh
from colorama import Fore, Style, init
from pydantic import BaseModel, Field
from src.main import run_hedge_fund
from src.utils.display import print_trading_output
from src.utils.sanitize import sanitize_decisions
from src.utils.llm import call_llm

init(autoreset=True)

# ── CLI flags ──────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--deepseek", action="store_true")
parser.add_argument("--pro",      action="store_true")
args, _ = parser.parse_known_args()

if args.deepseek:
    MODEL_NAME     = "deepseek-v4-pro" if args.pro else "deepseek-v4-flash"
    MODEL_PROVIDER = "DeepSeek"
else:
    MODEL_NAME     = "llama-3.3-70b-versatile"
    MODEL_PROVIDER = "Groq"

# ── Config ─────────────────────────────────────────────────────────────────────
END_DATE   = str(date.today())
START_DATE = str(date.today() - timedelta(days=365))
ANALYSTS = [
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

# ── Helpers ────────────────────────────────────────────────────────────────────

_NON_LLM_AGENTS = {
    "fundamentals_analyst_agent", "technical_analyst_agent", "sentiment_analyst_agent",
    "valuation_analyst_agent", "market_signals_analyst_agent", "macro_analyst_agent",
    "earnings_analyst_agent", "industry_analyst_agent",
}

def make_portfolio(tickers: list[str], cash: float, positions: dict | None = None) -> dict:
    pos_data = {}
    for t in tickers:
        real = (positions or {}).get(t, {})
        pos_data[t] = {
            "long":             real.get("long", 0),
            "short":            0,
            "long_cost_basis":  real.get("long_cost_basis", 0.0),
            "short_cost_basis": 0.0,
            "short_margin_used":0.0,
        }
    return {
        "cash":               cash,
        "signal_only":        True,   # pure signal mode — consistent with run.py
        "margin_requirement": 0.0,
        "margin_used":        0.0,
        "positions":          pos_data,
        "realized_gains":     {t: {"long": 0.0, "short": 0.0} for t in tickers},
    }


def run_section(tickers: list[str], cash: float, positions: dict | None = None) -> dict | None:
    if not tickers:
        print("\n[!] No tickers found, skipping.\n")
        return None

    result = run_hedge_fund(
        tickers=tickers,
        start_date=START_DATE,
        end_date=END_DATE,
        portfolio=make_portfolio(tickers, cash, positions),
        show_reasoning=True,
        selected_analysts=ANALYSTS,
        model_name=MODEL_NAME,
        model_provider=MODEL_PROVIDER,
    )
    sanitized = sanitize_decisions(result)
    print_trading_output(sanitized)
    return sanitized


# ── Robinhood ──────────────────────────────────────────────────────────────────

def get_robinhood_account() -> tuple[list[str], float, dict]:
    username = os.getenv("ROBINHOOD_USERNAME")
    password = os.getenv("ROBINHOOD_PASSWORD")
    totp     = os.getenv("ROBINHOOD_TOTP_SECRET")

    print(f"\n{Fore.CYAN}[Robinhood] Logging in as {username}...{Style.RESET_ALL}")
    if totp:
        import pyotp
        rh.login(username, password, mfa_code=pyotp.TOTP(totp).now())
    else:
        rh.login(username, password)

    profile      = rh.load_account_profile()
    portfolio_profile = rh.load_portfolio_profile()

    # Use actual portfolio equity from portfolio profile (buying_power is inflated on margin accounts)
    actual_equity = float(
        portfolio_profile.get("equity") or
        portfolio_profile.get("extended_hours_equity") or
        0.0
    )

    raw_positions = rh.get_open_stock_positions()
    tickers   = []
    positions = {}

    print(f"{Fore.GREEN}[Robinhood] Fetching positions...{Style.RESET_ALL}")
    for p in raw_positions:
        qty = float(p.get("quantity", 0))
        if qty < 0.01:
            continue
        rh_symbol = rh.get_symbol_by_url(p["instrument"])
        if not rh_symbol:
            continue
        rh_symbol = rh_symbol.upper()
        yf_symbol = rh_symbol.replace(".", "-")

        avg_cost   = float(p.get("clearing_average_cost") or p.get("average_buy_price") or 0)
        cost_basis = float(p.get("clearing_cost_basis") or qty * avg_cost)

        # Use Robinhood's own equity field — exact match to what the app shows
        mkt_value  = float(p.get("equity") or p.get("market_value") or 0.0)
        if mkt_value == 0.0:
            # fallback: fetch live price only if equity field is missing
            try:
                quote     = rh.get_latest_price(rh_symbol)
                price     = float(quote[0]) if (quote and quote[0] is not None) else 0.0
                mkt_value = qty * price
            except Exception:
                mkt_value = 0.0
        unrealized = mkt_value - cost_basis

        positions[yf_symbol] = {
            "long":            round(qty, 4),
            "long_cost_basis": avg_cost,
            "market_value":    round(mkt_value, 2),
            "unrealized_pnl":  round(unrealized, 2),
            "unrealized_pct":  round((unrealized / cost_basis * 100) if cost_basis else 0, 2),
        }
        tickers.append(yf_symbol)

    rh.logout()

    total_mkt = sum(v["market_value"] for v in positions.values())
    total_pnl = sum(v["unrealized_pnl"] for v in positions.values())

    # Use actual equity from portfolio profile; derive true cash from it
    equity        = actual_equity if actual_equity > 0 else total_mkt
    cash          = max(0.0, equity - total_mkt)   # uninvested cash = equity - stock value
    buying_power  = cash                            # expose as cash for downstream use

    print(f"\n{'─'*52}")
    print(f"  {'ROBINHOOD ACCOUNT SNAPSHOT':^50}")
    print(f"{'─'*52}")
    print(f"  Total Equity    : {Fore.GREEN}${equity:>12,.2f}{Style.RESET_ALL}")
    print(f"  Stock Value     : ${total_mkt:>12,.2f}")
    print(f"  Cash            : {Fore.YELLOW}${cash:>12,.2f}{Style.RESET_ALL}")
    pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
    pnl_str   = f"+${total_pnl:,.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):,.2f}"
    print(f"  Unrealized P&L  : {pnl_color}{pnl_str}{Style.RESET_ALL}")
    print(f"{'─'*52}")
    print(f"  {'Ticker':<8} {'Shares':>6}  {'Avg Cost':>10}  {'Mkt Val':>12}  {'P&L':>10}  {'P&L%':>7}")
    print(f"  {'─'*6:<8} {'─'*6:>6}  {'─'*10:>10}  {'─'*12:>12}  {'─'*10:>10}  {'─'*7:>7}")
    for sym, v in sorted(positions.items(), key=lambda x: -x[1]["market_value"]):
        pnl_s = f"+${v['unrealized_pnl']:,.2f}" if v['unrealized_pnl'] >= 0 else f"-${abs(v['unrealized_pnl']):,.2f}"
        color = Fore.GREEN if v['unrealized_pnl'] >= 0 else Fore.RED
        shares_str = f"{v['long']:.4f}".rstrip("0").rstrip(".")
        print(f"  {sym:<8} {shares_str:>8}  ${v['long_cost_basis']:>9,.2f}  ${v['market_value']:>11,.2f}  "
              f"{color}{pnl_s:>10}  {v['unrealized_pct']:>+6.2f}%{Style.RESET_ALL}")
    print(f"{'─'*52}\n")

    return tickers, buying_power, positions


# ── Final summary paragraph ────────────────────────────────────────────────────

def print_final_summary(result: dict, positions: dict, buying_power: float) -> None:
    decisions       = result.get("decisions") or {}
    analyst_signals = result.get("analyst_signals") or {}

    buys  = []
    sells = []
    holds = []

    for ticker, dec in decisions.items():
        action = (dec.get("action") or "hold").upper()
        conf   = dec.get("confidence") or 0

        # only count LLM investor agents (consistent with portfolio_manager.py)
        bull = bear = 0
        for agent_id, agent_signals in analyst_signals.items():
            if "risk_management" in agent_id or agent_id in _NON_LLM_AGENTS:
                continue
            sig = (agent_signals.get(ticker) or {}).get("signal", "neutral")
            if sig == "bullish":  bull += 1
            elif sig == "bearish": bear += 1

        entry = (ticker, action, conf, bull, bear)
        if action == "BUY":    buys.append(entry)
        elif action == "SELL": sells.append(entry)
        else:                  holds.append(entry)

    total_mkt     = sum(v["market_value"] for v in positions.values())
    total_pnl     = sum(v["unrealized_pnl"] for v in positions.values())
    equity        = total_mkt + buying_power
    pnl_sign      = "+" if total_pnl >= 0 else ""
    total_pnl_pct = (total_pnl / (equity - total_pnl) * 100) if (equity - total_pnl) != 0 else 0

    width = 66
    print("\n" + "=" * width)
    print(f"  {Fore.CYAN + Style.BRIGHT}PORTFOLIO SUMMARY & RECOMMENDATIONS{Style.RESET_ALL}")
    print("=" * width)

    pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
    print(f"\n  Equity: {Fore.GREEN}${equity:,.2f}{Style.RESET_ALL}  |  "
          f"Cash: {Fore.YELLOW}${buying_power:,.2f}{Style.RESET_ALL}  |  "
          f"P&L: {pnl_color}{pnl_sign}${abs(total_pnl):,.2f} ({pnl_sign}{total_pnl_pct:.1f}%){Style.RESET_ALL}")

    def fmt(entries):
        return ", ".join(
            f"{Fore.CYAN}{t}{Style.RESET_ALL} ({c:.0f}% conf, {b}B/{br}Br)"
            for t, _, c, b, br in entries
        ) or "none"

    print(f"\n  {Fore.GREEN}BUY :{Style.RESET_ALL} {fmt(buys)}")
    print(f"  {Fore.RED}SELL:{Style.RESET_ALL} {fmt(sells)}")
    print(f"  {Fore.YELLOW}HOLD:{Style.RESET_ALL} {', '.join(t for t,*_ in holds) or 'none'}")

    # Show LLM narrative per ticker
    print(f"\n  {Fore.WHITE + Style.BRIGHT}AI Analysis per position:{Style.RESET_ALL}")
    for ticker, dec in decisions.items():
        action    = (dec.get("action") or "hold").upper()
        narrative = dec.get("narrative", "")
        action_color = {"BUY": Fore.GREEN, "SELL": Fore.RED, "HOLD": Fore.YELLOW}.get(action, Fore.WHITE)
        print(f"\n  {Fore.CYAN}{ticker}{Style.RESET_ALL} — {action_color}{action}{Style.RESET_ALL} "
              f"({dec.get('confidence', 0):.1f}% conf)")
        if narrative:
            for line in textwrap.wrap(narrative, width=62):
                print(f"    {line}")

    print("\n" + "=" * width + "\n")


# ── Risk & Position Sizing Agent ──────────────────────────────────────────────

class _PositionRec(BaseModel):
    recommended_pct: float = Field(default=0.0, description="Target allocation % of total equity")
    rationale:       str   = Field(default="")

class _RiskReport(BaseModel):
    risk_score:  float = Field(default=5.0, description="Portfolio risk 1(safe)–10(dangerous)")
    assessment:  str   = Field(default="")
    positions:   dict  = Field(default_factory=dict)   # ticker → {recommended_pct, rationale}
    rebalancing: list  = Field(default_factory=list)   # top 3-5 priority actions (strings)
    cash_advice: str   = Field(default="")
    strategy:    str   = Field(default="")


def print_risk_position_analysis(
    result: dict,
    positions: dict,
    buying_power: float,
) -> None:
    decisions = result.get("decisions") or {}
    if not decisions or not positions:
        return

    total_mkt = sum(v["market_value"] for v in positions.values())
    equity    = total_mkt + buying_power
    cash_pct  = buying_power / equity * 100 if equity else 0

    # ── Python pre-computes all numbers — LLM receives exact values, never calculates ──
    pos_stats = {}   # ticker → {cur_pct, mkt_value, pnl_pct, ai_action, ai_conf}
    for ticker, v in positions.items():
        dec = decisions.get(ticker, {})
        pos_stats[ticker] = {
            "cur_pct":   round(v["market_value"] / equity * 100, 2) if equity else 0,
            "mkt_value": round(v["market_value"], 2),
            "pnl_pct":   v["unrealized_pct"],
            "ai_action": (dec.get("action") or "hold").upper(),
            "ai_conf":   dec.get("confidence") or 0,
        }

    # Build prompt table with Python-computed values
    pos_lines = []
    for ticker, s in sorted(pos_stats.items(), key=lambda x: -x[1]["mkt_value"]):
        pos_lines.append(
            f"  {ticker:<8}  current_pct={s['cur_pct']:.2f}%  "
            f"pnl={s['pnl_pct']:+.1f}%  "
            f"ai_signal={s['ai_action']} ({s['ai_conf']:.0f}% conf)  "
            f"mkt=${s['mkt_value']:,.0f}"
        )

    narrative_lines = []
    for ticker, dec in decisions.items():
        narrative = dec.get("narrative", "")
        if narrative:
            narrative_lines.append(f"  [{ticker}] {narrative}")

    prompt = (
        f"You are a professional portfolio risk manager and position sizing specialist.\n"
        f"Your goal: maximise long-term risk-adjusted returns through disciplined sizing and diversification.\n\n"
        f"PORTFOLIO OVERVIEW (calculated by Python — these numbers are exact):\n"
        f"  Total Equity  : ${equity:,.2f}\n"
        f"  Cash          : ${buying_power:,.2f} = {cash_pct:.2f}% of equity\n"
        f"  Invested      : ${total_mkt:,.2f} = {100-cash_pct:.2f}% of equity\n"
        f"  # Positions   : {len(positions)}\n\n"
        f"CURRENT POSITIONS — all percentages are Python-computed from actual market values:\n"
        f"  (ticker | current_pct | unrealized_pnl% | ai_signal | market_value)\n"
        + "\n".join(pos_lines) + "\n\n"
        f"AI RESEARCH NARRATIVE PER POSITION:\n"
        + ("\n".join(narrative_lines) if narrative_lines else "  (none)") + "\n\n"
        "TASK: Decide the recommended_pct (target allocation %) for each ticker.\n\n"
        "SIZING RULES — follow strictly in order:\n"
        "  1. AI signal is the primary driver:\n"
        "       SELL signal  → reduce or exit (recommended_pct <= current_pct)\n"
        "       BUY  signal  → may increase (subject to 20% cap)\n"
        "       HOLD signal  → keep near current_pct\n"
        "  2. No single position > 20% of equity\n"
        "  3. Size convictions by AI confidence: higher conf BUY → larger allocation\n"
        "  4. Do NOT increase a position whose ai_signal is SELL — even for diversification\n\n"
        "CALCULATION INSTRUCTIONS — follow these steps like running Python code:\n"
        "  Step 1: List every ticker with its current_pct (use the exact values above, do not round differently)\n"
        "  Step 2: For each ticker, assign recommended_pct strictly following the AI signal rules above\n"
        "  Step 3: Compute target_cash_pct = 100 - sum(all recommended_pct values)\n"
        "  Step 4: Verify sum(recommended_pct) + target_cash_pct == 100.0 exactly\n"
        "  Step 5: For each rebalancing step, write: '<TICKER> current_pct% → recommended_pct%'\n"
        "          using the EXACT current_pct values from the table above — never invent or round them\n\n"
        "Only return recommended_pct and rationale per position — Python will compute delta and action.\n\n"
        "Return JSON only:\n"
        "{\n"
        '  "risk_score": <float 1-10>,\n'
        '  "assessment": "<2-3 sentences>",\n'
        '  "positions": {\n'
        '    "TICKER": {"recommended_pct": <float>, "rationale": "<one sentence>"}\n'
        '  },\n'
        '  "rebalancing": ["<TICKER> <exact_current_pct>% → <recommended_pct>% — reason", ...],\n'
        '  "cash_advice": "<state: target_cash_pct = 100 - sum(recommended_pct) = X%, then explain why>",\n'
        '  "strategy": "<2-3 sentences>"\n'
        "}"
    )

    state = {"metadata": {"model_name": MODEL_NAME, "model_provider": MODEL_PROVIDER}}
    report = call_llm(
        prompt,
        pydantic_model=_RiskReport,
        agent_name="risk_position_agent",
        state=state,
        default_factory=_RiskReport,
    )

    # ── Display ────────────────────────────────────────────────────────────────
    width = 66
    print("\n" + "=" * width)
    print(f"  {Fore.RED + Style.BRIGHT}RISK & POSITION SIZING ANALYSIS{Style.RESET_ALL}")
    print("=" * width)

    score      = report.risk_score
    score_color = Fore.GREEN if score <= 3 else Fore.YELLOW if score <= 6 else Fore.RED
    print(f"\n  Risk Score : {score_color}{Style.BRIGHT}{score:.1f}/10{Style.RESET_ALL}")
    if report.assessment:
        for line in textwrap.wrap(report.assessment, width=62):
            print(f"  {line}")

    # Position sizing table
    if report.positions:
        print(f"\n  {Fore.WHITE + Style.BRIGHT}Position Sizing Recommendations:{Style.RESET_ALL}")
        print(f"  {'Ticker':<8}  {'Current%':>8}  {'Target%':>8}  {'Action':<10}  Rationale")
        print(f"  {'─'*6:<8}  {'─'*8:>8}  {'─'*7:>8}  {'─'*8:<10}  {'─'*30}")
        for ticker, rec in report.positions.items():
            if isinstance(rec, dict):
                rec_pct   = rec.get("recommended_pct", 0)
                rationale = rec.get("rationale", "")
            else:
                rec_pct   = getattr(rec, "recommended_pct", 0)
                rationale = getattr(rec, "rationale", "")

            # cur_pct from Python's pre-computed stats — never recalculate from LLM data
            cur_pct = pos_stats.get(ticker, {}).get("cur_pct", 0)
            delta   = rec_pct - cur_pct

            # Derive action purely from delta — ignore LLM's text to avoid contradictions
            if rec_pct == 0 and cur_pct > 0.05:
                action = "exit"
            elif delta > 0.5:
                action = "increase"
            elif delta < -0.5:
                action = "reduce"
            else:
                action = "hold"

            act_color = (Fore.GREEN if action == "increase"
                         else Fore.RED if action in ("reduce", "exit")
                         else Fore.YELLOW)
            delta_str = f"{delta:+.1f}%"
            print(f"  {Fore.CYAN}{ticker:<8}{Style.RESET_ALL}  "
                  f"{cur_pct:>7.1f}%  "
                  f"{rec_pct:>7.1f}% {delta_str:>7}  "
                  f"{act_color}{action:<10}{Style.RESET_ALL}  "
                  f"{rationale[:45]}")

    # Rebalancing priorities
    if report.rebalancing:
        print(f"\n  {Fore.WHITE + Style.BRIGHT}Priority Actions:{Style.RESET_ALL}")
        for i, action in enumerate(report.rebalancing, 1):
            print(f"  {Fore.YELLOW}{i}.{Style.RESET_ALL} {action}")

    # Cash advice
    if report.cash_advice:
        print(f"\n  {Fore.WHITE + Style.BRIGHT}Cash Strategy:{Style.RESET_ALL}")
        for line in textwrap.wrap(report.cash_advice, width=62):
            print(f"  {Fore.YELLOW}{line}{Style.RESET_ALL}")

    # Long-term strategy
    if report.strategy:
        print(f"\n  {Fore.WHITE + Style.BRIGHT}Long-term Strategy:{Style.RESET_ALL}")
        for line in textwrap.wrap(report.strategy, width=62):
            print(f"  {Fore.CYAN}{line}{Style.RESET_ALL}")

    print("\n" + "=" * width + "\n")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    rh_tickers, buying_power, rh_positions = get_robinhood_account()
    result = run_section(rh_tickers, cash=buying_power, positions=rh_positions)
    if result:
        print_final_summary(result, rh_positions, buying_power)
        print_risk_position_analysis(result, rh_positions, buying_power)
