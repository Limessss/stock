"""应用配置。

通过环境变量或 .env 文件可覆盖默认值；默认情况下：
- 通达信原始数据：仓库外的 ../data/raw
- Parquet 缓存：    ../data/cache
- SQLite 数据库：    ../data/db/stockmodel.db
"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# 仓库根目录：curosr/
REPO_ROOT = Path(__file__).resolve().parents[3]
# 默认数据目录：与 curosr/ 同级的 data/
DEFAULT_DATA_DIR = REPO_ROOT.parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_prefix="STOCKMODEL_",
        extra="ignore",
    )

    # === 路径配置 ===
    data_dir: Path = DEFAULT_DATA_DIR
    raw_dir: Path | None = None         # 默认 data_dir / "raw"
    cache_dir: Path | None = None       # 默认 data_dir / "cache"
    db_dir: Path | None = None          # 默认 data_dir / "db"

    # === 服务配置 ===
    api_prefix: str = "/api"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # === 应用元数据 ===
    app_name: str = "A 股回测平台"
    app_version: str = "0.1.0"
    debug: bool = True

    # === 大模型（.env fallback；UI 配置优先见 settings_service）===
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout: float = 60.0

    # === 开盘啦可选增强数据源 ===
    # 默认关闭；开启后也只会由情绪周期的显式同步接口触发，不参与普通页面查询。
    kaipanla_enabled: bool = False
    kaipanla_user_id: str = ""
    kaipanla_token: str = ""
    kaipanla_device_id: str = ""
    kaipanla_version: str = "6.2.20.2"
    kaipanla_timeout: float = 15.0

    def model_post_init(self, __context) -> None:
        if self.raw_dir is None:
            self.raw_dir = self.data_dir / "raw"
        if self.cache_dir is None:
            self.cache_dir = self.data_dir / "cache"
        if self.db_dir is None:
            self.db_dir = self.data_dir / "db"
        # 确保目录存在
        for d in (self.data_dir, self.raw_dir, self.cache_dir, self.db_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def db_url(self) -> str:
        return f"sqlite:///{(self.db_dir / 'stockmodel.db').as_posix()}"


settings = Settings()
