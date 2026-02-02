import os
import time
import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler


# Create logs directory
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)


def setup_logger(name: str = 'travian_bot', log_file: str = None) -> logging.Logger:
    """
    Set up a logger with both file and console output.

    Args:
        name: Logger name
        log_file: Optional specific log file name

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )

    # File handler - rotates at 5MB, keeps 5 backups
    if not log_file:
        log_file = f"{name}_{datetime.now().strftime('%Y%m%d')}.log"

    file_path = os.path.join(LOGS_DIR, log_file)
    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=5*1024*1024,  # 5MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


class Logger:
    """Simple logger wrapper with emoji indicators for console"""

    _logger = None
    _instance = None

    @classmethod
    def get_instance(cls, name: str = 'travian_bot'):
        if cls._instance is None:
            cls._instance = cls(name)
        return cls._instance

    def __init__(self, name: str = 'travian_bot'):
        self._logger = setup_logger(name)

    @classmethod
    def _get_logger(cls):
        if cls._logger is None:
            cls._logger = setup_logger()
        return cls._logger

    @classmethod
    def debug(cls, message: str):
        cls._get_logger().debug(message)

    @classmethod
    def info(cls, message: str):
        cls._get_logger().info(f"ℹ️  {message}")

    @classmethod
    def success(cls, message: str):
        cls._get_logger().info(f"✓ {message}")

    @classmethod
    def warning(cls, message: str):
        cls._get_logger().warning(f"⚠️  {message}")

    @classmethod
    def error(cls, message: str):
        cls._get_logger().error(f"✗ {message}")

    @classmethod
    def critical(cls, message: str):
        cls._get_logger().critical(f"🔥 {message}")

    @classmethod
    def action(cls, message: str):
        """Log an action being performed"""
        cls._get_logger().info(f"🔧 {message}")

    @classmethod
    def resource(cls, message: str):
        """Log resource updates"""
        cls._get_logger().info(f"📊 {message}")

    @classmethod
    def military(cls, message: str):
        """Log military actions"""
        cls._get_logger().info(f"⚔️  {message}")

    @classmethod
    def ai(cls, message: str):
        """Log AI-related actions"""
        cls._get_logger().info(f"🤖 {message}")

    @classmethod
    def log_separator(cls, title: str = ""):
        """Log a visual separator"""
        if title:
            cls._get_logger().info(f"{'='*20} {title} {'='*20}")
        else:
            cls._get_logger().info("=" * 50)


class ActionLogger:
    """Specialized logger for tracking bot actions"""

    def __init__(self, name: str = 'actions'):
        self.logger = setup_logger(f'travian_{name}', f'actions_{datetime.now().strftime("%Y%m%d")}.log')

    def log_upgrade(self, building_name: str, from_level: int, to_level: int, success: bool):
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"UPGRADE | {status} | {building_name} | L{from_level} -> L{to_level}")

    def log_train(self, troop_type: str, amount: int, success: bool):
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"TRAIN | {status} | {troop_type} x{amount}")

    def log_attack(self, target_x: int, target_y: int, troops: dict, success: bool):
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"ATTACK | {status} | ({target_x},{target_y}) | {troops}")

    def log_resources(self, resources: dict, production: dict):
        self.logger.info(f"RESOURCES | wood={resources.get('wood',0)} clay={resources.get('clay',0)} iron={resources.get('iron',0)} crop={resources.get('crop',0)}")
        self.logger.info(f"PRODUCTION | wood={production.get('wood',0)}/h clay={production.get('clay',0)}/h iron={production.get('iron',0)}/h crop={production.get('crop',0)}/h")

    def log_login(self, username: str, success: bool):
        status = "SUCCESS" if success else "FAILED"
        self.logger.info(f"LOGIN | {status} | {username}")

    def log_cycle(self, cycle_num: int, actions_taken: list):
        self.logger.info(f"CYCLE | #{cycle_num} | Actions: {', '.join(actions_taken) if actions_taken else 'None'}")

    def log_error(self, action: str, error: str):
        self.logger.error(f"ERROR | {action} | {error}")

    def log_incoming_attack(self, attacker: str, arrival_time: str):
        self.logger.warning(f"INCOMING | {attacker} | Arrival: {arrival_time}")


def format_time(seconds: int) -> str:
    """Format seconds into human-readable time"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def parse_travian_time(time_str: str) -> int:
    """Parse Travian time format to seconds"""
    try:
        parts = time_str.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
    except:
        return 0


def calculate_arrival_time(duration_seconds: int) -> datetime:
    """Calculate arrival time from duration"""
    return datetime.now() + timedelta(seconds=duration_seconds)


def random_delay(min_seconds: float = 0.5, max_seconds: float = 2.0):
    """Add a random delay to avoid detection"""
    import random
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


def safe_int(value, default: int = 0) -> int:
    """Safely convert value to int"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    """Safely convert value to float"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
