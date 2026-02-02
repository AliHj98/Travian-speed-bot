import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class BotConfig(BaseModel):
    """Bot configuration settings"""

    # Travian Settings
    server: str = Field(default_factory=lambda: os.getenv('TRAVIAN_SERVER', 'ts1.travian-speed.com'))
    username: str = Field(default_factory=lambda: os.getenv('TRAVIAN_USERNAME', ''))
    password: str = Field(default_factory=lambda: os.getenv('TRAVIAN_PASSWORD', ''))

    # AI Settings
    anthropic_api_key: str = Field(default_factory=lambda: os.getenv('ANTHROPIC_API_KEY', ''))

    # Bot Behavior
    headless: bool = Field(default_factory=lambda: os.getenv('HEADLESS', 'false').lower() == 'true')
    check_interval: int = Field(default_factory=lambda: int(os.getenv('CHECK_INTERVAL', '60')))
    auto_build: bool = Field(default_factory=lambda: os.getenv('AUTO_BUILD', 'true').lower() == 'true')
    auto_train_troops: bool = Field(default_factory=lambda: os.getenv('AUTO_TRAIN_TROOPS', 'true').lower() == 'true')
    auto_upgrade: bool = Field(default_factory=lambda: os.getenv('AUTO_UPGRADE', 'true').lower() == 'true')

    # Paths
    screenshots_dir: str = 'screenshots'
    session_data_dir: str = 'session_data'

    def validate_credentials(self) -> bool:
        """Check if required credentials are set"""
        if not self.username or not self.password:
            return False
        return True

    @property
    def base_url(self) -> str:
        """Get the base URL for the Travian server"""
        return f"https://{self.server}"


config = BotConfig()
