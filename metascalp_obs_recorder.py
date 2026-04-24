"""
MetaScalp SDK + OBS Studio Video Recording Automation

This script monitors trading positions via MetaScalp SDK and controls
OBS Studio recording based on position open/close events.

Uses official MetaScalp SDK
WebSocket: ws://127.0.0.1:17845/
"""

import os
import sys
import json
import time
import logging
import asyncio
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False
    tk = None

try:
    from obswebsocket import obsws, requests
    OBS_WEBSOCKET_AVAILABLE = True
except ImportError:
    OBS_WEBSOCKET_AVAILABLE = False
    obsws = None
    requests = None

from dotenv import load_dotenv

try:
    from metascalp import MetaScalpClient, MetaScalpSocket
    METASCALP_AVAILABLE = True
except ImportError:
    METASCALP_AVAILABLE = False
    MetaScalpClient = None
    MetaScalpSocket = None

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PositionData:
    """Stores information about a single position."""
    ticker: str
    size: float
    side: str  # "Buy" or "Sell" from API
    realized_pnl: float = 0.0
    
    @property
    def is_open(self) -> bool:
        return self.size > 0
    
    @property
    def normalized_side(self) -> str:
        """Normalize side to LONG or SHORT."""
        side_upper = self.side.upper()
        if side_upper in ("BUY", "LONG"):
            return "LONG"
        return "SHORT"


@dataclass
class TradeSession:
    """Tracks a complete trade session from entry to full exit."""
    ticker: str = ""
    side: str = ""  # LONG or SHORT
    entry_time: Optional[datetime] = None
    total_pnl: float = 0.0
    is_recording: bool = False


class OBSController:
    """Controls OBS Studio via obswebsocket library."""
    
    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password or ""
        self.client = None
        self.connected = False
    
    def connect(self) -> bool:
        try:
            from obswebsocket import obsws
            self.client = obsws(self.host, self.port, self.password)
            self.client.connect()
            self.connected = True
            logger.info(f"Подключено к OBS {self.host}:{self.port}")
            return True
        except Exception as e:
            self.connected = False
            logger.error(f"Не подключиться к OBS: {e}")
            return False
    
    def ensure_connected(self) -> bool:
        if self.connected and self.client:
            return True
        return self.connect()
    
    def is_recording(self) -> bool:
        if not self.ensure_connected():
            return False
        try:
            from obswebsocket import requests
            status = self.client.call(requests.GetRecordStatus())
            return status.getOutputActive()
        except Exception as e:
            logger.error(f"Ошибка проверки статуса: {e}")
            self.connected = False
            return False
    
    def start_recording(self) -> bool:
        if not self.ensure_connected():
            return False
        try:
            from obswebsocket import requests
            self.client.call(requests.StartRecord())
            logger.info("Запись началась!")
            return True
        except Exception as e:
            logger.error(f"Ошибка старта записи: {e}")
            return False
    
    def stop_recording(self) -> bool:
        if not self.ensure_connected():
            return False
        try:
            from obswebsocket import requests
            self.client.call(requests.StopRecord())
            logger.info("Запись остановлена!")
            return True
        except Exception as e:
            logger.error(f"Ошибка стопа записи: {e}")
            return False
    
    def get_output_directory(self) -> Optional[str]:
        video_path = os.getenv("OBS_VIDEO_PATH", "")
        if video_path and Path(video_path).exists():
            return video_path
        default_paths = [
            Path.home() / "Videos",
            Path.home() / "Desktop",
        ]
        for p in default_paths:
            if p.exists():
                return str(p)
        return None


