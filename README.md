# MetaScalp SDK for OBS Studio

> Automatic video recording in OBS Studio when positions or orders appear in MetaScalp.

## Supported Terminals

- **MetaScalp** ✅ (currently)
- **Tiger.Trade** 🚧 (seeking contributor)
- **Vataga** 🚧 (seeking contributor)

## Want to add support for your terminal?

This SDK is open source. The logic is simple - listen to WebSocket events and control OBS recording. 
Pull requests welcome! Help add support for Tiger.Trade, Vataga, or other trading terminals.

## Features

- 🎥 Automatically starts recording when position opens OR order is placed
- 📝 Records when pending order (limit/stop) is placed - before position opens
- ⏹ Stops recording when all orders AND positions are closed (with 10s cooldown)
- 📁 Filename: `2026-04-24_15-30_BSBUSDT.mp4`
- 📹 Video captures the trade moment (order placement → position open → position closed)
- 🌍 Works with all exchanges (Binance, Bybit, OKX, Gate, HyperLiquid, etc.)
- 🔄 Multiple tickers support simultaneously
- 🔄 Watchdog stops recording if position not closed via WebSocket

## Quick Start

```bash
# 1. Install dependencies
pip install websocket-client obswebsocket-python python-dotenv requests

# 2. Configure (or just press Enter for all exchanges)
python setup.py

# 3. Run
python metascalp_obs_recorder.py
```

## Requirements

- Python 3.8+
- OBS Studio with WebSocket enabled (Tools → WebSocket Server Settings)
- MetaScalp running
- requests library (for position check)

## OBS settings

1. Enable WebSocket: Tools → WebSocket Server Settings → Enable
2. Password can be left empty (for local use)
3. Recording path: Settings → Output → Recording → Path

## License

MIT

## Credits & Tools 🛠️

Created by **@maratsalihov**

This project was built with the help of:
- **Big Pickle (OpenCode Zen)** — for core logic and architecture
- **Zed IDE** — for fast coding
- **MetaScalp SDK** — for trading data access

---

# MetaScalp OBS Recorder

Автоматическая запись видео в OBS Studio при открытии сделок или заявок в MetaScalp.

## Поддерживаемые терминалы

- **MetaScalp** ✅ (сейчас)
- **Tiger.Trade** 🚧 (нужен контрибьютор)
- **Vataga** 🚧 (нужен контрибьютор)

## Хочешь добавить поддержку своего терминала?

Это open source проект. Логика простая - слушай WebSocket события и управляй записью в OBS.
Pull requests приветствуются! Помоги добавить поддержку Tiger.Trade, Vataga или других терминалов.

## Возможности

- 🎥 Автоматически начинает запись при открытии позиции или размещении заявки
- 📝 Записывает момент отложки (лимит/стоп) до открытия позиции
- ⏹ Останавливает запись когда все заявки и позиции закрыты (с cooldown 10 сек)
- 📁 Имя файла: `2026-04-24_15-30_BSBUSDT.mp4`
- 📹 Видео захватывает момент сделки (размещение заявки → открытие → закрытие)
- 🌍 Работает со всеми биржами (Binance, Bybit, OKX, Gate, HyperLiquid и т.д.)
- 🔄 Поддержка нескольких тикеров одновременно
- 🔄 Watchdog останавливает запись если позиция не закрылась через WebSocket

## Быстрый старт

```bash
# 1. Установи зависимости
pip install websocket-client obswebsocket-python python-dotenv requests

# 2. Настрой (или просто нажми Enter для всех бирж)
python setup.py

# 3. Запусти
python metascalp_obs_recorder.py
```

## Требования

- Python 3.8+
- OBS Studio с включенным WebSocket (Tools → WebSocket Server Settings)
- MetaScalp запущенный
- requests библиотека (для проверки позиций)

## OBS настройки

1. Включи WebSocket: Tools → WebSocket Server Settings → Enable
2. Пароль можно оставить пустым (для локального использования)
3. Путь записи: Settings → Output → Recording → Path

## Лицензия

MIT

## Credits & Tools 🛠️

Создано **@maratsalihov**

Проект создан при помощи:
- **Big Pickle (OpenCode Zen)** — логика и архитектура
- **Zed IDE** — быстрое кодирование
- **MetaScalp SDK** — доступ к данным терминала