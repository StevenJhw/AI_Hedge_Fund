"""Analyst configuration — all available agents."""

from src.agents.market_signals import market_signals_analyst_agent
from src.agents.macro import macro_analyst_agent
from src.agents.earnings import earnings_analyst_agent
from src.agents.industry import industry_analyst_agent
from src.agents.warren_buffett import warren_buffett_agent
from src.agents.fundamentals import fundamentals_analyst_agent
from src.agents.technicals import technical_analyst_agent
from src.agents.sentiment import sentiment_analyst_agent
from src.agents.valuation import valuation_analyst_agent
from src.agents.aswath_damodaran import aswath_damodaran_agent
from src.agents.ben_graham import ben_graham_agent
from src.agents.bill_ackman import bill_ackman_agent
from src.agents.cathie_wood import cathie_wood_agent
from src.agents.charlie_munger import charlie_munger_agent
from src.agents.michael_burry import michael_burry_agent
from src.agents.mohnish_pabrai import mohnish_pabrai_agent
from src.agents.nassim_taleb import nassim_taleb_agent
from src.agents.peter_lynch import peter_lynch_agent
from src.agents.phil_fisher import phil_fisher_agent
from src.agents.rakesh_jhunjhunwala import rakesh_jhunjhunwala_agent
from src.agents.stanley_druckenmiller import stanley_druckenmiller_agent

