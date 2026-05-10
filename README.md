# stock-krx-signal

BB/KC Squeeze Momentum 전략 기반 한국/미국 주식 시그널 시스템

## 전략 개요

LazyBear Squeeze Momentum 지표를 기반으로 BB(볼린저밴드)가 KC(켈트너채널) 안에 갇히는 스퀴즈 구간을 포착하고, 해제 시 모멘텀 방향으로 진입 신호를 생성합니다.

- **ENTRY**: 스퀴즈 해제 + 모멘텀 양수 + 상승 중
- **EXIT**: 모멘텀 양수 → 음수 크로스다운
- **SQUEEZE_FORMING**: 스퀴즈 진행 중 (3봉 이상)

## 종목 구성

**한국 (KRX / pykrx)**
| 종목코드 | 종목명 | 섹터 |
|---------|--------|------|
| 000660 | SK하이닉스 | 반도체 |
| 005930 | 삼성전자 | 반도체 |
| 012450 | 한화에어로스페이스 | 방산 |
| 034020 | 두산에너빌리티 | 원전 |
| 005380 | 현대자동차 | 자동차 |
| 006800 | 미래에셋증권 | 금융 |

**미국 (yfinance)**
| 섹터 | 종목 |
|------|------|
| AI반도체 | NVDA, AVGO, AMD, ARM |
| AI/빅테크 | META, GOOGL, MSFT |
| 반도체장비/파운드리 | ASML, TSM |
| 빅테크 | AAPL, AMZN |
| AI소프트웨어 | PLTR |

## 데이터 소스

| 시장 | 라이브러리 | 지원 타임프레임 |
|------|-----------|----------------|
| 미국 | yfinance | 4H (1H 리샘플링), 1D |
| 한국 | pykrx (KRX) | 1D |

> KR 4H: pykrx는 일봉 전용 — 4H 섹션은 항상 시그널 없음으로 표시됩니다.

## Telegram 알림 포맷

US/KR 각각 별도 메시지로 전송하며, 각 메시지에 4H + 1D 두 섹션이 포함됩니다.

```
🇺🇸 미국 시장 (US)

⏰ 시그널 시점: 2026년 05월 10일 22시 30분

📊 4시간 캔들

✅ BUY SIGNAL

🇺🇸 AI반도체
• NVDA  $1,092.50

🔴 SELL SIGNAL
  • 시그널 없음

🟡 SQUEEZE 형성 중
  • 시그널 없음
━━━━━━━━━━━━━━━━━━━━
📊 1일 캔들
...
```

## GitHub Actions 스케줄

| 시장 | cron (UTC) | KST | 목적 |
|------|-----------|-----|------|
| KR | `0 0 * * 1-5` | 09:00 | 장 시작 |
| KR | `0 4 * * 1-5` | 13:00 | 4H 중간 |
| KR | `30 6 * * 1-5` | 15:30 | 장 마감 (1D 확정) |
| US | `30 13 * * 1-5` | 22:30 | EDT 09:30 ET 개장 |
| US | `0 18 * * 1-5` | 03:00 | EDT 14:00 ET 중반 |
| US | `0 21 * * 1-5` | 06:00 | EDT 17:00 ET 마감 후 |

## 환경 설정

`.env` 파일 생성 후 아래 값 입력:

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

GitHub Actions 사용 시 Secrets 등록 필요:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 실행 방법

```bash
pip install -r requirements.txt

# 현재 시점 시그널 전송
python main.py --market both --mode notify

# 특정 날짜 기준 시그널 재현
python main.py --market both --mode notify --as_of 2026-04-25

# Telegram 연결 테스트
python main.py --mode test_telegram
```
