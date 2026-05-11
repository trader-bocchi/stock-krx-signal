"""
Squeeze Momentum Signal System — Main Entry Point

Usage:
  python main.py --market us --mode backtest
  python main.py --market kr --mode backtest
  python main.py --market us --mode scan
  python main.py --market us --mode notify             # 스캔 + Telegram 전송 (US: 4H+1D)
  python main.py --market kr --mode notify             # 스캔 + Telegram 전송 (KR: 4H미지원+1D)
  python main.py --market both --mode notify           # US + KR 각각 별도 메시지 전송
  python main.py --market both --mode notify --as_of 2026-04-30  # 과거 날짜 기준 재현
  python main.py --market us --mode walkforward
  python main.py --mode test_telegram                  # Telegram 연결 테스트
"""
import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

# Windows 콘솔 UTF-8 출력 보장
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# .env 자동 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv 미설치 시 환경변수를 직접 설정

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.data.cache_manager import CacheManager
from src.data.us_provider import USDataProvider
from src.data.kr_provider import KRDataProvider
from src.indicators.squeeze import SqueezeDetector
from src.signals.engine import SignalEngine
from src.backtest.engine import BacktestEngine
from src.backtest.walk_forward import WalkForwardValidator
from src.scanner.universe import UniverseManager
from src.ranking.edge_analyzer import EdgeAnalyzer
from src.visualization.charts import SignalChart
from src.visualization.reports import PerformanceReport
from src.notifications.telegram import TelegramNotifier, SignalAlert

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_pipeline(cfg: Config):
    """Instantiate all components from config."""
    s = cfg.strategy
    b = cfg.backtest

    cache = CacheManager(
        cache_dir=cfg.data.get("cache_dir", "data/cache"),
        expiry_hours=cfg.data.get("cache_expiry_hours", 12),
    )

    squeeze_detector = SqueezeDetector(
        bb_period=s.get("bb_period", 20),
        bb_std=s.get("bb_std", 2.0),
        kc_period=s.get("kc_period", 20),
        kc_atr_mult=s.get("kc_atr_mult", 1.5),
        kc_atr_period=s.get("atr_period", 14),
        momentum_period=s.get("momentum_period", 12),
        volume_ma_period=s.get("volume_ma_period", 20),
        volume_multiplier=s.get("volume_multiplier", 1.2),
        min_squeeze_bars=s.get("min_squeeze_bars", 3),
    )

    signal_engine = SignalEngine(
        squeeze_detector=squeeze_detector,
        use_volume_filter=s.get("use_volume_filter", True),
        use_trend_filter=s.get("use_trend_filter", True),
        trend_ema_period=s.get("trend_ema_period", 50),
        signal_window_bars=s.get("signal_window_bars", 1),
    )

    backtest_engine = BacktestEngine(
        initial_capital=b.get("initial_capital", 100_000_000),
        commission=b.get("commission", 0.0025),
        slippage=b.get("slippage", 0.001),
        position_size=b.get("position_size", 0.1),
        stop_loss=b.get("stop_loss", 0.05),
        take_profit=b.get("take_profit", None),
    )

    return cache, signal_engine, backtest_engine


def run_backtest(market: str, cfg: Config):
    cache, signal_engine, backtest_engine = build_pipeline(cfg)
    universe = UniverseManager()
    period = cfg.data.get("default_period", "2y")

    if market == "us":
        provider = USDataProvider(cache)
        tickers = universe.get_us_tickers()
    else:
        provider = KRDataProvider(cache)
        tickers = universe.get_kr_tickers()

    logger.info(f"Fetching data for {len(tickers)} {market.upper()} tickers…")
    raw_data = provider.fetch_multiple(tickers, period=period)
    filtered_data = universe.filter_by_liquidity(raw_data, market=market)

    metrics_map = {}
    chart = SignalChart()

    for ticker, df in filtered_data.items():
        try:
            signal_data = signal_engine.generate(df)
            metrics = backtest_engine.run(signal_data, ticker=ticker)
            metrics_map[ticker] = metrics
            chart.plot(signal_data, ticker=ticker)
            logger.info(
                f"[{ticker}] CAGR={metrics.cagr*100:.1f}%  "
                f"Sharpe={metrics.sharpe:.2f}  "
                f"MDD={metrics.max_drawdown*100:.1f}%  "
                f"Trades={metrics.total_trades}"
            )
        except Exception as e:
            logger.warning(f"[{ticker}] Error: {e}")

    analyzer = EdgeAnalyzer()
    ranking = analyzer.rank(metrics_map)
    analyzer.print_report(ranking)

    report = PerformanceReport()
    csv_path = report.save_ranking_csv(ranking, filename=f"ranking_{market}.csv")
    report.plot_ranking_bar(ranking, metric="sharpe")
    logger.info(f"Ranking saved to {csv_path}")

    for ticker in ranking.head(5)["ticker"].tolist():
        if ticker in metrics_map:
            report.plot_equity_curve(metrics_map[ticker])