# horizon: "short" = days-weeks, "medium" = months-quarters, "long" = 1+ years
ANALYST_CONFIG = {
    "warren_buffett": {
        "display_name": "Warren Buffett",
        "description": "The Oracle of Omaha",
        "investing_style": "Value investing with focus on moat, management quality, and margin of safety.",
        "agent_func": warren_buffett_agent,
        "order": 0,
        "horizon": "long",
    },
    "charlie_munger": {
        "display_name": "Charlie Munger",
        "description": "Buffett's partner",
        "investing_style": "Buys wonderful businesses at fair prices using multidisciplinary thinking.",
        "agent_func": charlie_munger_agent,
        "order": 1,
        "horizon": "long",
    },
    "ben_graham": {
        "display_name": "Ben Graham",
        "description": "Godfather of value investing",
        "investing_style": "Deep value — only buys hidden gems with a wide margin of safety.",
        "agent_func": ben_graham_agent,
        "order": 2,
        "horizon": "long",
    },
    "peter_lynch": {
        "display_name": "Peter Lynch",
        "description": "Practical ten-bagger hunter",
        "investing_style": "Seeks fast-growing companies in everyday businesses.",
        "agent_func": peter_lynch_agent,
        "order": 3,
        "horizon": "medium",
    },
    "phil_fisher": {
        "display_name": "Phil Fisher",
        "description": "Deep growth research",
        "investing_style": "Meticulous scuttlebutt research on long-term growth potential.",
        "agent_func": phil_fisher_agent,
        "order": 4,
        "horizon": "long",
    },
    "bill_ackman": {
        "display_name": "Bill Ackman",
        "description": "Activist investor",
        "investing_style": "Takes bold concentrated positions and pushes for change.",
        "agent_func": bill_ackman_agent,
        "order": 5,
        "horizon": "medium",
    },
    "cathie_wood": {
        "display_name": "Cathie Wood",
        "description": "Queen of growth / innovation",
        "investing_style": "Invests in disruptive innovation and exponential growth themes.",
        "agent_func": cathie_wood_agent,
        "order": 6,
        "horizon": "long",
    },
    "michael_burry": {
        "display_name": "Michael Burry",
        "description": "The Big Short contrarian",
        "investing_style": "Deep-value contrarian hunting for heavily discounted businesses.",
        "agent_func": michael_burry_agent,
        "order": 7,
        "horizon": "medium",
    },
    "mohnish_pabrai": {
        "display_name": "Mohnish Pabrai",
        "description": "Dhandho investor",
        "investing_style": "Heads I win, tails I don't lose much — low-risk doubles.",
        "agent_func": mohnish_pabrai_agent,
        "order": 8,
        "horizon": "long",
    },
    "nassim_taleb": {
        "display_name": "Nassim Taleb",
        "description": "Black Swan risk analyst",
        "investing_style": "Tail-risk focus, antifragility, and asymmetric payoffs.",
        "agent_func": nassim_taleb_agent,
        "order": 9,
        "horizon": "short",
    },
    "stanley_druckenmiller": {
        "display_name": "Stanley Druckenmiller",
        "description": "Macro legend",
        "investing_style": "Hunts asymmetric macro opportunities with growth potential.",
        "agent_func": stanley_druckenmiller_agent,
        "order": 10,
        "horizon": "medium",
    },
    "rakesh_jhunjhunwala": {
        "display_name": "Rakesh Jhunjhunwala",
        "description": "The Big Bull of India",
        "investing_style": "Long-term growth bets on India-facing and global leaders.",
        "agent_func": rakesh_jhunjhunwala_agent,
        "order": 11,
        "horizon": "long",
    },
    "aswath_damodaran": {
        "display_name": "Aswath Damodaran",
        "description": "Dean of Valuation",
        "investing_style": "Story + numbers: rigorous DCF and narrative-driven valuation.",
        "agent_func": aswath_damodaran_agent,
        "order": 12,
        "horizon": "long",
    },
    "fundamentals_analyst": {
        "display_name": "Fundamentals Analyst",
        "description": "Financial Statement Specialist",
        "investing_style": "Scores profitability, growth, financial health, and valuation ratios.",
        "agent_func": fundamentals_analyst_agent,
        "order": 13,
        "horizon": "medium",
    },
    "technical_analyst": {
        "display_name": "Technical Analyst",
        "description": "Chart Pattern Specialist",
        "investing_style": "Trend, momentum, mean-reversion, and volatility signals from price data.",
        "agent_func": technical_analyst_agent,
        "order": 14,
        "horizon": "short",
    },
    "sentiment_analyst": {
        "display_name": "Sentiment Analyst",
        "description": "Insider & News Sentiment",
        "investing_style": "Combines insider-trade direction (30%) and news headline sentiment (70%).",
        "agent_func": sentiment_analyst_agent,
        "order": 15,
        "horizon": "short",
    },
    "valuation_analyst": {
        "display_name": "Valuation Analyst",
        "description": "Multi-Method Valuation",
        "investing_style": "DCF, owner earnings, EV/EBITDA, and residual income models.",
        "agent_func": valuation_analyst_agent,
        "order": 16,
        "horizon": "long",
    },
    "market_signals_analyst": {
        "display_name": "Market Signals Analyst",
        "description": "Options, Short Interest & Analyst Ratings",
        "investing_style": "Put/call ratio, short interest, and Wall Street consensus ratings.",
        "agent_func": market_signals_analyst_agent,
        "order": 17,
        "horizon": "short",
    },
    "macro_analyst": {
        "display_name": "Macro Analyst",
        "description": "Treasury Yield Curve",
        "investing_style": "US yield curve shape and rate environment as a macro risk signal.",
        "agent_func": macro_analyst_agent,
        "order": 18,
        "horizon": "medium",
    },
    "earnings_analyst": {
        "display_name": "Earnings Analyst",
        "description": "Beat Rate & Forward Estimates",
        "investing_style": "Historical earnings beat rate, forward EPS/revenue growth, and upcoming catalysts.",
        "agent_func": earnings_analyst_agent,
        "order": 19,
        "horizon": "short",
    },
    "industry_analyst": {
        "display_name": "Industry Analyst",
        "description": "Sector Momentum & Themes",
        "investing_style": "Industry tailwinds, AI/thematic exposure, and sector-level growth prospects.",
        "agent_func": industry_analyst_agent,
        "order": 20,
        "horizon": "long",
    },
}

ANALYST_ORDER = [
    (config["display_name"], key)
    for key, config in sorted(ANALYST_CONFIG.items(), key=lambda x: x[1]["order"])
]

# horizon lookup: agent_id (with _agent suffix) → horizon
AGENT_HORIZON: dict[str, str] = {
    f"{key}_agent": config["horizon"]
    for key, config in ANALYST_CONFIG.items()
}


def get_analyst_nodes() -> dict:
    return {
        key: (f"{key}_agent", config["agent_func"])
        for key, config in ANALYST_CONFIG.items()
    }


def get_agents_list() -> list:
    return [
        {
            "key": key,
            "display_name": config["display_name"],
            "description": config["description"],
            "investing_style": config["investing_style"],
            "order": config["order"],
            "horizon": config["horizon"],
        }
        for key, config in sorted(ANALYST_CONFIG.items(), key=lambda x: x[1]["order"])
    ]
