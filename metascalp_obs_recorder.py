"""
MetaScalp SDK + OBS Studio Video Recording Automation

This script monitors trading positions via MetaScalp SDK and controls
OBS Studio recording based on position open/close events.
"""

import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from dotenv import load_dotenv
from obswebsocket import obsws, requests

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PositionInfo:
    """Stores information about the current trading position."""
    ticker: str = ""
    side: str = ""  # "LONG" or "SHORT"
    entry_time: Optional[datetime] = None
    entry_pnl: float = 0.0
    is_open: bool = False
    
    def reset(self):
        """Reset position info to initial state."""
        self.ticker = ""
        self.side = ""
        self.entry_time = None
        self.entry_pnl = 0.0
        self.is_open = False


@dataclass
class TradeSession:
    """Tracks a complete trade session from entry to full exit."""
    ticker: str = ""
    side: str = ""
    entry_time: Optional[datetime] = None
    total_pnl: float = 0.0
    is_recording: bool = False
    last_position_size: float = 0.0


class OBSController:
    """Controls OBS Studio via WebSocket connection."""
    
    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.ws: Optional[obsws] = None
        self.connected = False
        
    def connect(self) -> bool:
        """Establish connection to OBS WebSocket."""
        try:
            if self.ws:
                try:
                    self.ws.disconnect()
                except Exception:
                    pass
            
            self.ws = obsws(self.host, self.port, self.password)
            self.ws.connect()
            self.connected = True
            logger.info(f"Connected to OBS at {self.host}:{self.port}")
            return True
        except Exception as e:
            self.connected = False
            logger.error(f"Failed to connect to OBS: {e}")
            return False
    
    def ensure_connected(self) -> bool:
        """Ensure connection is active, reconnect if needed."""
        if not self.connected or not self.ws:
            return self.connect()
        
        try:
            # Test connection with a simple request
            self.ws.call(requests.GetStatus())
            return True
        except Exception as e:
            logger.warning(f"OBS connection lost: {e}")
            self.connected = False
            return self.connect()
    
    def is_recording(self) -> bool:
        """Check if OBS is currently recording."""
        if not self.ensure_connected():
            return False
        
        try:
            result = self.ws.call(requests.GetRecordStatus())
            return result.datain.get('outputActive', False)
        except Exception as e:
            logger.error(f"Error checking record status: {e}")
            return False
    
    def start_recording(self) -> bool:
        """Start recording in OBS."""
        if not self.ensure_connected():
            return False
        
        if self.is_recording():
            logger.info("Recording is already active")
            return True
        
        try:
            self.ws.call(requests.StartRecord())
            logger.info("Recording started")
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False
    
    def stop_recording(self) -> bool:
        """Stop recording in OBS."""
        if not self.ensure_connected():
            return False
        
        if not self.is_recording():
            logger.info("Recording is not active")
            return True
        
        try:
            self.ws.call(requests.StopRecord())
            logger.info("Recording stopped")
            return True
        except Exception as e:
            logger.error(f"Failed to stop recording: {e}")
            return False
    
    def get_output_directory(self) -> Optional[str]:
        """Get the directory where OBS saves recordings."""
        if not self.ensure_connected():
            return None
        
        try:
            result = self.ws.call(requests.GetProfileParameter(parameter="RecFilePath"))
            path = result.datain.get('parameterValue', '')
            if path:
                return path
        except Exception as e:
            logger.error(f"Error getting output directory: {e}")
        
        # Fallback to default paths
        default_paths = [
            Path.home() / "Videos",
            Path.home() / "Desktop",
            Path.cwd() / "recordings"
        ]
        for p in default_paths:
            if p.exists():
                return str(p)
        
        return None


