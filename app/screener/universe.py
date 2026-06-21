"""Stock universe fetcher: S&P 500 + Nasdaq 100 union with 24h cache.

Data sources (priority order):
1. GitHub CSV (datasets/s-and-p-500-companies) — daily auto-updated
2. NASDAQ Screener API — official, no key needed
3. Hardcoded fallback — last resort
"""

import logging
import time
from io import StringIO

import pandas as pd
import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

_sp500_cache: dict = {"symbols": [], "ts": 0.0}
_ndx100_cache: dict = {"symbols": [], "ts": 0.0}

# ═══════════════════════════════════════════════════════════════
# GitHub CSV Sources (most reliable for cloud servers)
# ═══════════════════════════════════════════════════════════════

_GITHUB_SP500_URLS = [
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
    "https://raw.githubusercontent.com/Ate329/top-us-stock-tickers/main/tickers/sp500.csv",
]

_GITHUB_NDX100_URLS = [
    "https://raw.githubusercontent.com/Ate329/top-us-stock-tickers/main/tickers/nasdaq100.csv",
]


def _normalize_symbol(sym: str) -> str:
    """Normalize ticker for yfinance: BRK.B -> BRK-B"""
    return sym.strip().replace(".", "-")


def _fetch_csv_symbols(urls: list[str], symbol_col_candidates: list[str]) -> list[str] | None:
    """Try fetching symbols from GitHub CSV URLs (first success wins)."""
    for url in urls:
        try:
            resp = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15, follow_redirects=True)
            resp.raise_for_status()
            df = pd.read_csv(StringIO(resp.text))
            # Find the symbol/ticker column
            for col_name in symbol_col_candidates:
                matched = [c for c in df.columns if c.lower().strip() == col_name.lower()]
                if matched:
                    symbols = [_normalize_symbol(str(s)) for s in df[matched[0]].dropna().tolist() if str(s).strip()]
                    if len(symbols) > 50:  # sanity check
                        logger.info(f"Fetched {len(symbols)} symbols from {url}")
                        return symbols
        except Exception as e:
            logger.debug(f"Failed to fetch from {url}: {e}")
            continue
    return None


# ═══════════════════════════════════════════════════════════════
# NASDAQ Official API (backup)
# ═══════════════════════════════════════════════════════════════

def _fetch_from_nasdaq_api(index: str = "sp500") -> list[str] | None:
    """Fetch from NASDAQ screener API. index: 'sp500' or 'nasdaq100'."""
    try:
        # NASDAQ API provides all traded stocks; we filter by index membership isn't directly
        # available, but we can get top stocks by market cap as a proxy for Nasdaq-100
        if index == "nasdaq100":
            url = "https://api.nasdaq.com/api/quote/list-type/nasdaq100"
        else:
            url = "https://api.nasdaq.com/api/quote/list-type/sp500"

        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        }
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()

        # Navigate response structure
        rows = data.get("data", {}).get("data", {}).get("rows", [])
        if not rows:
            # Alternative structure
            rows = data.get("data", {}).get("rows", [])
        if not rows:
            return None

        symbols = [_normalize_symbol(r.get("symbol", "")) for r in rows if r.get("symbol")]
        if len(symbols) > 50:
            logger.info(f"Fetched {len(symbols)} symbols from NASDAQ API ({index})")
            return symbols
    except Exception as e:
        logger.debug(f"NASDAQ API failed for {index}: {e}")
    return None


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

def get_sp500_symbols() -> list[str]:
    """Fetch S&P 500 constituent symbols (cached 24h).

    Priority: GitHub CSV → NASDAQ API → fallback
    """
    now = time.time()
    if _sp500_cache["symbols"] and (now - _sp500_cache["ts"]) < _CACHE_TTL:
        return _sp500_cache["symbols"]

    # Try GitHub CSV first
    symbols = _fetch_csv_symbols(_GITHUB_SP500_URLS, ["symbol", "ticker"])
    if symbols:
        _sp500_cache["symbols"] = symbols
        _sp500_cache["ts"] = now
        return symbols

    # Try NASDAQ API
    symbols = _fetch_from_nasdaq_api("sp500")
    if symbols:
        _sp500_cache["symbols"] = symbols
        _sp500_cache["ts"] = now
        return symbols

    # Fallback
    logger.warning("All S&P 500 sources failed, using fallback list")
    if _sp500_cache["symbols"]:
        return _sp500_cache["symbols"]
    return _SP500_FALLBACK.copy()


