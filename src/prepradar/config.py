"""Settings loaded from environment / .env."""
import os

from dotenv import load_dotenv

load_dotenv()

# Which AI provider reads the pages: OpenAI, or Google's Gemini through its
# OpenAI-compatible endpoint (same client, same calls). LLM_PROVIDER forces one; otherwise
# it's OpenAI when its key is set, else Gemini.
LLM_PROVIDER = os.getenv("LLM_PROVIDER") or ("openai" if os.getenv("OPENAI_API_KEY") or not os.getenv("GEMINI_API_KEY")
                                             else "gemini")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
_GEMINI = LLM_PROVIDER == "gemini"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gemini-3.5-flash" if _GEMINI else "gpt-4o-mini")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/prepradar")
MAX_PAGE_CHARS = 15_000  # one question-extraction call reads this much of a page
MAX_CHUNKS = 4           # longer pages are read in up to this many chunks (60k chars)
EXPERIENCE_CHARS = 60_000  # the experience call reads a page in one go, so a story isn't split
# Pages read at once (fetch + AI calls). Saving stays one page at a time, so duplicate
# and tag checks see everything saved before them. One at a time took ~70s a page.
INGEST_WORKERS = int(os.getenv("INGEST_WORKERS", "3" if _GEMINI else "6"))

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
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.5-flash" if _GEMINI else "gpt-5.4-mini")
# With no reasoning the classifier flipped on borderline pages (an AI-written summary
# read as candidate reviews 2 runs in 5); "low" was stable, "medium" no better.
JUDGE_REASONING = {"effort": os.getenv("JUDGE_REASONING", "low")}
# Gemini's free tier allows only a few requests a minute, so fewer pages at once and a
# retry for brief overloads (503); rate limits (429) are handled in extractor.parse.
LLM_RETRIES = int(os.getenv("LLM_RETRIES", "3" if _GEMINI else "2"))
# Requests per minute across all threads; 0 = no pacing. A burst of parallel calls was
# rejected (429) by Gemini's free tier even with retries. Raise it on a paid key.
LLM_RPM = float(os.getenv("LLM_RPM", "8" if _GEMINI else "0"))
# Short tag names embed poorly ("Java" vs "JavaScript" 0.83, "Prod Debugging" vs
# "Production Troubleshooting" 0.73), so similarity alone can't decide tag merges:
# >= AUTO: merge; between CANDIDATE and AUTO: ask the LLM; below CANDIDATE: new tag.
TOPIC_AUTO_MERGE = float(os.getenv("TOPIC_AUTO_MERGE", "0.92"))
TOPIC_CANDIDATE = float(os.getenv("TOPIC_CANDIDATE", "0.70"))