class MetaScalpPositionTracker:
    """
    Tracks position changes via MetaScalp SDK WebSocket events.
    
    This class implements event-driven logic to detect position
    openings and closings, handling partial closes correctly.
    
    Position data format from MetaScalp SDK:
    {
        "connectionId": int,
        "ticker": str,
        "size": float,
        "side": str,  # "Buy" or "Sell"
        "realizedPnl": float
    }
    """
    
    def __init__(self):
        self.positions: Dict[str, PositionData] = {}  # ticker -> PositionData
        self.trade_session: Optional[TradeSession] = None
        self._accumulated_pnl: Dict[str, float] = {}  # ticker -> accumulated pnl
        
    def process_position_update(self, data: Dict[str, Any]):
        """
        Process a position update from MetaScalp SDK WebSocket.
        
        Args:
            data: Position data dict from SDK with keys:
                - connectionId: int
                - ticker: str
                - size: float
                - side: str ("Buy" or "Sell")
                - realizedPnl: float (optional)
        """
        ticker = data.get("ticker", "")
        size = float(data.get("size", 0))
        side = data.get("side", "Buy")
        realized_pnl = float(data.get("realizedPnl", 0) or 0)
        
        if not ticker:
            logger.warning("Received position update without ticker")
            return
        
        normalized_side = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
        
        # Check if we had a position before
        had_position = ticker in self.positions and self.positions[ticker].is_open
        
        # Update or create position
        if size > 0:
            self.positions[ticker] = PositionData(
                ticker=ticker,
                size=size,
                side=side,
                realized_pnl=realized_pnl
            )
            
            # Accumulate PnL for this ticker
            if ticker not in self._accumulated_pnl:
                self._accumulated_pnl[ticker] = 0.0
            
            if realized_pnl != 0:
                self._accumulated_pnl[ticker] += realized_pnl
                logger.info(f"Accumulated PnL for {ticker}: {self._accumulated_pnl[ticker]:.2f} (this update: {realized_pnl:.2f})")
            
            # Detect new position opening
            if not had_position:
                self._on_position_open(ticker, size, normalized_side)
                
        else:
            # Position closed (size == 0)
            if had_position:
                total_pnl = self._accumulated_pnl.get(ticker, 0.0)
                old_side = self.positions[ticker].normalized_side
                self._on_position_close(ticker, old_side, total_pnl)
            
            # Clean up
            if ticker in self.positions:
                del self.positions[ticker]
            if ticker in self._accumulated_pnl:
                del self._accumulated_pnl[ticker]
    
    def _on_position_open(self, ticker: str, size: float, side: str):
        """Handle position opening event."""
        now = datetime.now()
        
        self.trade_session = TradeSession(
            ticker=ticker,
            side=side,
            entry_time=now,
            total_pnl=0.0,
            is_recording=False
        )
        
        logger.info(f"Position opened: {ticker} {side} at {now}")
    
    def _on_position_close(self, ticker: str, side: str, total_pnl: float):
        """Handle position closing event (full close)."""
        if self.trade_session and self.trade_session.ticker == ticker:
            self.trade_session.total_pnl = total_pnl
        
        logger.info(
            f"Position closed: {ticker} {side}, "
            f"Total PnL: {total_pnl:.2f}"
        )
    
    def get_active_session(self) -> Optional[TradeSession]:
        """Get the current active trade session if any."""
        return self.trade_session
    
    def has_open_positions(self) -> bool:
        """Check if there are any open positions."""
        return any(pos.is_open for pos in self.positions.values())