def run_walkforward(market: str, cfg: Config):
    cache, signal_engine, backtest_engine = build_pipeline(cfg)
    universe = UniverseManager()
    period = cfg.data.get("default_period", "2y")
    wf_cfg = cfg.walk_forward

    if market == "us":
        provider = USDataProvider(cache)
        tickers = universe.get_us_tickers()
    else:
        provider = KRDataProvider(cache)
        tickers = universe.get_kr_tickers()

    validator = WalkForwardValidator(
        backtest_engine=backtest_engine,
        n_splits=wf_cfg.get("n_splits", 5),
        in_sample_ratio=wf_cfg.get("in_sample_ratio", 0.7),
    )

    raw_data = provider.fetch_multiple(tickers, period=period)
    filtered_data = universe.filter_by_liquidity(raw_data, market=market)

    rows = []
    for ticker, df in filtered_data.items():
        try:
            signal_data = signal_engine.generate(df)
            result = validator.validate(signal_data, ticker=ticker)
            rows.append({
                "ticker": ticker,
                "avg_oos_sharpe": round(result.avg_oos_sharpe, 3),
                "avg_oos_cagr": round(result.avg_oos_cagr * 100, 2),
                "n_folds": len(result.folds),
            })
        except Exception as e:
            logger.warning(f"[{ticker}] WF error: {e}")

    if rows:
        import pandas as pd
        wf_df = pd.DataFrame(rows).sort_values("avg_oos_sharpe", ascending=False)
        print("\n=== Walk-Forward OOS Results ===")
        print(wf_df.to_string(index=False))
        wf_df.to_csv(f"data/results/walkforward_{market}.csv", index=False)


def _alerts_from_raw_data(
    raw_data: dict,
    market: str,
    signal_engine,
    sector_map: dict,
    now: datetime,
) -> list[SignalAlert]:
    """pre-fetched raw_data dict → SignalAlert 목록."""
    alerts: list[SignalAlert] = []
    for ticker, df in raw_data.items():
        try:
            data = signal_engine.generate(df)
            if data.empty:
                continue

            last = data.iloc[-1]
            close         = float(last["close"])
            momentum      = float(last.get("momentum", 0) or 0)
            momentum_prev = float(last.get("momentum_prev", 0) or 0)
            squeeze_bars  = int(last.get("squeeze_bars", 0) or 0)

            _vol_ratio = last.get("vol_ratio", 1.0)
            vol_ratio  = float(_vol_ratio) if pd.notna(_vol_ratio) else 1.0

            _bb_pct = last.get("bb_pct", 0.5)
            bb_pct  = float(_bb_pct) if pd.notna(_bb_pct) else 0.5

            sector        = sector_map.get(ticker, "")

            kwargs = dict(
                ticker=ticker,
                market=market.upper(),
                close=close,
                momentum=momentum,
                momentum_prev=momentum_prev,
                squeeze_bars=squeeze_bars,
                vol_ratio=vol_ratio,
                bb_pct=bb_pct,
                sector=sector,
                timestamp=now,
            )

            # scan_entry/scan_exit: 현재 봉(N) 기준 → 다음 봉(N+1) 시가에 진입/청산
            # long_signal/exit_signal은 백테스트 실행 타이밍용 (N-1봉 조건, 이미 지난 시그널)
            if last.get("scan_entry", False):
                alerts.append(SignalAlert(signal_type="ENTRY", **kwargs))
            elif last.get("scan_exit", False):
                alerts.append(SignalAlert(signal_type="EXIT", **kwargs))
            elif last.get("squeeze_on", False) and squeeze_bars >= 3:
                alerts.append(SignalAlert(signal_type="SQUEEZE_FORMING", **kwargs))

        except Exception as e:
            logger.warning(f"[{ticker}] 시그널 수집 오류: {e}")

    return alerts


def _collect_signals(
    market: str,
    cfg: Config,
    end_date: Optional[str] = None,
) -> list[SignalAlert]:
    """
    1D 봉 기준으로 시장 스캔 → SignalAlert 목록 반환.
    end_date: 'YYYY-MM-DD' 형식 — 해당 날짜 기준 과거 시그널 재현 (기본: 오늘)
    """
    cache, signal_engine, _ = build_pipeline(cfg)
    universe = UniverseManager()

    if market == "us":
        provider = USDataProvider(cache)
        tickers = universe.get_us_tickers()
        sector_map = _build_sector_map_us()
    else:
        provider = KRDataProvider(cache)
        tickers = universe.get_kr_tickers()
        sector_map = _build_sector_map_kr()

    raw_data = provider.fetch_multiple(tickers, period="6mo", end_date=end_date)
    now = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    alerts = _alerts_from_raw_data(raw_data, market, signal_engine, sector_map, now)
    logger.info(f"[{market.upper()} 1D] 시그널 수집 완료: {len(alerts)}건")
    return alerts


