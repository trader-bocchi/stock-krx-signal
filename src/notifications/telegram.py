import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


@dataclass
class SignalAlert:
    ticker: str
    market: str           # "US" | "KR"
    signal_type: str      # "ENTRY" | "EXIT" | "SQUEEZE_FORMING"
    close: float
    momentum: float
    momentum_prev: float
    squeeze_bars: int
    vol_ratio: float      # 현재거래량 / MA
    bb_pct: float         # BB 내 위치 (0~1)
    sector: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


class TelegramNotifier:
    """
    참조: trader-bocchi/cyrpto-upbit-signal 메시지 포맷 기준
    - 개별 시그널: send_signal() — 지표값, 추세, 거래량 상세 포함
    - 배치 요약:  send_summary() — BUY / SELL / SQUEEZE 그룹별 정리
    - 시그널 없음: send_no_signal()
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
    ):
        self.bot_token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        if not self.bot_token or not self.chat_id:
            logger.warning(
                "TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정. .env 확인 필요."
            )

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token) and bool(self.chat_id)

    # ── 저수준 API ────────────────────────────────────────────

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            logger.warning("Telegram 미설정 — 전송 건너뜀.")
            return False
        url = TELEGRAM_API.format(token=self.bot_token, method="sendMessage")
        try:
            resp = requests.post(
                url,
                json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error(f"Telegram 전송 실패: {e}")
            return False

    # ── 포맷 헬퍼 ────────────────────────────────────────────

    @staticmethod
    def _price_str(alert: SignalAlert) -> str:
        """시장에 맞는 가격 포맷."""
        if alert.market == "US":
            return f"${alert.close:,.2f}"
        return f"{alert.close:,.0f} KRW"

    @staticmethod
    def _flag(market: str) -> str:
        return "🇺🇸" if market == "US" else "🇰🇷"

    @staticmethod
    def _mom_direction(alert: SignalAlert) -> str:
        diff = alert.momentum - alert.momentum_prev
        if diff > 0:
            return "▲ 상승 (가속 중)"
        return "▼ 하락 (감속 중)"

    @staticmethod
    def _vol_str(vol_ratio: float) -> str:
        mark = "✅" if vol_ratio >= 1.2 else "⚠️"
        return f"{vol_ratio:.1f}x MA {mark}"

    @staticmethod
    def _bb_position(bb_pct: float) -> str:
        """BB 내 위치를 텍스트로."""
        if bb_pct >= 0.8:
            return f"상단 근접 ({bb_pct:.2f}) ⚠️"
        if bb_pct >= 0.5:
            return f"중상단 ({bb_pct:.2f}) ✅"
        if bb_pct >= 0.2:
            return f"중하단 ({bb_pct:.2f})"
        return f"하단 근접 ({bb_pct:.2f}) 🔴"

    # ── 개별 시그널 메시지 ────────────────────────────────────

    def format_entry(self, a: SignalAlert) -> str:
        flag = self._flag(a.market)
        ts = a.timestamp.strftime("%Y-%m-%d %H:%M")
        mom_sign = "+" if a.momentum > 0 else ""
        prev_sign = "+" if a.momentum_prev > 0 else ""

        lines = [
            f"✅ <b>BUY SIGNAL [1D] {a.ticker}</b> {flag}",
            "",
            f"⏰ 시간 (KST): {ts}",
            f"💰 현재가: <b>{self._price_str(a)}</b>",
            "   (진입가는 다음 캔들 시가 기준)",
            "",
            "📊 <b>Squeeze Momentum 지표:</b>",
            f"   모멘텀: {mom_sign}{a.momentum:.4f}",
            f"   직전 모멘텀: {prev_sign}{a.momentum_prev:.4f}",
            f"   방향: {self._mom_direction(a)}",
            f"   스퀴즈 지속: {a.squeeze_bars}봉 후 해제",
            "",
            "📈 <b>추세 분석:</b>",
            f"   BB 위치: {self._bb_position(a.bb_pct)}",
            f"   거래량 비율: {self._vol_str(a.vol_ratio)}",
        ]
        if a.sector:
            lines += ["", f"💹 섹터: {a.sector}"]
        return "\n".join(lines)

    def format_exit(self, a: SignalAlert) -> str:
        flag = self._flag(a.market)
        ts = a.timestamp.strftime("%Y-%m-%d %H:%M")
        mom_sign = "+" if a.momentum > 0 else ""

        lines = [
            f"🟥 <b>SELL SIGNAL [1D] {a.ticker}</b> {flag}",
            "",
            f"⏰ 시간 (KST): {ts}",
            f"💰 현재가: <b>{self._price_str(a)}</b>",
            "",
            "📊 <b>청산 사유:</b>",
            f"   모멘텀 반전: {mom_sign}{a.momentum:.4f}",
            f"   방향: {self._mom_direction(a)}",
            "",
            f"💹 거래량 비율: {self._vol_str(a.vol_ratio)}",
        ]
        if a.sector:
            lines += [f"   섹터: {a.sector}"]
        return "\n".join(lines)

    def send_signal(self, alert: SignalAlert) -> bool:
        """개별 시그널 전송 (BUY / SELL)."""
        if alert.signal_type == "ENTRY":
            text = self.format_entry(alert)
        elif alert.signal_type == "EXIT":
            text = self.format_exit(alert)
        else:
            return False  # SQUEEZE_FORMING은 배치 요약에만 포함
        return self.send_message(text)

    # ── 배치 요약 메시지 ─────────────────────────────────────

    # ── 국가+섹터 그룹 헬퍼 ──────────────────────────────────

    @staticmethod
    def _group_by_country_sector(
        alerts: list[SignalAlert],
    ) -> dict[tuple[str, str], list[SignalAlert]]:
        """
        alerts → {(flag, sector): [alert, ...]} 순서 보존 dict
        flag 예: "🇺🇸", "🇰🇷"
        sector 예: "AI반도체", "빅테크"
        """
        groups: dict[tuple[str, str], list[SignalAlert]] = {}
        for a in alerts:
            flag   = "🇺🇸" if a.market == "US" else "🇰🇷"
            sector = a.sector if a.sector else "기타"
            key    = (flag, sector)
            groups.setdefault(key, []).append(a)
        return groups

    def _signal_block(
        self,
        alerts: list[SignalAlert],
        show_squeeze_bars: bool = False,
    ) -> list[str]:
        """
        국가/섹터별로 묶은 종목 블록 반환.
        시그널이 없는 국가 항목은 '시그널 없음'으로 표기.
        """
        if not alerts:
            return ["  • 시그널 없음"]

        groups = self._group_by_country_sector(alerts)
        lines: list[str] = []
        for (flag, sector), group in groups.items():
            lines.append(f"{flag} {sector}")
            for a in group:
                sqz = f"  {a.squeeze_bars}봉" if show_squeeze_bars else ""
                lines.append(f"• {a.ticker}  {self._price_str(a)}{sqz}")
        return lines

    # ── 배치 요약 메시지 ─────────────────────────────────────

    def send_summary(
        self,
        alerts: list[SignalAlert],
        interval_label: str = "일봉 캔들",
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """
        포맷 예시:
          ⏰ 시그널 시점: 2026년 05월 10일 18시 07분
          📊 캔들 기준: 4시간 캔들

          ✅ BUY SIGNAL

          🇺🇸 AI반도체
          • NVDA  $1,092.50

          🇰🇷 반도체
          • 시그널 없음

          🔴 SELL SIGNAL
          ...
        """
        ts = (timestamp or datetime.now()).strftime("%Y년 %m월 %d일 %H시 %M분")

        entries = [a for a in alerts if a.signal_type == "ENTRY"]
        exits   = [a for a in alerts if a.signal_type == "EXIT"]
        forming = [a for a in alerts if a.signal_type == "SQUEEZE_FORMING"]

        lines: list[str] = [
            f"⏰ 시그널 시점: {ts}",
            f"📊 캔들 기준: {interval_label}",
            "",
            "✅ <b>BUY SIGNAL</b>",
            "",
        ]
        lines.extend(self._signal_block(entries))
        lines += ["", "🔴 <b>SELL SIGNAL</b>", ""]
        lines.extend(self._signal_block(exits))
        lines += ["", "🟡 <b>SQUEEZE 형성 중</b>", ""]
        lines.extend(self._signal_block(forming, show_squeeze_bars=True))

        return self.send_message("\n".join(lines))

    def send_combined(
        self,
        alerts_4h: list[SignalAlert],
        alerts_1d: list[SignalAlert],
        timestamp: Optional[datetime] = None,
        market: Optional[str] = None,   # "US" | "KR"
    ) -> bool:
        """4시간 + 1일 두 타임프레임을 하나의 메시지로 전송."""
        ts = (timestamp or datetime.now()).strftime("%Y년 %m월 %d일 %H시 %M분")

        _MARKET_HEADER = {
            "US": "🇺🇸 <b>미국 시장 (US)</b>",
            "KR": "🇰🇷 <b>한국 시장 (KR)</b>",
        }

        def section(label: str, alerts: list[SignalAlert]) -> list[str]:
            entries = [a for a in alerts if a.signal_type == "ENTRY"]
            exits   = [a for a in alerts if a.signal_type == "EXIT"]
            forming = [a for a in alerts if a.signal_type == "SQUEEZE_FORMING"]
            blk = [
                f"📊 <b>{label}</b>",
                "",
                "✅ <b>BUY SIGNAL</b>",
                "",
            ]
            blk.extend(self._signal_block(entries))
            blk += ["", "🔴 <b>SELL SIGNAL</b>", ""]
            blk.extend(self._signal_block(exits))
            blk += ["", "🟡 <b>SQUEEZE 형성 중</b>", ""]
            blk.extend(self._signal_block(forming, show_squeeze_bars=True))
            return blk

        lines = []
        if market and market.upper() in _MARKET_HEADER:
            lines += [_MARKET_HEADER[market.upper()], ""]
        lines += [f"⏰ 시그널 시점: {ts}", ""]
        lines.extend(section("4시간 캔들", alerts_4h))
        lines += ["", "━" * 20, ""]
        lines.extend(section("1일 캔들", alerts_1d))

        return self.send_message("\n".join(lines))

    def send_no_signal(self, market: str) -> bool:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = (
            f"📭 <b>시그널 없음</b>\n\n"
            f"📊 캔들 기준: 일봉 (1D)\n"
            f"📅 스캔 시점: {ts}"
        )
        return self.send_message(text)

    def send_error(self, context: str, error: str) -> bool:
        text = f"❌ <b>오류 발생</b>\n{context}\n<code>{error}</code>"
        return self.send_message(text)

    def test(self) -> bool:
        return self.send_message(
            "✅ <b>Squeeze Momentum Bot</b>\n연결 테스트 성공!"
        )