class MetaScalpPositionTracker:
    """
    Tracks position changes via MetaScalp SDK events.
    
    This class implements event-driven logic to detect position
    openings and closings, handling partial closes correctly.
    """
    
    def __init__(self):
        self.current_position: PositionInfo = PositionInfo()
        self.trade_session: TradeSession = TradeSession()
        self._last_known_size: float = 0.0
        self._accumulated_pnl: float = 0.0
        
    def process_position_update(self, ticker: str, size: float, side: str, realized_pnl: float = 0.0):
        """
        Process a position update from MetaScalp SDK.
        
        Args:
            ticker: Trading symbol (e.g., "BTCUSDT")
            size: Current position size (absolute value)
            side: Position side ("Buy"/"Long" or "Sell"/"Short")
            realized_pnl: Realized PnL from this update
        """
        normalized_side = self._normalize_side(side)
        
        # Detect position opening (size changed from 0 to > 0)
        if self._last_known_size == 0 and size > 0:
            self._on_position_open(ticker, size, normalized_side)
        
        # Accumulate PnL for partial closes
        if realized_pnl != 0:
            self._accumulated_pnl += realized_pnl
            logger.info(f"Accumulated PnL: {self._accumulated_pnl:.2f} (this update: {realized_pnl:.2f})")
        
        # Detect position closing (size changed to 0)
        if self._last_known_size > 0 and size == 0:
            self._on_position_close(ticker, normalized_side)
        
        self._last_known_size = size
    
    def _normalize_side(self, side: str) -> str:
        """Normalize side string to LONG or SHORT."""
        side_upper = side.upper()
        if side_upper in ("BUY", "LONG"):
            return "LONG"
        elif side_upper in ("SELL", "SHORT"):
            return "SHORT"
        else:
            logger.warning(f"Unknown side '{side}', defaulting to LONG")
            return "LONG"
    
    def _on_position_open(self, ticker: str, size: float, side: str):
        """Handle position opening event."""
        self.current_position.ticker = ticker
        self.current_position.side = side
        self.current_position.entry_time = datetime.now()
        self.current_position.is_open = True
        self._accumulated_pnl = 0.0  # Reset accumulated PnL for new position
        
        self.trade_session.ticker = ticker
        self.trade_session.side = side
        self.trade_session.entry_time = datetime.now()
        self.trade_session.total_pnl = 0.0
        self.trade_session.is_recording = False
        
        logger.info(f"Position opened: {ticker} {side} at {self.current_position.entry_time}")
    
    def _on_position_close(self, ticker: str, side: str):
        """Handle position closing event (full close)."""
        self.trade_session.total_pnl = self._accumulated_pnl
        
        logger.info(
            f"Position closed: {ticker} {side}, "
            f"Total PnL: {self.trade_session.total_pnl:.2f}"
        )
        
        # Reset for next position
        self.current_position.reset()
        self._last_known_size = 0.0


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
        
        # Callbacks for OBS control
        self._on_record_start_callback = None
        self._on_record_stop_callback = None
        
    def set_callbacks(self, on_start=None, on_stop=None):
        """Set callbacks for recording events."""
        self._on_record_start_callback = on_start
        self._on_record_stop_callback = on_stop
    
    def handle_position_event(self, ticker: str, size: float, side: str, realized_pnl: float = 0.0):
        """
        Handle a position update event from MetaScalp SDK.
        
        This is the main entry point for integrating with MetaScalp SDK.
        Call this method whenever you receive a position update from the SDK.
        
        Args:
            ticker: Trading symbol
            size: Current position size
            side: Position side
            realized_pnl: Realized PnL from this update
        """
        previous_state = self.position_tracker.current_position.is_open
        
        # Process the position update
        self.position_tracker.process_position_update(ticker, size, side, realized_pnl)
        
        current_state = self.position_tracker.current_position.is_open
        
        # Detect transition: No position -> Position opened
        if not previous_state and current_state:
            self._start_recording_flow(
                ticker,
                self.position_tracker.current_position.side
            )
        
        # Detect transition: Position -> No position (full close)
        if previous_state and not current_state:
            self._stop_recording_flow(
                ticker,
                self.position_tracker.trade_session.side,
                self.position_tracker.trade_session.total_pnl
            )
    
    def _start_recording_flow(self, ticker: str, side: str):
        """Execute the recording start flow."""
        logger.info(f"Starting recording for {ticker} {side}")
        
        if self.obs_controller.start_recording():
            self.position_tracker.trade_session.is_recording = True
            if self._on_record_start_callback:
                self._on_record_start_callback(ticker, side)
        else:
            logger.error("Failed to start recording - will retry on next event")
    
    def _stop_recording_flow(self, ticker: str, side: str, pnl: float):
        """Execute the recording stop and file rename flow."""
        logger.info(f"Stopping recording for {ticker} {side}, PnL: {pnl:.2f}")
        
        if self.obs_controller.stop_recording():
            self.position_tracker.trade_session.is_recording = False
            
            # Wait for file finalization
            logger.info("Waiting 2 seconds for file finalization...")
            time.sleep(2)
            
            # Rename the recorded file
            self._rename_last_recording(ticker, side, pnl)
            
            if self._on_record_stop_callback:
                self._on_record_stop_callback(ticker, side, pnl)
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


if __name__ == "__main__":
    # Initialize the recorder
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
        if recorder.obs_controller.connected:
            try:
                recorder.obs_controller.ws.disconnect()
            except Exception:
                pass
        logger.info("Application terminated")