def _collect_signals_4h(
    market: str,
    cfg: Config,
    end_date: Optional[str] = None,
) -> list[SignalAlert]:
    """
    4H 봉 기준 스캔 → SignalAlert 목록 반환.
    현재는 US만 지원 (pykrx는 일봉 전용).
    end_date: 'YYYY-MM-DD' 형식 — 해당 날짜 기준 과거 시그널 재현 (기본: 오늘)
    """
    if market != "us":
        return []

    cache, signal_engine, _ = build_pipeline(cfg)
    universe = UniverseManager()
    provider = USDataProvider(cache)
    tickers = universe.get_us_tickers()
    sector_map = _build_sector_map_us()

    raw_data = provider.fetch_multiple_4h(tickers, lookback_days=59, end_date=end_date)
    now = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    alerts = _alerts_from_raw_data(raw_data, market, signal_engine, sector_map, now)
    logger.info(f"[US 4H] 시그널 수집 완료: {len(alerts)}건")
    return alerts


def _build_sector_map_us() -> dict[str, str]:
    return {
        "NVDA": "AI반도체", "META": "AI/빅테크", "GOOGL": "AI/빅테크",
        "PLTR": "AI소프트웨어", "MSFT": "AI/빅테크",
        "AVGO": "AI반도체", "AMD": "AI반도체", "ARM": "AI반도체",
        "ASML": "반도체장비", "TSM": "파운드리",
        "AAPL": "빅테크", "AMZN": "빅테크",
    }


def _build_sector_map_kr() -> dict[str, str]:
    return {
        "000660": "반도체",
        "005930": "반도체",
        "012450": "방산",
        "034020": "원전",
        "005380": "자동차",
        "006800": "금융",
    }


def run_scan(market: str, cfg: Config):
    """터미널 출력 전용 스캔 (Telegram 미전송)."""
    alerts = _collect_signals(market, cfg)

    print(f"\n=== Squeeze Momentum Scan [{market.upper()}] ===")
    if not alerts:
        print("  활성 시그널 없음.")
        return

    for a in alerts:
        print(
            f"  [{a.signal_type:16s}] {a.ticker:10s}  "
            f"close={a.close:>12,.2f}  "
            f"mom={a.momentum:+.4f}  "
            f"sqz={a.squeeze_bars}봉"
        )


def run_notify(market: str, cfg: Config, end_date: Optional[str] = None):
    """스캔 후 Telegram 전송.

    US / KR 각각 별도 메시지로 전송.
    각 메시지 안에 4H 섹션 + 1D 섹션이 포함됨 (send_combined).
    KR 4H는 pykrx 미지원이므로 항상 빈 목록으로 처리.
    end_date: 'YYYY-MM-DD' — 해당 날짜 기준 과거 시그널 재현 (기본: 오늘)
    """
    notifier = TelegramNotifier()
    markets = ["us", "kr"] if market == "both" else [market]
    now = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    for mkt in markets:
        try:
            alerts_4h = _collect_signals_4h(mkt, cfg, end_date=end_date)  # KR은 항상 []
            alerts_1d = _collect_signals(mkt, cfg, end_date=end_date)
            total = len(alerts_4h) + len(alerts_1d)

            # 시그널 유무와 관계없이 항상 4H+1D 두 섹션이 포함된 메시지 전송
            success = notifier.send_combined(alerts_4h, alerts_1d, timestamp=now, market=mkt)

            if success:
                logger.info(f"[{mkt.upper()}] Telegram 전송 완료 ({total}건)")
            else:
                logger.error(f"[{mkt.upper()}] Telegram 전송 실패")
        except Exception as e:
            logger.error(f"[{mkt.upper()}] 알림 오류: {e}")
            notifier.send_error(context=f"시장: {mkt.upper()}", error=str(e))


def run_test_telegram():
    """Telegram 연결 테스트."""
    notifier = TelegramNotifier()
    if notifier.test():
        print("✅ Telegram 연결 성공")
    else:
        print("❌ Telegram 연결 실패 — .env 파일의 BOT_TOKEN, CHAT_ID를 확인하세요.")


def main():
    parser = argparse.ArgumentParser(description="Squeeze Momentum Signal System")
    parser.add_argument(
        "--market",
        choices=["us", "kr", "both"],
        default="us",
    )
    parser.add_argument(
        "--mode",
        choices=["backtest", "scan", "notify", "walkforward", "test_telegram"],
        default="backtest",
    )
    parser.add_argument("--config", default="config/settings.yaml")
    parser.add_argument(
        "--as_of",
        default=None,
        metavar="YYYY-MM-DD",
        help="과거 특정 날짜 기준 시그널 재현 (예: 2026-04-30). 기본값: 오늘",
    )
    args = parser.parse_args()

    cfg = Config(args.config)

    if args.mode == "backtest":
        if args.market == "both":
            run_backtest("us", cfg)
            run_backtest("kr", cfg)
        else:
            run_backtest(args.market, cfg)
    elif args.mode == "scan":
        if args.market == "both":
            run_scan("us", cfg)
            run_scan("kr", cfg)
        else:
            run_scan(args.market, cfg)
    elif args.mode == "notify":
        run_notify(args.market, cfg, end_date=args.as_of)
    elif args.mode == "walkforward":
        if args.market == "both":
            run_walkforward("us", cfg)
            run_walkforward("kr", cfg)
        else:
            run_walkforward(args.market, cfg)
    elif args.mode == "test_telegram":
        run_test_telegram()


if __name__ == "__main__":
    main()