class TradingRecorder:
    """
    Main controller that integrates MetaScalp tracking with OBS recording.
    """
    
    def __init__(self, config_path="config.json"):
        # Try to load from config.json first
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            self.obs_host = config.get("obs", {}).get("host", "127.0.0.1")
            self.obs_port = config.get("obs", {}).get("port", 4455)
            self.obs_password = config.get("obs", {}).get("password", "")
            self.obs_video_path = config.get("obs", {}).get("video_path", "e:\\video")
            self.exchange_ids = config.get("exchange_ids", [])
            self.filename_template = config.get("filename_template", "[{date}_{time}] {tickers}.mp4")
        except FileNotFoundError:
            # Fallback to environment
            self.obs_host = os.getenv("OBS_HOST", "localhost")
            self.obs_port = int(os.getenv("OBS_PORT", "4455"))
            self.obs_password = os.getenv("OBS_PASSWORD", "")
            self.obs_video_path = os.getenv("OBS_VIDEO_PATH", "")
            self.filename_template = os.getenv(
                "FILENAME_TEMPLATE",
                "[{date}_{time}] {tickers}.mp4"
            )
            self.exchange_ids = []
        
        # Recording state - track manually
        self._recording_active = False
        self._last_ticker = ""
        self._last_side = ""
        self._last_size = {}  # Track size per ticker
        
        # Track recording start time for file identification
        self._recording_start_time = None  # datetime when recording started
        
        # Cooldown settings for frequent trades
        self._cooldown_seconds = 10  # Don't stop for 10 seconds after close
        self._stop_scheduled = False  # True if stop is pending
        self._stop_timer = None  # Timer thread for delayed stop
        self._pending_ticker = ""  # Ticker for scheduled stop
        self._pending_side = ""  # Side for scheduled stop
        
        # Initialize components
        self.obs_controller = OBSController(
            self.obs_host, 
            self.obs_port, 
            self.obs_password
        )
        # Simplified tracking - no position tracker needed
        self._active_tickers = set()   # открытые сейчас
        self._session_tickers = set()  # все тикеры за сессию
        
        # Track pending orders - для запуска записи при выставлении заявки ДО открытия позиции
        self._active_orders = set()  # {(ticker, order_id)}
        
        # Track: была ли позиция открыта в текущей сессии записи?
        self._had_position_opened = False  # True если была хотя бы одна позиция opened
    
    def handle_position_event(self, ticker: str, size: float, side: str, realized_pnl: float = 0.0):
        """
        Handle a position update event from MetaScalp SDK.
        Поддержка нескольких тикеров одновременно.
        """
        # Нормализуем размер: сохраняем знак в side
        if size < 0:
            side = "Short"
            size = abs(size)
        elif size > 0:
            side = side.capitalize() if side else "Buy"
        
        logger.info(f"Position update: {ticker} {side} size={size}")
        
        # Определяем: была ли позиция открыта до этого?
        was_open = ticker in self._active_tickers
        
        # Определяем: открыта ли позиция сейчас?
        is_open = size != 0
        
        # СЛУЧАЙ 1: Позиция открылась
        if not was_open and is_open:
            # Cancel any scheduled stop (cooldown)
            if self._stop_scheduled:
                logger.info(f"🟢 New position before cooldown ends -> canceling scheduled stop")
                self._cancel_scheduled_stop()
            
            logger.info(f"🟢 Position opened: {ticker}")
            self._active_tickers.add(ticker)
            self._session_tickers.add(ticker)  # запоминаем для имени файла
            self._had_position_opened = True  # Mark что позиция была открыта
            
            # Если это первая позиция - старт записи
            if len(self._active_tickers) == 1:
                logger.info(f"First position -> START recording")
                self._recording_active = True
                self._last_ticker = ticker
                self._last_side = side
                self._recording_start_time = datetime.now()  # Track start
                self._start_recording_flow(ticker, side)
        
        # СЛУЧАЙ 2: Позиция закрылась
        elif was_open and not is_open:
            logger.info(f"🔴 Position closed: {ticker}")
            self._active_tickers.discard(ticker)
            self._last_size[ticker] = 0  # explicitly set to 0
            
            logger.info(f"Active tickers now: {self._active_tickers}")
            
            # Если закрылась последняя позиция - планируем стоп с cooldown
            if len(self._active_tickers) == 0:
                logger.info(f"Last position closed -> scheduling stop in {self._cooldown_seconds}s (cooldown)")
                self._schedule_stop_recording(ticker, side)
        
        # Всегда обновляем размер
        self._last_size[ticker] = size
    
    def handle_order_event(self, ticker: str, order_id: str, status: str, side: str, order_type: str = "Limit"):
        """
        Handle an order update event from MetaScalp SDK.
        Запускает запись при создании заявки (до открытия позиции).
        """
        if not ticker:
            logger.warning("handle_order_event: empty ticker!")
            return
        
        status_lower = (status or "").lower()
        logger.info(f"📝 Order event: {ticker} order={order_id} status={status} ({status_lower}) active_orders={len(self._active_orders)} active_positions={len(self._active_tickers)} recording={self._recording_active}")
        
        # Новый заявка (New, Open, PartiallyFilled) - запоминаем
        if status_lower in ("new", "open", "partiallyfilled", "partially_filled"):
            order_key = (ticker, order_id)
            if order_key not in self._active_orders:
                logger.info(f"📝 New order added: {ticker} {order_type} {side} ID={order_id} status={status}")
                self._active_orders.add(order_key)
                self._session_tickers.add(ticker)
                
                # Если нет активной записи - начинаем
                if not self._recording_active:
                    logger.info(f"📝 Order without position -> START recording")
                    self._recording_active = True
                    self._last_ticker = ticker
                    self._last_side = side
                    self._recording_start_time = datetime.now()  # Track start
                    self._start_recording_flow(ticker, side)
        
        # ALTERNATIVE: Check if this status means order is no longer active
        elif status_lower:
            order_key = (ticker, order_id)
            if order_key in self._active_orders:
                # Check for any status that is NOT a new/active order
                if status_lower not in ("new", "open", "partiallyfilled", "partially_filled", "partially-filled"):
                    logger.info(f"❌ Order no longer active: {ticker} ID={order_id} status={status} -> removing")
                    self._active_orders.discard(order_key)
        
        # Проверяем: если нет заявок и нет позиций - останавливаем запись
        if not self._active_orders and not self._active_tickers and self._recording_active:
            logger.info(f"🛑 STOP CONDITION MET: orders={len(self._active_orders)}, positions={len(self._active_tickers)}, recording={self._recording_active}")
            # Определяем тип файла: была ли позиция?
            # Определяем тип файла: была ли позиция?
            if self._had_position_opened:
                # Позиция была -> обычный файл
                suffix = ""
                logger.info(f"📝 Position was opened -> normal file")
            else:
                # Только заявка, без позиции -> добавляем маркер
                suffix = "_NOFill"
                logger.info(f"📝 Order canceled/expired without position -> NOFill file")
            
            logger.info(f"📝 No orders and no positions -> STOP recording")
            self._recording_active = False
            tickers_str = "+".join(sorted(self._session_tickers)) if self._session_tickers else ticker
            self._stop_recording_flow(tickers_str, side, 0.0, suffix)
            self._session_tickers.clear()
            self._had_position_opened = False  # Reset for next session
    
    def _start_recording_flow(self, ticker: str, side: str):
        """Execute the recording start flow."""
        logger.info(f"Starting recording for {ticker} {side}")
        
        # Track start time for file identification
        self._recording_start_time = datetime.now()
        
        if self.obs_controller.start_recording():
            logger.info(f"Recording started at {self._recording_start_time}")
        else:
            logger.error("Failed to start recording - will retry on next event")
    
    def _schedule_stop_recording(self, ticker: str, side: str):
        """Schedule recording stop after cooldown period."""
        if self._stop_scheduled:
            logger.info("Stop already scheduled, skipping")
            return
        
        self._stop_scheduled = True
        self._pending_ticker = "+".join(sorted(self._session_tickers)) if self._session_tickers else ticker
        self._pending_side = side
        
        def delayed_stop():
            if self._stop_scheduled:  # Double-check not canceled
                logger.info(f"Cooldown expired -> executing scheduled stop")
                self._recording_active = False
                self._stop_recording_flow(self._pending_ticker, side, 0.0)
                self._session_tickers.clear()
                self._had_position_opened = False
                self._stop_scheduled = False
        
        self._stop_timer = threading.Timer(self._cooldown_seconds, delayed_stop)
        self._stop_timer.start()
        logger.info(f"Stop scheduled for {self._cooldown_seconds}s from now")
    
    def _cancel_scheduled_stop(self):
        """Cancel scheduled recording stop."""
        if self._stop_timer and self._stop_scheduled:
            self._stop_timer.cancel()
            self._stop_timer = None
            self._stop_scheduled = False
            logger.info("Scheduled stop cancelled")
    
    def _stop_recording_flow(self, ticker: str, side: str, pnl: float, suffix: str = ""):
        """Execute the recording stop and file rename flow."""
        # Проверяем, активна ли запись
        is_rec = self.obs_controller.is_recording()
        logger.info(f"Current OBS recording status before stop: {is_rec}")
        
        success = self.obs_controller.stop_recording()
        
        if success:
            logger.info("✅ Stop recording command sent successfully")
        else:
            logger.error("❌ Failed to stop recording, retrying in 1s...")
            time.sleep(1)
            self.obs_controller.stop_recording()
        
        # Ждем финализации файла (увеличено для надежности)
        logger.info("Waiting 6 seconds for file finalization...")
        time.sleep(6)
        
        # Проверяем, что запись действительно остановилась
        is_rec_after = self.obs_controller.is_recording()
        logger.info(f"Current OBS recording status after stop: {is_rec_after}")
        
        # Rename the recorded file
        self._rename_last_recording(ticker, side, pnl, suffix)
    
    def _rename_last_recording(self, tickers: str, side: str, pnl: float, suffix: str = ""):
        """Find and rename the most recent recording file."""
        # Get video directory
        video_dir = self.obs_video_path
        if not video_dir:
            video_dir = self.obs_controller.get_output_directory()
        
        if not video_dir:
            logger.error("Cannot determine video directory for renaming")
            return
        
        video_path = Path(video_dir)
        if not video_path.exists():
            logger.error(f"Video directory does not exist: {video_dir}")
            return
        
        # Find video files created AFTER recording started
        start_time = self._recording_start_time
        logger.info(f"Looking for files after {start_time}")
        
        video_files = []
        for ext in ('*.mp4', '*.mkv'):
            for f in video_path.glob(ext):
                # Check if file was created during this recording session
                mtime = datetime.fromtimestamp(f.stat().st_mtime)
                if start_time and mtime >= start_time:
                    video_files.append((mtime, f))
        
        if not video_files:
            # Fallback: get any recent file
            logger.warning("No files from this session, trying any file...")
            for ext in ('*.mp4', '*.mkv'):
                video_files.extend(video_path.glob(ext))
        
        if not video_files:
            logger.warning("No video files found to rename")
            return
        
        # Sort by modification time and get the latest
        if isinstance(video_files[0], tuple):
            latest_file = max(video_files, key=lambda x: x[0])[1]
        else:
            latest_file = max(video_files, key=lambda f: f.stat().st_mtime)
        
        logger.info(f"Found file to rename: {latest_file.name}")
        
        # Generate new filename using tickers (side and pnl removed as agreed)
        now = datetime.now()
        
        # International sortable format: YYYY-MM-DD HH-MM
        date_str = now.strftime("%Y-%m-%d")  # 2026-04-23 for sorting
        time_str = now.strftime("%H-%M")
        
        # Insert suffix before file extension (e.g., _NOFill)
        base_name = self.filename_template.format(
            date=date_str,  # 2026-04-23
            time=time_str,
            tickers=tickers,
            ticker=tickers,
            side="",
            pnl=""
        )
        
        # Add suffix (e.g., _NOFill) before extension
        if suffix:
            base_name = base_name.replace(".mp4", f"{suffix}.mp4").replace(".mkv", f"{suffix}.mkv")
        
        new_path = video_path / base_name
        
        # Handle duplicate filenames
        if new_path.exists():
            timestamp = int(time.time())
            new_name = f"{timestamp}_{base_name}"
            new_path = video_path / new_name
        
        # Retry loop for file access (handles WinError 32 - file in use)
        max_retries = 10
        for attempt in range(max_retries):
            try:
                latest_file.rename(new_path)
                logger.info(f"Renamed: {latest_file.name} -> {new_path.name}")
                return
            except PermissionError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"File busy (attempt {attempt + 1}/{max_retries}), retrying in 1s...")
                    time.sleep(1)
                else:
                    logger.error(f"Failed to rename after {max_retries} attempts: {e}")
            except Exception as e:
                logger.error(f"Failed to rename file: {e}")
                return
    
    def _format_pnl(self, pnl: float) -> str:
        """Format PnL value with sign."""
        if pnl >= 0:
            return f"+{pnl:.2f}"
        else:
            return f"{pnl:.2f}"
    
    def run_demo_loop(self, duration: int = 60):
        """
        Run a demonstration loop simulating MetaScalp SDK events.
        
        This is for testing purposes. In production, replace this with
        actual MetaScalp SDK event subscription.
        """
        logger.info(f"Starting demo mode for {duration} seconds...")
        logger.info("Simulating position open/close events...")
        
        start_time = time.time()
        
        # Simulate: Open position
        logger.info("--- Simulating: Opening BTCUSDT LONG position ---")
        self.handle_position_event("BTCUSDT", 1.0, "Buy", 0.0)
        
        # Wait some time (simulating active trade)
        time.sleep(5)
        
        # Simulate: Partial close (should NOT stop recording)
        logger.info("--- Simulating: Partial close (0.5 remaining) ---")
        self.handle_position_event("BTCUSDT", 0.5, "Buy", 10.0)
        
        time.sleep(3)
        
        # Simulate: More PnL accumulation
        logger.info("--- Simulating: Additional PnL realization ---")
        self.handle_position_event("BTCUSDT", 0.5, "Buy", 15.0)
        
        time.sleep(3)
        
        # Simulate: Full close (should stop recording and rename)
        logger.info("--- Simulating: Full position close ---")
        self.handle_position_event("BTCUSDT", 0.0, "Buy", 25.0)
        
        # Wait for file operations
        time.sleep(5)
        
        # Simulate another trade: ETHUSDT SHORT
        logger.info("--- Simulating: Opening ETHUSDT SHORT position ---")
        self.handle_position_event("ETHUSDT", 10.0, "Sell", 0.0)
        
        time.sleep(5)
        
        logger.info("--- Simulating: Full close with loss ---")
        self.handle_position_event("ETHUSDT", 0.0, "Sell", -35.50)
        
        elapsed = time.time() - start_time
        remaining = max(0, duration - elapsed)
        
        if remaining > 0:
            logger.info(f"Demo completed. Waiting {remaining:.0f}s before exit...")
            time.sleep(remaining)
        
        logger.info("Demo loop finished")


