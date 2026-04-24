# MetaScalp SDK for OBS Studio

> Automatic video recording in OBS Studio when positions or orders appear in MetaScalp.

**Download:** [Latest Release (v1.0.0)](https://github.com/maratsalihov/MetaScalp-SDK-OBS-Studio/releases/tag/v1.0.0)

## Supported Terminals

- **MetaScalp** ✅ (currently)
- **Tiger.Trade** 🚧 (seeking contributor)
- **Vataga** 🚧 (seeking contributor)

## Want to add support for your terminal?

This SDK is open source. The logic is simple - listen to WebSocket events and control OBS recording. 
Pull requests welcome! Help add support for Tiger.Trade, Vataga, or other trading terminals.

## Trading, Scalping, Overlay, Automation, MetaScalp, OBS Studio, SDK

## Features

- 🎥 Automatically starts recording when position opens OR order is placed
- 📝 Records when pending order (limit/stop) is placed - before position opens
- ⏹ Stops recording when all orders AND positions are closed
- 📁 Filename: `[date_time] TICKER1+TICKER2.mp4` (based on open position tickers)
- 📹 Video captures the trade moment (order placement → position open → position closed)
- 🌍 Works with all exchanges (Binance, Bybit, OKX, Gate, HyperLiquid, etc.)
- 🔄 Multiple tickers support simultaneously

## Quick Start

```bash
# 1. Install dependencies
pip install websocket-client obswebsocket-python python-dotenv

# 2. Configure (or just press Enter for all exchanges)
python setup.py

# 3. Run
python metascalp_obs_recorder.py
```

## setup.py configuration

```
1. Open http://127.0.0.1:17845/api/connections
2. Copy JSON
3. Paste in setup.py and press Enter
```

## Requirements

- Python 3.8+
- OBS Studio with WebSocket enabled (Tools → WebSocket Server Settings)
- MetaScalp running

## config.json

```json
{
  "obs": {
    "host": "127.0.0.1",
    "port": 4455,
    "password": "",
    "video_path": "e:\\video"
  },
  "filename_template": "[{date}_{time}] {tickers}.mp4"
}
```

## How it works

1. Script connects to MetaScalp WebSocket
2. Listens to `position_update` events
3. On first open position → start recording in OBS
4. On last closed position → stop recording
5. Video is saved and renamed

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

**Скачать:** [Последний релиз (v1.0.0)](https://github.com/maratsalihov/MetaScalp-SDK-OBS-Studio/releases/tag/v1.0.0)

## Поддерживаемые терминалы

- **MetaScalp** ✅ (сейчас)
- **Tiger.Trade** 🚧 (нужен контрибьютор)
- **Vataga** 🚧 (нужен контрибьютор)

## Хочешь добавить поддержку своего терминала?

Это open source проект. Логика простая - слушай WebSocket события и управляй записью в OBS.
Pull requests приветствуются! Помоги добавить поддержку Tiger.Trade, Vataga или других терминалов.

## Быстрый старт

```bash
# 1. Установи зависимости
pip install websocket-client obswebsocket-python python-dotenv

# 2. Настрой (или просто нажми Enter для всех бирж)
python setup.py

# 3. Запусти
python metascalp_obs_recorder.py
```

## Настройка setup.py

```
1. Открой http://127.0.0.1:17845/api/connections
2. Скопируй JSON
3. Вставь в setup.py и нажми Enter
```

## Требования

- Python 3.8+
- OBS Studio с включенным WebSocket (Tools → WebSocket Server Settings)
- MetaScalp запущенный

## config.json

```json
{
  "obs": {
    "host": "127.0.0.1",
    "port": 4455,
    "password": "",
    "video_path": "e:\\video"
  },
  "filename_template": "[{date}_{time}] {tickers}.mp4"
}
```

## Как это работает

1. Скрипт подключается к MetaScalp WebSocket
2. Слушает события `position_update`
3. При первой открытой позиции → старт записи в OBS
4. При последней закрытой позиции → стоп записи
5. Видео сохраняется и переименовывается

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