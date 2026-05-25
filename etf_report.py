"""
ETF 수익률 리포트 — 매일 장 마감 후 텔레그램 전송

TIGER 미국S&P500 (360750) + S&P 500 지수 (^GSPC)
TIGER 미국나스닥100 (133690) + NASDAQ 100 지수 (^NDX)

비교 기간: 어제(1거래일) / 전주(5거래일) / 전달(21거래일) / 3개월(63거래일)

Usage:
  python etf_report.py
  python etf_report.py --dry-run   # 텔레그램 미전송, 터미널 출력만
"""
import argparse
import logging
import os
import sys
from datetime import datetime, timedelta

import pandas as pd
import requests
import yfinance as yf

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 설정 ──────────────────────────────────────────────────────────────────────

ETF_PAIRS = [
    {
        "etf_name":    "TIGER 미국S&P500",
        "etf_ticker":  "360750",
        "idx_ticker":  "^GSPC",
        "idx_name":    "S&P 500",
    },
    {
        "etf_name":    "TIGER 미국나스닥100",
        "etf_ticker":  "133690",
        "idx_ticker":  "^NDX",
        "idx_name":    "NASDAQ 100",
    },
]

# (레이블, 거래일 수)
PERIODS = [
    ("어제",  1),
    ("전주",  5),
    ("전달",  21),
    ("3개월", 63),
]

# 63거래일 ≈ 91 달력일 → 버퍼 포함 130일 조회
_KR_LOOKBACK_DAYS = 130
_US_PERIOD        = "6mo"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


# ── 데이터 수집 ───────────────────────────────────────────────────────────────

def fetch_kr_close(ticker: str) -> pd.Series:
    """pykrx로 KR ETF 일별 종가 시리즈 반환 (index: DatetimeIndex)."""
    try:
        from pykrx import stock as pykrx_stock
    except ImportError:
        raise ImportError("pykrx 미설치. pip install pykrx 실행 필요.")

    end_dt   = datetime.today()
    start_dt = end_dt - timedelta(days=_KR_LOOKBACK_DAYS)
    raw = pykrx_stock.get_market_ohlcv_by_date(
        start_dt.strftime("%Y%m%d"),
        end_dt.strftime("%Y%m%d"),
        ticker,
    )
    if raw.empty:
        raise ValueError(f"KR 데이터 없음: {ticker}")

    series = raw["종가"].rename(ticker)
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


def fetch_us_close(ticker: str) -> pd.Series:
    """yfinance로 US 지수 일별 종가 시리즈 반환."""
    raw = yf.download(
        ticker,
        period=_US_PERIOD,
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if raw.empty:
        raise ValueError(f"US 데이터 없음: {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.rename(ticker).sort_index()


# ── 수익률 계산 ───────────────────────────────────────────────────────────────

def calc_return(series: pd.Series, n_trading_days: int) -> float | None:
    """n 거래일 전 종가 대비 현재 종가 수익률 (%)."""
    if len(series) <= n_trading_days:
        return None
    current = float(series.iloc[-1])
    past    = float(series.iloc[-(n_trading_days + 1)])
    if past == 0:
        return None
    return (current / past - 1) * 100


# ── 메시지 포맷 ───────────────────────────────────────────────────────────────

def _pct(val: float | None) -> str:
    if val is None:
        return "   N/A  "
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def build_message(pairs: list[dict], timestamp: datetime) -> str:
    ts = timestamp.strftime("%Y년 %m월 %d일")

    lines: list[str] = [
        "📊 <b>ETF 수익률 리포트</b>",
        f"📅 {ts}",
    ]

    for pair in pairs:
        lines += ["", "━" * 24, ""]

        etf_price = pair["etf_close"]
        idx_price = pair["idx_close"]

        lines += [
            f"🇰🇷 <b>{pair['etf_name']} ({pair['etf_ticker']})</b>",
            f"   현재가: <b>{etf_price:,.0f}원</b>",
            "",
            f"🇺🇸 {pair['idx_name']} ({pair['idx_ticker']})",
            f"   현재가: <b>{idx_price:,.2f}</b>",
            "",
            "<code>기간     ETF        지수</code>",
        ]

        for label, _ in PERIODS:
            etf_r = _pct(pair["etf_returns"].get(label))
            idx_r = _pct(pair["idx_returns"].get(label))
            # 한글 2자/3자 레이블 → 공백 보정
            pad = " " if len(label) == 2 else ""
            lines.append(f"<code>{label}{pad}  {etf_r:>8}  {idx_r:>8}</code>")

    return "\n".join(lines)


# ── 텔레그램 전송 ─────────────────────────────────────────────────────────────

def send_telegram(text: str) -> bool:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정 — .env 확인 필요.")
        return False
    url = TELEGRAM_API.format(token=token)
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        logger.error(f"Telegram 전송 실패: {e}")
        return False


def send_error_telegram(error: str) -> None:
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    text = f"❌ <b>ETF 리포트 오류</b>\n<code>{error}</code>"
    try:
        requests.post(
            TELEGRAM_API.format(token=token),
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ETF 수익률 리포트")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="텔레그램 미전송, 터미널 출력만",
    )
    args = parser.parse_args()

    now = datetime.now()
    pairs: list[dict] = []

    for cfg in ETF_PAIRS:
        try:
            kr_series = fetch_kr_close(cfg["etf_ticker"])
            us_series = fetch_us_close(cfg["idx_ticker"])

            etf_returns = {label: calc_return(kr_series, n) for label, n in PERIODS}
            idx_returns = {label: calc_return(us_series, n) for label, n in PERIODS}

            pairs.append({
                "etf_name":    cfg["etf_name"],
                "etf_ticker":  cfg["etf_ticker"],
                "idx_ticker":  cfg["idx_ticker"],
                "idx_name":    cfg["idx_name"],
                "etf_close":   float(kr_series.iloc[-1]),
                "idx_close":   float(us_series.iloc[-1]),
                "etf_returns": etf_returns,
                "idx_returns": idx_returns,
            })
            logger.info(f"[{cfg['etf_name']}] 데이터 수집 완료")
        except Exception as e:
            logger.error(f"[{cfg['etf_name']}] 수집 오류: {e}")

    if not pairs:
        logger.error("수집된 데이터 없음 — 전송 취소")
        send_error_telegram("ETF 데이터를 하나도 수집하지 못했습니다.")
        sys.exit(1)

    msg = build_message(pairs, now)
    print(msg)

    if args.dry_run:
        logger.info("[dry-run] 텔레그램 전송 건너뜀")
        return

    if send_telegram(msg):
        logger.info("Telegram 전송 완료")
    else:
        logger.error("Telegram 전송 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