def create_metascalp_event_handler(recorder: TradingRecorder):
    """
    Create an event handler function for MetaScalp SDK integration.
    
    Use this function to integrate with the actual MetaScalp SDK.
    Pass the returned handler to the SDK's event subscription mechanism.
    
    Example:
        recorder = TradingRecorder()
        handler = create_metascalp_event_handler(recorder)
        metascalp_client.on_position_update(handler)
    """
    def on_position_update(event_data: Dict[str, Any]):
        """
        Handler for MetaScalp SDK position update events.
        
        Expected event_data structure:
        {
            'ticker': str,      # e.g., "BTCUSDT"
            'size': float,      # Current position size
            'side': str,        # "Buy"/"Sell" or "Long"/"Short"
            'realized_pnl': float  # Realized PnL (optional, default 0)
        }
        """
        # ЛОГИРОВАНИЕ СЫРЫХ ДАННЫХ
        logger.info(f"RAW EVENT: {event_data}")
        
        ticker = event_data.get('ticker', '')
        size = float(event_data.get('size', 0))
        side = event_data.get('side', '')
        realized_pnl = float(event_data.get('realized_pnl', 0))
        
        # Проверяем status
        status = event_data.get('status', '')
        if status and status.lower() in ('closed', 'close'):
            logger.info(f"Status indicates closed: {status}, setting size=0")
            size = 0.0
        
        recorder.handle_position_event(ticker, size, side, realized_pnl)
    
    return on_position_update


