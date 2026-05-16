"""
IncidentIQ - Central Configuration
All secrets loaded from environment variables. Never hardcode credentials.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

# Load .env early so AWS credentials are available before boto3 initialises
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — rely on env vars being set externally


@dataclass
class BedrockConfig:
    region: str = field(default_factory=lambda: os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))

    # ── Priority model stack (in order) ──────────────────────────────────────
    # P1 — Primary reasoning, RCA, orchestration
    qwen3_32b: str = "qwen.qwen3-32b-v1:0"
    # P2 — Deep analysis, critical incident validation
    deepseek_v3: str = "deepseek.v3-v1:0"
    # P3 — Code intelligence, PR generation, code fixes
    qwen3_coder: str = "qwen.qwen3-coder-30b-a3b-v1:0"
    # P4 — Fast responses, ChatOps, streaming summaries
    kimi_k2: str = "moonshotai.kimi-k2.5"

    # Embeddings — Titan V2 (still used for vector store, no replacement needed)
    titan_embeddings: str = "amazon.titan-embed-text-v2:0"

    # Convenience aliases used throughout the codebase
    @property
    def primary(self) -> str:
        """P1: General reasoning, RCA, orchestration → Qwen3 32B"""
        return self.qwen3_32b

    @property
    def deep_analysis(self) -> str:
        """P2: Deep incident analysis, critical validation → DeepSeek V3"""
        return self.deepseek_v3

    @property
    def code_model(self) -> str:
        """P3: Code intelligence, PR generation → Qwen3 Coder"""
        return self.qwen3_coder

    @property
    def fast_model(self) -> str:
        """P4: Fast ChatOps, streaming, summaries → Kimi K2"""
        return self.kimi_k2


@dataclass
class DatabaseConfig:
    postgres_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "sqlite:///./incidentiq.db"
        )
    )
    redis_url: str = field(
        default_factory=lambda: os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    )


@dataclass
class VectorDBConfig:
    provider: str = field(default_factory=lambda: os.environ.get("VECTOR_DB_PROVIDER", "chroma"))
    chroma_path: str = field(
        default_factory=lambda: os.environ.get("CHROMA_PATH", "./data/chroma")
    )
    pinecone_api_key: Optional[str] = field(
        default_factory=lambda: os.environ.get("PINECONE_API_KEY")
    )
    pinecone_index: str = field(
        default_factory=lambda: os.environ.get("PINECONE_INDEX", "incidentiq")
    )
    collection_name: str = "incident_embeddings"
    embedding_dim: int = 1024  # Titan Embeddings V2


@dataclass
class GuardrailConfig:
    confidence_threshold: float = 0.70
    max_interjection_interval_seconds: int = 300  # 5 minutes
    require_human_approval_for: list = field(
        default_factory=lambda: [
            "production_deployment",
            "database_schema_change",
            "infrastructure_deletion",
            "permission_change",
            "customer_impacting_action",
        ]
    )
    advisory_only_mode: bool = True


@dataclass
class GitHubConfig:
    token: Optional[str] = field(default_factory=lambda: os.environ.get("GITHUB_TOKEN"))
    repo_owner: Optional[str] = field(default_factory=lambda: os.environ.get("GITHUB_REPO_OWNER"))
    repo_name: Optional[str] = field(default_factory=lambda: os.environ.get("GITHUB_REPO_NAME"))
    base_branch: str = "main"


@dataclass
class SlackConfig:
    bot_token: Optional[str] = field(default_factory=lambda: os.environ.get("SLACK_BOT_TOKEN"))
    signing_secret: Optional[str] = field(
        default_factory=lambda: os.environ.get("SLACK_SIGNING_SECRET")
    )
    incident_channel: str = field(
        default_factory=lambda: os.environ.get("SLACK_INCIDENT_CHANNEL", "#incidents")
    )


@dataclass
class AppConfig:
    bedrock: BedrockConfig = field(default_factory=BedrockConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    vector_db: VectorDBConfig = field(default_factory=VectorDBConfig)
    guardrails: GuardrailConfig = field(default_factory=GuardrailConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    log_level: str = field(default_factory=lambda: os.environ.get("LOG_LEVEL", "INFO"))
    environment: str = field(
        default_factory=lambda: os.environ.get("ENVIRONMENT", "development")
    )


# Singleton config instance
config = AppConfig()