def get_ndx100_symbols() -> list[str]:
    """Fetch Nasdaq 100 constituent symbols (cached 24h).

    Priority: GitHub CSV → NASDAQ API → fallback
    """
    now = time.time()
    if _ndx100_cache["symbols"] and (now - _ndx100_cache["ts"]) < _CACHE_TTL:
        return _ndx100_cache["symbols"]

    # Try GitHub CSV first
    symbols = _fetch_csv_symbols(_GITHUB_NDX100_URLS, ["symbol", "ticker"])
    if symbols:
        _ndx100_cache["symbols"] = symbols
        _ndx100_cache["ts"] = now
        return symbols

    # Try NASDAQ API
    symbols = _fetch_from_nasdaq_api("nasdaq100")
    if symbols:
        _ndx100_cache["symbols"] = symbols
        _ndx100_cache["ts"] = now
        return symbols

    # Fallback
    logger.warning("All Nasdaq 100 sources failed, using fallback list")
    if _ndx100_cache["symbols"]:
        return _ndx100_cache["symbols"]
    return _NDX100_FALLBACK.copy()


def get_universe() -> list[str]:
    """Get the full stock universe: S&P 500 + Nasdaq 100 union (deduplicated)."""
    sp500 = get_sp500_symbols()
    ndx100 = get_ndx100_symbols()
    merged = sorted(set(sp500) | set(ndx100))
    logger.info(f"Stock universe: {len(sp500)} S&P500 + {len(ndx100)} NDX100 = {len(merged)} unique")
    return merged


# ═══════════════════════════════════════════════════════════════
# Fallback lists (used only if ALL online sources fail)
# ═══════════════════════════════════════════════════════════════

_NDX100_FALLBACK = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "ARM", "ASML", "AVGO", "AZN", "BIIB", "BKNG", "BKR", "CCEP",
    "CDNS", "CDW", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP",
    "CSX", "CTAS", "CTSH", "DASH", "DDOG", "DLTR", "DXCM", "EA", "EXC", "FANG",
    "FAST", "FTNT", "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "ILMN",
    "INTC", "INTU", "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU", "MAR",
    "MCHP", "MDB", "MDLZ", "MELI", "META", "MNST", "MRNA", "MRVL", "MSFT", "MU",
    "NFLX", "NVDA", "NXPI", "ODFL", "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD",
    "PEP", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SMCI", "SNDK", "SNPS",
    "TEAM", "TMUS", "TSLA", "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "ZS",
]