class MetaScalpSDKIntegration:
    """
    Integrates with the official MetaScalp SDK for real-time position updates.
    
    Uses MetaScalpSocket from the official SDK:
    https://github.com/MetaScalp/metascalp-sdk
    
    WebSocket endpoint: ws://127.0.0.1:17845/
    REST endpoint: http://127.0.0.1:17845/
    
    Usage:
        recorder = TradingRecorder()
        integration = MetaScalpSDKIntegration(recorder)
        await integration.run()
    """
    
    def __init__(self, recorder: TradingRecorder):
        self.recorder = recorder
        self.socket: Optional[MetaScalpSocket] = None
        self.client: Optional[MetaScalpClient] = None
        self.connection_id: Optional[int] = None
        self._running = False
        
    async def connect(self, max_retries: int = 5, retry_delay: float = 2.0) -> bool:
        """
        Connect to MetaScalp via WebSocket.
        
        Auto-discovers the running MetaScalp instance on ports 17845-17855.
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Connecting to MetaScalp SDK (attempt {attempt + 1}/{max_retries})...")
                
                # Discover and connect to WebSocket
                self.socket = await MetaScalpSocket.discover(timeout=2.0)
                logger.info(f"WebSocket connected to MetaScalp on port {self.socket.port}")
                
                # Get connection ID via REST client
                self.client = await MetaScalpClient.discover(timeout=2.0)
                logger.info(f"REST client connected to MetaScalp on port {self.client.port}")
                
                # Get available connections
                connections_data = await self.client.get_connections()
                connections = connections_data.get("connections", [])
                
                if not connections:
                    logger.error("No active exchange connections found in MetaScalp")
                    await self.close()
                    return False
                
                # Use the first active connection
                self.connection_id = connections[0]["id"]
                logger.info(f"Using connection ID: {self.connection_id} ({connections[0]['name']})")
                
                # Subscribe to position and order updates
                self.socket.subscribe(self.connection_id)
                logger.info(f"Subscribed to position updates for connection {self.connection_id}")
                
                # Register position update handler
                @self.socket.on("position_update")
                def on_position(data):
                    self._handle_position_event(data)
                
                # Register order update handler
                @self.socket.on("order_update")
                def on_order(data):
                    self._handle_order_event(data)
                
                # Check for existing positions/orders and start recording if needed
                await self._check_existing_positions()
                
                self._running = True
                return True
                
            except ConnectionError as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error("Max retries reached. Could not connect to MetaScalp.")
                    return False
            except Exception as e:
                logger.error(f"Unexpected error during connection: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    return False
        
        return False
    
    async def _check_existing_positions(self):
        """Check for existing positions/orders on startup and start recording if needed."""
        logger.info("Checking for existing positions/orders...")
        
        try:
            # Check positions via REST
            positions_data = await self.client.get_positions(self.connection_id)
            positions = positions_data.get("positions", [])
            
            # Check orders via REST
            try:
                orders_data = await self.client.get_orders(self.connection_id)
                orders = orders_data.get("orders", [])
            except:
                orders = []
            
            logger.info(f"Found {len(positions)} positions and {len(orders)} active orders")
            
            # If there are existing positions or orders, start recording
            if positions or orders:
                for pos in positions:
                    ticker = pos.get("ticker", "")
                    if ticker:
                        self.recorder._active_tickers.add(ticker)
                        self.recorder._session_tickers.add(ticker)
                        self.recorder._had_position_opened = True
                
                for order in orders:
                    ticker = order.get("ticker", "")
                    if ticker:
                        self.recorder._session_tickers.add(ticker)
                
                if not self.recorder._recording_active:
                    logger.info("Existing positions/orders found -> START recording")
                    self.recorder._recording_active = True
                    self.recorder._recording_start_time = datetime.now()
                    self.recorder._start_recording_flow(
                        "+".join(sorted(self.recorder._session_tickers)) or "unknown",
                        "unknown"
                    )
            else:
                logger.info("No existing positions or orders found")
                
        except Exception as e:
            logger.error(f"Error checking existing positions: {e}")
    
    def _handle_position_event(self, data: Dict[str, Any]):
        """
        Handle raw position update from MetaScalp SDK.
        
        SDK position data format:
        {
            "connectionId": int,
            "ticker": str,
            "size": float,
            "side": str,  # "Buy" or "Sell"
            "realizedPnl": float (optional)
        }
        """
        try:
            # ЛОГИРОВАНИЕ СЫРЫХ ДАННЫХ
            logger.info(f"RAW EVENT: {data}")
            
            ticker = data.get("ticker", "")
            size = float(data.get("size", 0))
            side = data.get("side", "Buy")
            realized_pnl = float(data.get("realizedPnl", 0) or 0)
            
            # ПРОВЕРЯЕМ ПОЛЕ STATUS
            status = data.get("status", "")
            if status and status.lower() in ("closed", "close"):
                logger.info(f"Status indicates closed: {status}, setting size=0")
                size = 0.0
            
            logger.debug(f"Position update: {ticker} size={size} side={side} realizedPnl={realized_pnl}")
            
            self.recorder.handle_position_event(ticker, size, side, realized_pnl)
            
        except Exception as e:
            logger.error(f"Error processing position event: {e}", exc_info=True)
    
    def _handle_order_event(self, data: Dict[str, Any]):
        """
        Handle raw order update from MetaScalp SDK.
        
        SDK order data format:
        {
            "connectionId": int,
            "orderId": str,
            "ticker": str,
            "side": str,  # "Buy" or "Sell"
            "type": str,  # "Limit", "Stop", etc.
            "status": str,  # "New", "Open", "Filled", "Canceled", etc.
            "size": float,
            "price": float
        }
        """
        try:
            logger.info(f"ORDER EVENT: {data}")
            
            ticker = data.get("ticker", "")
            order_id = str(data.get("orderId", data.get("order_id", "")))
            status = data.get("status", "")
            side = data.get("side", "Buy")
            order_type = data.get("type", "Limit")
            connection_id = data.get("connectionId", 0)
            
            logger.info(f"Order: conn={connection_id} ticker={ticker} id={order_id} status={status} type={order_type} {side}")
            logger.info(f"🐞 ORDER_DEBUG: all_fields={data}")
            
            self.recorder.handle_order_event(ticker, order_id, status, side, order_type)
            
        except Exception as e:
            logger.error(f"Error processing order event: {e}", exc_info=True)
    
    async def run(self):
        """
        Run the main event loop.
        
        Connects to MetaScalp and listens for position updates indefinitely.
        Implements auto-reconnect on connection loss.
        """
        while True:
            if not await self.connect():
                logger.warning("Failed to connect to MetaScalp. Retrying in 10s...")
                await asyncio.sleep(10)
                continue
            
            logger.info("Listening for position updates from MetaScalp SDK...")
            logger.info("Press Ctrl+C to stop")
            
            # Start REST watchdog in background
            watchdog_task = asyncio.create_task(self._rest_position_watchdog())
            
            try:
                # Start listening for WebSocket messages
                await self.socket.listen_forever()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self._running = False
                watchdog_task.cancel()
            
            if not self._running:
                break
            
            # Reconnect after disconnection
            logger.info("Connection lost. Reconnecting in 5s...")
            await asyncio.sleep(5)
    
    async def _rest_position_watchdog(self):
        """Fallback: проверка позиций и заявок через REST каждую секунду"""
        while self._running:
            await asyncio.sleep(2)
            try:
                if self.client and self.connection_id:
                    positions = await self.client.get_positions(self.connection_id)
                    position_list = positions.get("positions", [])
                    has_any_position = len(position_list) > 0
                    
                    # Also check orders via REST
                    try:
                        orders_data = await self.client.get_orders(self.connection_id)
                        orders_list = orders_data.get("orders", [])
                        has_any_order = len(orders_list) > 0
                    except:
                        has_any_order = False
                    
                    logger.debug(f"REST: positions={len(position_list)}, orders={len(orders_list) if has_any_order else 0}")
                    
                    if not has_any_position and not has_any_order and self.recorder._recording_active:
                        # Determine suffix based on whether position was opened
                        suffix = "" if self.recorder._had_position_opened else "_NOFill"
                        logger.warning("⚠️ REST watchdog: no positions and no orders but recording active! Forcing stop...")
                        self.recorder._recording_active = False
                        self.recorder._stop_recording_flow("unknown", "unknown", 0, suffix)
            except Exception as e:
                logger.debug(f"REST check failed: {e}")
    
    async def close(self):
        """Clean up resources."""
        self._running = False
        
        if self.socket:
            try:
                await self.socket.disconnect()
            except Exception:
                pass
        
        if self.client:
            try:
                await self.client.close()
            except Exception:
                pass
        
        logger.info("MetaScalp SDK integration closed")


async def run_with_metascalp_sdk():
    """
    Main entry point for running with real MetaScalp SDK.
    
    This function initializes the TradingRecorder and MetaScalpSDKIntegration,
    then runs the event loop.
    """
    recorder = TradingRecorder()
    
    # Log configuration
    logger.info("=" * 60)
    logger.info("MetaScalp SDK + OBS Recording Automation")
    logger.info("=" * 60)
    logger.info(f"OBS Host: {recorder.obs_host}:{recorder.obs_port}")
    logger.info(f"Video Path: {recorder.obs_video_path or '(auto-detect)'}")
    logger.info(f"Filename Template: {recorder.filename_template}")
    logger.info("=" * 60)
    
    # Test OBS connection
    logger.info("Testing OBS connection...")
    if recorder.obs_controller.connect():
        logger.info("OBS connection successful!")
        is_rec = recorder.obs_controller.is_recording()
        logger.info(f"Current recording status: {'ACTIVE' if is_rec else 'INACTIVE'}")
    else:
        logger.warning("Could not connect to OBS. Ensure OBS is running with WebSocket enabled.")
        logger.warning("The script will continue and retry connections as needed.")
    
    # Initialize MetaScalp SDK integration
    integration = MetaScalpSDKIntegration(recorder)
    
    try:
        await integration.run()
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        await integration.close()
        
        # Cleanup OBS
        if recorder.obs_controller.connected:
            try:
                recorder.obs_controller.client.disconnect()
            except Exception:
                pass
        
        logger.info("Application terminated")


if __name__ == "__main__":
    import asyncio
    from metascalp import MetaScalpClient, MetaScalpSocket
    
    import logging
    logging.getLogger("metascalp").setLevel(logging.WARNING)
    
    # Инициализируем рекордер
    recorder = TradingRecorder()
    
    logger.info("=" * 60)
    logger.info("MetaScalp + OBS Recording Automation")
    logger.info("=" * 60)
    logger.info(f"OBS Host: {recorder.obs_host}:{recorder.obs_port}")
    logger.info(f"Video Path: {recorder.obs_video_path or '(auto-detect)'}")
    logger.info("=" * 60)
    
    # Подключаемся к OBS и останавливаем висячую запись
    logger.info("Testing OBS connection...")
    if recorder.obs_controller.connect():
        logger.info("OBS connection successful!")
        
        # Проверяем и останавливаем висячую запись
        is_rec = recorder.obs_controller.is_recording()
        logger.info(f"Current recording status: {'ACTIVE' if is_rec else 'INACTIVE'}")
        
        if is_rec:
            logger.warning("⚠️ Active recording detected! Stopping previous recording...")
            recorder.obs_controller.stop_recording()
            time.sleep(2)
    else:
        logger.warning("Could not connect to OBS.")
    
    async def run_with_metascalp():
        """Запускаем с MetaScalp SDK"""
        logger.info("Connecting to MetaScalp...")
        
        # Подключаемся к MetaScalp
        client = await MetaScalpClient.discover()
        logger.info(f"Connected to MetaScalp on port {client.port}")
        
        # Получаем список соединений
        data = await client.get_connections()
        connections = data.get("connections", [])
        
        # Фильтруем только активные подключения (State == 2)
        active_connections = [c for c in connections if c.get("State") == 2]
        
        if not active_connections:
            logger.error("No active connections found in MetaScalp")
            await client.close()
            return
        
        logger.info(f"Found {len(active_connections)} active connection(s):")
        for conn in active_connections:
            logger.info(f"  - {conn['Name']} (ID: {conn['Id']})")
        
        # Подключаем WebSocket
        socket = await MetaScalpSocket.discover()
        logger.info(f"WebSocket connected to port {socket.port}")
        
        # Подписываемся на обновления позиций
        for conn in active_connections:
            conn_id = conn["Id"]
            conn_name = conn["Name"]
            socket.subscribe(conn_id)
            logger.info(f"Subscribed to position updates for {conn_name}")
        
        # Проверяем существующие позиции/ордера при запуске
        logger.info("Checking for existing positions/orders...")
        for conn in active_connections:
            conn_id = conn["Id"]
            # Check positions
            pos_data = await client.get_positions(conn_id)
            positions = pos_data.get("positions", [])
            for pos in positions:
                ticker = pos.get("ticker", "")
                if ticker:
                    recorder._active_tickers.add(ticker)
                    recorder._session_tickers.add(ticker)
                    recorder._had_position_opened = True
            
            # Check orders
            try:
                orders_data = await client.get_orders(conn_id)
                orders = orders_data.get("orders", [])
                for order in orders:
                    ticker = order.get("ticker", "")
                    if ticker:
                        recorder._session_tickers.add(ticker)
            except:
                pass
        
        existing_count = len(recorder._active_tickers) + len(recorder._session_tickers)
        if existing_count > 0:
            if not recorder._recording_active:
                logger.info(f"Found existing positions/orders ({existing_count}) -> START recording")
                recorder._recording_active = True
                recorder._recording_start_time = datetime.now()
                recorder._start_recording_flow(
                    "+".join(sorted(recorder._session_tickers)) or "unknown",
                    "unknown"
                )
        else:
            logger.info("No existing positions or orders found")
        
        # Simple watchdog - check positions periodically
        async def rest_watchdog():
            while True:
                await asyncio.sleep(2)
                try:
                    if not client:
                        continue
                    
                    # Check if any positions exist
                    has_positions = False
                    total_positions = 0
                    for conn in active_connections:
                        pos_data = await client.get_positions(conn["Id"])
                        positions = pos_data.get("positions", [])
                        total_positions += len(positions)
                        if positions:
                            has_positions = True
                            logger.debug(f"Positions on {conn['Name']}: {len(positions)}")
                    
                    logger.info(f"📊 Total positions: {total_positions}, recording_active={recorder._recording_active}")
                    
                    # Check active orders too
                    total_orders = 0
                    for conn in active_connections:
                        try:
                            orders_data = await client.get_orders(conn["Id"])
                            orders = orders_data.get("orders", [])
                            total_orders += len(orders)
                        except:
                            pass
                    
                    logger.info(f"📊 Positions: {total_positions}, Orders: {total_orders}")
                    
                    if not has_positions and recorder._recording_active:
                        # Only stop if no orders either
                        if total_orders == 0:
                            suffix = "" if recorder._had_position_opened else "_NOFill"
                            logger.warning("⚠️ No positions and no orders - stopping recording!")
                            tickers_str = "+".join(sorted(recorder._session_tickers)) if recorder._session_tickers else "unknown"
                            recorder._recording_active = False
                            recorder._stop_recording_flow(tickers_str, "unknown", 0, suffix)
                except Exception as e:
                    logger.debug(f"Watchdog error: {e}")
        
        @socket.on("position_update")
        def on_position(data):
            # ЛОГИРОВАНИЕ СЫРЫХ ДАННЫХ
            logger.info(f"RAW EVENT: {data}")
            
            ticker = data.get("ticker", "")
            size = float(data.get("size", 0))
            side = data.get("side", "Buy")
            connection_id = data.get("connectionId", 0)
            status = data.get("status", "")
            
            # Нормализуем размер
            if size < 0:
                side = "Short"
                size = abs(size)
            
            # Simple handler - just pass to recorder
            logger.info(f"Position: {ticker} {side} size={size}")
            
            # Check status - Closed means position is closed even if size != 0
            is_closed = status and status.lower() == "closed"
            if is_closed:
                size = 0  # Force close
            
            recorder.handle_position_event(ticker, size, side, 0.0)
        
        @socket.on("order_update")
        def on_order(data):
            logger.info(f"🐞 ORDER_UPDATE: {data}")
            logger.info(f"🐞 All fields: key={data.keys()}")
            
            ticker = data.get("ticker", "")
            order_id = str(data.get("orderId", data.get("order_id", "")))
            status = data.get("status", "")
            side = data.get("side", "Buy")
            order_type = data.get("type", "Limit")
            
            recorder.handle_order_event(ticker, order_id, status, side, order_type)
        
        logger.info("Listening for position updates...")
        logger.info("Press Ctrl+C to stop")
        
        # Запускаем watchdog параллельно
        watchdog = asyncio.create_task(rest_watchdog())
        
        try:
            await socket.listen_forever()
        finally:
            watchdog.cancel()
        
        await client.close()
    
    try:
        asyncio.run(run_with_metascalp())
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        # Принудительная остановка записи при выходе
        if recorder._recording_active:
            logger.warning("⚠️ Recording active on exit! Stopping recording...")
            try:
                recorder.obs_controller.stop_recording()
            except Exception:
                pass
        
        # Cleanup
        if recorder.obs_controller.connected:
            try:
                recorder.obs_controller.client.disconnect()
            except Exception:
                pass
        logger.info("Application terminated")
