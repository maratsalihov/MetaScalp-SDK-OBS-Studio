"""
MetaScalp SDK + OBS Studio Video Recording Automation

This script monitors trading positions via MetaScalp SDK and controls
OBS Studio recording based on position open/close events.

Uses official MetaScalp SDK: https://github.com/MetaScalp/metascalp-sdk
WebSocket endpoint: ws://127.0.0.1:17845/
REST endpoint: http://127.0.0.1:17845/
"""

import os
import time
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from dotenv import load_dotenv

try:
    from obswebsocket import obsws, requests
    OBS_WEBSOCKET_AVAILABLE = True
except ImportError:
    OBS_WEBSOCKET_AVAILABLE = False
    obsws = None
    requests = None

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
    """Controls OBS Studio via WebSocket connection."""
    
    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.ws = None
        self.connected = False
    
    def _build_auth(self, salt: str, challenge: str) -> str:
        """Build authentication string for OBS WebSocket v5."""
        import hashlib
        import hmac
        import base64
        secret = hashlib.pbkdf2_hmac('sha256', self.password.encode(), base64.b64decode(salt), 60000)
        auth = hmac.new(base64.b64decode(challenge), secret, hashlib.sha256).digest()
        return base64.b64encode(auth).decode()
    
    def connect(self) -> bool:
        """Подключаемся к OBS - каждый раз новое соединение для каждой команды"""
        try:
            import websocket
            import json
            import hashlib
            import hmac
            import base64
            
            # Новое подключение для каждой команды
            ws = websocket.WebSocket(skip_utf8_validation=True)
            ws.settimeout(5)
            url = f"ws://{self.host}:{self.port}"
            ws.connect(url)
            
            # Hello
            hello = json.loads(ws.recv())
            obs_version = hello['d'].get('obsStudioVersion', 'unknown')
            
            # Auth - не используем пароль для локального подключения
            auth_str = None
            
            # Identify
            ws.send(json.dumps({
                "op": 1,
                "d": {"rpcVersion": 1, "authentication": auth_str}
            }))
            
            # Сохраняем соединение
            self.ws = ws
            self.connected = True
            logger.info(f"Connected to OBS {obs_version}")
            return True
            
        except Exception as e:
            self.connected = False
            logger.error(f"OBS connection failed: {e}")
            return False
    
    def ensure_connected(self) -> bool:
        """Для каждой операции создаем НОВОЕ подключение"""
        if self.connected and self.ws:
            try:
                # Просто тестируем - пингуем
                return True
            except:
                pass
        return self.connect()
    
    def is_recording(self) -> bool:
        """Check if OBS is currently recording."""
        if not self.ensure_connected():
            return False
        
        try:
            import json
            self.ws.send(json.dumps({
                "op": 6,
                "d": {"requestType": "GetRecordStatus", "requestId": "1"}
            }))
            # Ждём ответ (op:7)
            import time
            time.sleep(0.3)
            response = self.ws.recv()
            if response:
                data = json.loads(response)
                record_status = data.get('d', {}).get('responseData', {}).get('outputActive', False)
                logger.info(f"Record status: {record_status}")
                return record_status
        except Exception as e:
            logger.error(f"Error checking record status: {e}")
            self.connected = False
        return False
    
    def start_recording(self) -> bool:
        """Start recording in OBS."""
        try:
            import websocket
            import json
            import hashlib
            import hmac
            import base64
            
            # Новое подключение
            ws = websocket.WebSocket(skip_utf8_validation=True)
            ws.settimeout(5)
            ws.connect(f"ws://{self.host}:{self.port}")
            
            # Hello
            hello = json.loads(ws.recv())
            
            # Auth - не используем пароль для локального подключения
            auth_str = None
            
            # Identify
            ws.send(json.dumps({'op': 1, 'd': {'rpcVersion': 1, 'authentication': auth_str}}))
            
            # Ждём Identified (op:2)
            identified = ws.recv()
            if identified:
                ident_data = json.loads(identified)
                logger.info(f"Identified: {ident_data}")
                if ident_data.get('op') == 2:
                    if not ident_data.get('d', {}).get('requestStatus', {}).get('result', False):
                        logger.error("Identify failed")
                        ws.close()
                        return False
            
            # StartRecord
            ws.send(json.dumps({'op': 6, 'd': {'requestType': 'StartRecord', 'requestId': '2'}}))
            
            # Ждём ответ (op:7)
            response = ws.recv()
            if response:
                resp_data = json.loads(response)
                logger.info(f"StartRecord response: {resp_data}")
                result = resp_data.get('d', {}).get('requestStatus', {}).get('result', False)
                if result:
                    logger.info("Recording started")
                    ws.close()
                    return True
                else:
                    logger.error(f"StartRecord failed: {resp_data}")
                    ws.close()
                    return False
            
            ws.close()
            return False
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False
    
    def stop_recording(self) -> bool:
        """Stop recording in OBS."""
        try:
            import websocket
            import json
            import hashlib
            import hmac
            import base64
            
            # Новое подключение
            ws = websocket.WebSocket(skip_utf8_validation=True)
            ws.settimeout(5)
            ws.connect(f"ws://{self.host}:{self.port}")
            
            # Hello
            hello = json.loads(ws.recv())
            
            # Auth - не используем пароль для локального подключения
            auth_str = None
            
            # Identify
            ws.send(json.dumps({'op': 1, 'd': {'rpcVersion': 1, 'authentication': auth_str}}))
            
            # Ждём Identified (op:2)
            identified = ws.recv()
            if identified:
                ident_data = json.loads(identified)
                logger.info(f"Identified: {ident_data}")
                if ident_data.get('op') == 2:
                    if not ident_data.get('d', {}).get('requestStatus', {}).get('result', False):
                        logger.error("Identify failed")
                        ws.close()
                        return False
            
            # StopRecord
            ws.send(json.dumps({'op': 6, 'd': {'requestType': 'StopRecord', 'requestId': '2'}}))
            
            # Ждём ответ (op:7)
            response = ws.recv()
            if response:
                resp_data = json.loads(response)
                logger.info(f"StopRecord response: {resp_data}")
                result = resp_data.get('d', {}).get('requestStatus', {}).get('result', False)
                if result:
                    logger.info("Recording stopped")
                    ws.close()
                    return True
                else:
                    logger.error(f"StopRecord failed: {resp_data}")
                    ws.close()
                    return False
            
            ws.close()
            return False
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return False
    
    def get_output_directory(self) -> Optional[str]:
        """Get the directory where OBS saves recordings."""
        # Fallback to environment variable or common paths
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
    
    def __init__(self):
        # Configuration from environment
        self.obs_host = os.getenv("OBS_HOST", "localhost")
        self.obs_port = int(os.getenv("OBS_PORT", "4455"))
        self.obs_password = os.getenv("OBS_PASSWORD", "")
        self.obs_video_path = os.getenv("OBS_VIDEO_PATH", "")
        self.filename_template = os.getenv(
            "FILENAME_TEMPLATE",
            "[{date}_{time}] {ticker}_{side}_PnL_{pnl}.mp4"
        )
        
        # Initialize components
        self.obs_controller = OBSController(
            self.obs_host, 
            self.obs_port, 
            self.obs_password
        )
        self.position_tracker = MetaScalpPositionTracker()
        
        # Track which tickers are currently being recorded
        self._recording_tickers: set = set()
        
    def handle_position_event(self, ticker: str, size: float, side: str, realized_pnl: float = 0.0):
        """
        Handle a position update event from MetaScalp SDK.
        
        This is the main entry point for integrating with MetaScalp SDK.
        Call this method whenever you receive a position update from the SDK.
        
        Args:
            ticker: Trading symbol
            size: Current position size
            side: Position side ("Buy"/"Sell" or "Long"/"Short")
            realized_pnl: Realized PnL from this update
        """
        # Create data dict in SDK format
        data = {
            "ticker": ticker,
            "size": size,
            "side": side,
            "realizedPnl": realized_pnl
        }
        
        # Get state before processing
        session_before = self.position_tracker.get_active_session()
        was_recording = session_before.is_recording if session_before else False
        
        # Process the position update through tracker
        self.position_tracker.process_position_update(data)
        
        # Get state after processing
        session_after = self.position_tracker.get_active_session()
        
        # Detect: New position opened -> Start recording
        if session_after and not was_recording and session_after.ticker == ticker:
            self._start_recording_flow(ticker, session_after.side)
        
        # Detect: Position fully closed -> Stop recording
        elif was_recording and session_after and not self.position_tracker.has_open_positions():
            self._stop_recording_flow(ticker, session_after.side, session_after.total_pnl)
    
    def _start_recording_flow(self, ticker: str, side: str):
        """Execute the recording start flow."""
        logger.info(f"Starting recording for {ticker} {side}")
        
        if self.obs_controller.start_recording():
            session = self.position_tracker.get_active_session()
            if session:
                session.is_recording = True
            # Callback removed
                
        else:
            logger.error("Failed to start recording - will retry on next event")
    
    def _stop_recording_flow(self, ticker: str, side: str, pnl: float):
        """Execute the recording stop and file rename flow."""
        logger.info(f"Stopping recording for {ticker} {side}, PnL: {pnl:.2f}")
        
        if self.obs_controller.stop_recording():
            session = self.position_tracker.get_active_session()
            if session:
                session.is_recording = False
            
            # Wait for file finalization
            logger.info("Waiting 2 seconds for file finalization...")
            time.sleep(2)
            
            # Rename the recorded file
            self._rename_last_recording(ticker, side, pnl)
            
            # Callback removed
                
        else:
            logger.error("Failed to stop recording")
    
    def _rename_last_recording(self, ticker: str, side: str, pnl: float):
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
            logger.error(f"Video directory does not exist: {video_path}")
            return
        
        # Find the most recent .mp4 or .mkv file
        video_files = []
        for ext in ('*.mp4', '*.mkv'):
            video_files.extend(video_path.glob(ext))
        
        if not video_files:
            logger.warning("No video files found to rename")
            return
        
        # Sort by modification time and get the latest
        latest_file = max(video_files, key=lambda f: f.stat().st_mtime)
        
        # Generate new filename
        now = datetime.now()
        new_name = self.filename_template.format(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H-%M"),
            ticker=ticker,
            side=side,
            pnl=self._format_pnl(pnl)
        )
        
        new_path = video_path / new_name
        
        # Handle duplicate filenames
        if new_path.exists():
            timestamp = int(time.time())
            new_path = video_path / f"{timestamp}_{new_name}"
        
        try:
            latest_file.rename(new_path)
            logger.info(f"Renamed recording: {latest_file.name} -> {new_path.name}")
        except Exception as e:
            logger.error(f"Failed to rename file: {e}")
    
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
        ticker = event_data.get('ticker', '')
        size = float(event_data.get('size', 0))
        side = event_data.get('side', '')
        realized_pnl = float(event_data.get('realized_pnl', 0))
        
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
                
                # Subscribe to position updates
                self.socket.subscribe(self.connection_id)
                logger.info(f"Subscribed to position updates for connection {self.connection_id}")
                
                # Register position update handler
                @self.socket.on("position_update")
                def on_position(data):
                    self._handle_position_event(data)
                
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
            ticker = data.get("ticker", "")
            size = float(data.get("size", 0))
            side = data.get("side", "Buy")
            realized_pnl = float(data.get("realizedPnl", 0) or 0)
            
            logger.debug(f"Position update: {ticker} size={size} side={side} realizedPnl={realized_pnl}")
            
            self.recorder.handle_position_event(ticker, size, side, realized_pnl)
            
        except Exception as e:
            logger.error(f"Error processing position event: {e}", exc_info=True)
    
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
            
            try:
                # Start listening for WebSocket messages
                await self.socket.listen_forever()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self._running = False
            
            if not self._running:
                break
            
            # Reconnect after disconnection
            logger.info("Connection lost. Reconnecting in 5s...")
            await asyncio.sleep(5)
    
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
                recorder.obs_controller.ws.disconnect()
            except Exception:
                pass
        
        logger.info("Application terminated")