_SP500_FALLBACK = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE",
    "AEP", "AES", "AFL", "AIG", "AIZ", "AJG", "AKAM", "ALB", "ALGN", "ALK",
    "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME", "AMGN", "AMP", "AMT", "AMZN",
    "ANET", "ANSS", "AON", "AOS", "APA", "APD", "APH", "APTV", "ARE", "ATO",
    "ATVI", "AVB", "AVGO", "AVY", "AWK", "AXP", "AZO", "BA", "BAC", "BAX",
    "BBWI", "BBY", "BDX", "BEN", "BF-B", "BIO", "BK", "BKNG", "BKR", "BLK",
    "BMY", "BR", "BRK-B", "BRO", "BSX", "BWA", "BXP", "C", "CAG", "CAH",
    "CARR", "CAT", "CB", "CBOE", "CBRE", "CCI", "CCL", "CDAY", "CDNS", "CDW",
    "CE", "CEG", "CF", "CFG", "CHD", "CHRW", "CHTR", "CI", "CINF", "CL",
    "CLX", "CMA", "CMCSA", "CME", "CMG", "CMI", "CMS", "CNC", "CNP", "COF",
    "COO", "COP", "COST", "CPAY", "CPB", "CPRT", "CPT", "CRL", "CRM", "CSCO",
    "CSGP", "CSX", "CTAS", "CTLT", "CTRA", "CTSH", "CTVA", "CVS", "CVX", "CZR",
    "D", "DAL", "DD", "DE", "DFS", "DG", "DGX", "DHI", "DHR", "DIS",
    "DISH", "DLR", "DLTR", "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK", "DVA",
    "DVN", "DXC", "DXCM", "EA", "EBAY", "ECL", "ED", "EFX", "EIX", "EL",
    "EMN", "EMR", "ENPH", "EOG", "EPAM", "EQIX", "EQR", "EQT", "ES", "ESS",
    "ETN", "ETR", "ETSY", "EVRG", "EW", "EXC", "EXPD", "EXPE", "EXR", "F",
    "FANG", "FAST", "FBHS", "FCX", "FDS", "FDX", "FE", "FFIV", "FIS", "FISV",
    "FITB", "FLT", "FMC", "FOX", "FOXA", "FRC", "FRT", "FTNT", "FTV", "GD",
    "GE", "GEHC", "GEN", "GILD", "GIS", "GL", "GLW", "GM", "GNRC", "GOOG",
    "GOOGL", "GPC", "GPN", "GRMN", "GS", "GWW", "HAL", "HAS", "HBAN", "HCA",
    "HD", "HOLX", "HON", "HPE", "HPQ", "HRL", "HSIC", "HST", "HSY", "HUM",
    "HWM", "IBM", "ICE", "IDXX", "IEX", "IFF", "ILMN", "INCY", "INTC", "INTU",
    "INVH", "IP", "IPG", "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ",
    "J", "JBHT", "JCI", "JKHY", "JNJ", "JNPR", "JPM", "K", "KDP", "KEY",
    "KEYS", "KHC", "KIM", "KLAC", "KMB", "KMI", "KMX", "KO", "KR", "L",
    "LDOS", "LEN", "LH", "LHX", "LIN", "LKQ", "LLY", "LMT", "LNC", "LNT",
    "LOW", "LRCX", "LULU", "LUV", "LVS", "LW", "LYB", "LYV", "MA", "MAA",
    "MAR", "MAS", "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MET", "META",
    "MGM", "MHK", "MKC", "MKTX", "MLM", "MMC", "MMM", "MNST", "MO", "MOH",
    "MOS", "MPC", "MPWR", "MRK", "MRNA", "MRO", "MS", "MSCI", "MSFT", "MSI",
    "MTB", "MTCH", "MTD", "MU", "NCLH", "NDAQ", "NDSN", "NEE", "NEM", "NFLX",
    "NI", "NKE", "NOC", "NOW", "NRG", "NSC", "NTAP", "NTRS", "NUE", "NVDA",
    "NVR", "NWL", "NWS", "NWSA", "NXPI", "O", "ODFL", "OGN", "OKE", "OMC",
    "ON", "ORCL", "ORLY", "OTIS", "OXY", "PARA", "PAYC", "PAYX", "PCAR", "PCG",
    "PEAK", "PEG", "PEP", "PFE", "PFG", "PG", "PGR", "PH", "PHM", "PKG",
    "PKI", "PLD", "PM", "PNC", "PNR", "PNW", "POOL", "PPG", "PPL", "PRU",
    "PSA", "PSX", "PTC", "PVH", "PWR", "PXD", "PYPL", "QCOM", "QRVO", "RCL",
    "RE", "REG", "REGN", "RF", "RHI", "RJF", "RL", "RMD", "ROK", "ROL",
    "ROP", "ROST", "RSG", "RTX", "RVTY", "SBAC", "SBNY", "SBUX", "SCHW", "SEE",
    "SHW", "SIVB", "SJM", "SLB", "SNA", "SNDK", "SNPS", "SO", "SPG", "SPGI", "SRE",
    "STE", "STT", "STX", "STZ", "SWK", "SWKS", "SYF", "SYK", "SYY", "T",
    "TAP", "TDG", "TDY", "TECH", "TEL", "TER", "TFC", "TFX", "TGT", "TMO",
    "TMUS", "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TT",
    "TTWO", "TXN", "TXT", "TYL", "UAL", "UDR", "UHS", "ULTA", "UNH", "UNP",
    "UPS", "URI", "USB", "V", "VFC", "VICI", "VLO", "VMC", "VRSK", "VRSN",
    "VRTX", "VTR", "VTRS", "VZ", "WAB", "WAT", "WBA", "WBD", "WDC", "WEC",
    "WELL", "WFC", "WHR", "WM", "WMB", "WMT", "WRB", "WRK", "WST", "WTW",
    "WY", "WYNN", "XEL", "XOM", "XRAY", "XYL", "YUM", "ZBH", "ZBRA", "ZION", "ZTS",
]
