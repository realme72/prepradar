"""Settings loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_PAGE_CHARS = 15_000  # trim very long pages to cap tokens per extraction call