if __name__ == "__main__":
    import asyncio
    from metascalp import MetaScalpClient, MetaScalpSocket
    
    # Инициализируем рекордер
    recorder = TradingRecorder()
    
    logger.info("=" * 60)
    logger.info("MetaScalp + OBS Recording Automation")
    logger.info("=" * 60)
    logger.info(f"OBS Host: {recorder.obs_host}:{recorder.obs_port}")
    logger.info(f"Video Path: {recorder.obs_video_path or '(auto-detect)'}")
    logger.info(f"Filename Template: {recorder.filename_template}")
    logger.info("=" * 60)
    
    logger.info("Testing OBS connection...")
    if recorder.obs_controller.connect():
        logger.info("OBS connection successful!")
    else:
        logger.warning("Could not connect to OBS. Ensure OBS is running with WebSocket enabled.")
    
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
        
        # Подписываемся на обновления позиций для КАЖДОГО активного подключения
        for conn in active_connections:
            conn_id = conn["Id"]
            conn_name = conn["Name"]
            socket.subscribe(conn_id)
            logger.info(f"Subscribed to position updates for {conn_name}")
        
        @socket.on("position_update")
        def on_position(data):
            ticker = data.get("ticker", "")
            size = float(data.get("size", 0))
            side = data.get("side", "Buy")
            realized_pnl = float(data.get("realizedPnl", 0) or 0)
            
            logger.info(f"Position: {ticker} {side} size={size} pnl={realized_pnl}")
            recorder.handle_position_event(ticker, size, side, realized_pnl)
        
        logger.info("Listening for position updates...")
        logger.info("Press Ctrl+C to stop")
        
        await socket.listen_forever()
    
    try:
        asyncio.run(run_with_metascalp())
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        if recorder.obs_controller.ws:
            try:
                recorder.obs_controller.ws.close()
            except Exception:
                pass
        logger.info("Application terminated")
    recorder = TradingRecorder()
    
    # Log configuration
    logger.info("=" * 60)
    logger.info("MetaScalp + OBS Recording Automation")
    logger.info("=" * 60)
    logger.info(f"OBS Host: {recorder.obs_host}:{recorder.obs_port}")
    logger.info(f"Video Path: {recorder.obs_video_path or '(auto-detect)'}")
    logger.info(f"Filename Template: {recorder.filename_template}")
    logger.info("=" * 60)
    
    # Test OBS connection
    logger.info("Testing OBS connection...")
    if recorder.obs_controller.connect():
        logger.info("OBS connection successful!")
        
        # Check current recording status
        is_rec = recorder.obs_controller.is_recording()
        logger.info(f"Current recording status: {'ACTIVE' if is_rec else 'INACTIVE'}")
    else:
        logger.warning("Could not connect to OBS. Ensure OBS is running with WebSocket enabled.")
        logger.warning("The script will continue and retry connections as needed.")
    
    logger.info("")
    logger.info("Starting event processing...")
    logger.info("Press Ctrl+C to stop")
    logger.info("")
    
    try:
        # Run demo mode (replace with actual SDK integration in production)
        recorder.run_demo_loop(duration=30)
        
        # For production use with real MetaScalp SDK, replace the above with:
        # 
        # from metascalp_sdk import MetaScalpClient  # hypothetical import
        # 
        # client = MetaScalpClient(api_key=..., secret=...)
        # handler = create_metascalp_event_handler(recorder)
        # client.subscribe_position_updates(handler)
        # client.run()  # or appropriate method to start event loop
        
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
    finally:
        # Cleanup
        if recorder.obs_controller.ws:
            try:
                recorder.obs_controller.ws.close()
            except Exception:
                pass
        logger.info("Application terminated")
