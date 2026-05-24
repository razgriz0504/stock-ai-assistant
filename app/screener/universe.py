"""Stock universe fetcher: S&P 500 + Nasdaq 100 union with 24h cache."""

import logging
import time
from io import StringIO
from typing import Optional

import pandas as pd
import httpx

logger = logging.getLogger(__name__)

_CACHE_TTL = 86400  # 24 hours
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

_sp500_cache: dict = {"symbols": [], "ts": 0.0}
_ndx100_cache: dict = {"symbols": [], "ts": 0.0}


def _fetch_wiki_html(url: str) -> str:
    """Fetch Wikipedia HTML with proper User-Agent."""
    resp = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def _normalize_symbol(sym: str) -> str:
    """Normalize ticker for yfinance: BRK.B -> BRK-B"""
    return sym.strip().replace(".", "-")


def get_sp500_symbols() -> list[str]:
    """Fetch S&P 500 constituent symbols from Wikipedia (cached 24h)."""
    now = time.time()
    if _sp500_cache["symbols"] and (now - _sp500_cache["ts"]) < _CACHE_TTL:
        return _sp500_cache["symbols"]

    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        html = _fetch_wiki_html(url)
        tables = pd.read_html(StringIO(html))
        df = tables[0]
        symbols = [_normalize_symbol(s) for s in df["Symbol"].tolist()]
        _sp500_cache["symbols"] = symbols
        _sp500_cache["ts"] = now
        logger.info(f"Fetched {len(symbols)} S&P 500 symbols from Wikipedia")
        return symbols
    except Exception as e:
        logger.warning(f"Failed to fetch S&P 500 list from Wikipedia: {e}, using fallback")
        if _sp500_cache["symbols"]:
            return _sp500_cache["symbols"]
        return _SP500_FALLBACK.copy()


def get_ndx100_symbols() -> list[str]:
    """Fetch Nasdaq 100 constituent symbols from Wikipedia (cached 24h)."""
    now = time.time()
    if _ndx100_cache["symbols"] and (now - _ndx100_cache["ts"]) < _CACHE_TTL:
        return _ndx100_cache["symbols"]

    try:
        url = "https://en.wikipedia.org/wiki/Nasdaq-100"
        html = _fetch_wiki_html(url)
        tables = pd.read_html(StringIO(html))
        # The components table has a "Ticker" or "Symbol" column
        df = None
        for t in tables:
            cols = [c.lower() for c in t.columns]
            if "ticker" in cols:
                df = t
                col_name = t.columns[cols.index("ticker")]
                break
            elif "symbol" in cols:
                df = t
                col_name = t.columns[cols.index("symbol")]
                break
        if df is None:
            raise ValueError("Could not find Nasdaq-100 components table")
        symbols = [_normalize_symbol(s) for s in df[col_name].tolist()]
        _ndx100_cache["symbols"] = symbols
        _ndx100_cache["ts"] = now
        logger.info(f"Fetched {len(symbols)} Nasdaq 100 symbols from Wikipedia")
        return symbols
    except Exception as e:
        logger.warning(f"Failed to fetch Nasdaq 100 list from Wikipedia: {e}, using fallback")
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
# Fallback lists (top holdings, used if Wikipedia is unreachable)
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
    "PEP", "PYPL", "QCOM", "REGN", "ROP", "ROST", "SBUX", "SMCI", "SNPS", "TEAM",
    "TMUS", "TSLA", "TTD", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "ZS",
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
    "SHW", "SIVB", "SJM", "SLB", "SNA", "SNPS", "SO", "SPG", "SPGI", "SRE",
    "STE", "STT", "STX", "STZ", "SWK", "SWKS", "SYF", "SYK", "SYY", "T",
    "TAP", "TDG", "TDY", "TECH", "TEL", "TER", "TFC", "TFX", "TGT", "TMO",
    "TMUS", "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TT",
    "TTWO", "TXN", "TXT", "TYL", "UAL", "UDR", "UHS", "ULTA", "UNH", "UNP",
    "UPS", "URI", "USB", "V", "VFC", "VICI", "VLO", "VMC", "VRSK", "VRSN",
    "VRTX", "VTR", "VTRS", "VZ", "WAB", "WAT", "WBA", "WBD", "WDC", "WEC",
    "WELL", "WFC", "WHR", "WM", "WMB", "WMT", "WRB", "WRK", "WST", "WTW",
    "WY", "WYNN", "XEL", "XOM", "XRAY", "XYL", "YUM", "ZBH", "ZBRA", "ZION", "ZTS",
]
