"""Settings loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/prepradar")
MAX_PAGE_CHARS = 15_000  # trim very long pages to cap tokens per extraction call

# cosine similarity at or above which two questions are the same question
# (picked from real pairs: true rewrites scored 0.93+, "MongoDB vs MySQL schema" 0.87)
DEDUPE_THRESHOLD = float(os.getenv("DEDUPE_THRESHOLD", "0.88"))
# Short tag names embed poorly ("Java" vs "JavaScript" 0.83, "Prod Debugging" vs
# "Production Troubleshooting" 0.73), so similarity alone can't decide tag merges:
# >= AUTO: merge; between CANDIDATE and AUTO: ask the LLM; below CANDIDATE: new tag.
TOPIC_AUTO_MERGE = float(os.getenv("TOPIC_AUTO_MERGE", "0.92"))
TOPIC_CANDIDATE = float(os.getenv("TOPIC_CANDIDATE", "0.70"))
