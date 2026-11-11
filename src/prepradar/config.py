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
# Between this and DEDUPE_THRESHOLD the score can't decide: "debounce function" vs
# "what is debounce" (0.856) is a duplicate, "debug a failing API" vs "debug a slow
# API" (0.863) is not. Those pairs go to an LLM judge. No true duplicates seen below.
DEDUPE_JUDGE = float(os.getenv("DEDUPE_JUDGE", "0.80"))
# Model for judgement calls that run rarely (duplicate judge, recategorise), so they
# can afford more care than extraction. For the duplicate judge, gpt-4o-mini flipped between merging "kth largest" with
# "2nd largest" and missing "debounce function" = "what is debounce, implement it".
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-5.4-mini")
# Short tag names embed poorly ("Java" vs "JavaScript" 0.83, "Prod Debugging" vs
# "Production Troubleshooting" 0.73), so similarity alone can't decide tag merges:
# >= AUTO: merge; between CANDIDATE and AUTO: ask the LLM; below CANDIDATE: new tag.
TOPIC_AUTO_MERGE = float(os.getenv("TOPIC_AUTO_MERGE", "0.92"))
TOPIC_CANDIDATE = float(os.getenv("TOPIC_CANDIDATE", "0.70"))
