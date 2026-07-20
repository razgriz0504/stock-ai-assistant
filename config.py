import os
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # LLM API Keys
    gemini_api_key: str = ""
    openai_api_key: str = ""
    dashscope_api_key: str = ""

    # 飞书配置
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""

    # MiniMax
    minimax_api_key: str = ""

    # 数据源
    finnhub_api_key: str = ""

    # 默认 LLM 模型
    default_llm: str = "gemini/gemini-3.1-pro-preview"

    # 图表临时文件目录
    charts_dir: str = "./charts"

    # 富途 OpenD（只读数据源，代码层面禁止下单）
    futu_enabled: bool = False
    futu_opend_host: str = "127.0.0.1"
    futu_opend_port: int = 11111
    futu_trd_env: str = "SIMULATE"   # SIMULATE / REAL（仅查询）
    futu_trd_market: str = "US"      # US / HK / CN

    # 账户体系 / JWT
    jwt_secret: str = ""                # 生产必填；openssl rand -hex 32
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7
    # 首个 admin 播种（users 表为空时生效，后续忽略）
    initial_admin_username: str = "admin"
    initial_admin_password: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    def setup_llm_env(self):
        """将 API Key 设置到环境变量中，供 LiteLLM 读取"""
        if self.gemini_api_key:
            os.environ["GEMINI_API_KEY"] = self.gemini_api_key
        if self.openai_api_key:
            os.environ["OPENAI_API_KEY"] = self.openai_api_key
        if self.dashscope_api_key:
            os.environ["DASHSCOPE_API_KEY"] = self.dashscope_api_key
        if self.minimax_api_key:
            os.environ["MINIMAX_API_KEY"] = self.minimax_api_key


settings = Settings()
settings.setup_llm_env()
