"""Who the interview was for: function -> role ladder, and what each function is asked.

Everything role-specific lives here (positions, categories, coverage targets, search
phrasing), so adding a function or a role is an edit to this file only.

    function   Engineering, Product, Sales, ...   (what department)
    position   SDE 2, Product Manager, Account Executive, ...   (a rung on that function's ladder)
    track      Backend, Frontend, ...   (engineering specialty only)

Managers are positions inside each ladder (Engineering Manager, Sales Manager), so an
engineering manager's system design and people questions stay under Engineering.
"""
import re
from dataclasses import dataclass, field

UNKNOWN = "Unknown"  # position not stated in the write-up


@dataclass(frozen=True)
class Function:
    positions: list[str]
    categories: list[str]       # categories questions for this function usually fall in
    core: list[str]             # what a candidate should expect to prepare; thin ones trigger searches
    search_terms: list[str]     # how candidates name these roles in post titles
    manager_core: list[str] = field(default_factory=lambda: ["People Management"])


ENGINEERING_CATEGORIES = [
    "DSA", "LLD", "HLD", "Backend", "Database", "Messaging & Streaming", "DevOps & Cloud", "Frontend",
    "Data", "ML/AI",
]

FUNCTIONS: dict[str, Function] = {
    "Engineering": Function(
        positions=["Intern", "SDE 1", "SDE 2", "SDE 3 / Senior", "Staff Engineer", "Principal Engineer",
                   "Engineering Manager"],
        categories=ENGINEERING_CATEGORIES,
        core=["DSA", "LLD", "HLD", "Backend", "Database", "Behavioral"],  # refined per track below
        search_terms=["software engineer", "SDE 2", "senior software engineer"],
    ),
    "Product": Function(
        positions=["APM", "Product Manager", "Senior Product Manager", "Group / Principal PM",
                   "Director of Product"],
        categories=["Product Sense", "Metrics & Experimentation", "Estimation", "Strategy", "Execution"],
        core=["Product Sense", "Metrics & Experimentation", "Estimation", "Behavioral"],
        search_terms=["product manager", "APM", "senior product manager"],
    ),
    "Data": Function(
        positions=["Data Analyst", "Business / BI Analyst", "Data Engineer", "Data Scientist",
                   "Analytics Manager"],
        categories=["Data", "Database", "Metrics & Experimentation", "ML/AI", "DSA"],
        core=["Data", "Database", "Behavioral"],
        search_terms=["data analyst", "data engineer", "data scientist"],
    ),
    "Design": Function(
        positions=["Product Designer", "Senior Product Designer", "UX Researcher", "Design Manager"],
        categories=["Portfolio & Critique", "Design Exercise", "Product Sense"],
        core=["Portfolio & Critique", "Design Exercise", "Behavioral"],
        search_terms=["product designer", "UX designer"],
    ),
    "Sales": Function(
        positions=["SDR / BDR", "Account Executive", "Enterprise AE", "Account Manager", "Sales Engineer",
                   "Sales Manager"],
        categories=["Sales Pitch & Role-play", "Pipeline & Negotiation", "Market & Product Knowledge"],
        core=["Sales Pitch & Role-play", "Pipeline & Negotiation", "Behavioral"],
        search_terms=["sales", "account executive", "business development"],
    ),
    "Marketing": Function(
        positions=["Marketing Associate", "Growth / Performance Marketer", "Product Marketing Manager",
                   "Content Marketer", "Marketing Manager"],
        categories=["Marketing Strategy", "Campaigns & Growth", "Metrics & Experimentation"],
        core=["Marketing Strategy", "Campaigns & Growth", "Behavioral"],
        search_terms=["marketing", "product marketing manager", "growth marketing"],
    ),
    "Operations": Function(
        positions=["Operations Analyst", "Business Operations", "Program Manager", "Operations Manager"],
        categories=["Operations & Process", "Estimation", "Metrics & Experimentation"],
        core=["Operations & Process", "Behavioral"],
        search_terms=["operations", "program manager", "business operations"],
    ),
    "People / HR": Function(
        positions=["Recruiter", "HR Generalist", "HR Business Partner", "HR Manager"],
        categories=["HR & Recruiting"],
        core=["HR & Recruiting", "Behavioral"],
        search_terms=["HR", "recruiter", "HRBP"],
    ),
}
DEFAULT_FUNCTION = "Engineering"
MANAGER_POSITIONS = {"Engineering Manager", "Director of Product", "Analytics Manager", "Design Manager",
                     "Sales Manager", "Marketing Manager", "Operations Manager", "HR Manager"}

# Shared by every function.
COMMON_CATEGORIES = ["People Management", "Behavioral", "Other"]

# One flat, ordered list: the Category type, UI tab order and guide section order.
CATEGORIES: list[str] = list(dict.fromkeys(
    [c for f in FUNCTIONS.values() for c in f.categories] + COMMON_CATEGORIES))

# Engineering specialties (tracks), with what each should expect to prepare.
TRACKS = ["Backend", "Frontend", "Fullstack", "ML/AI", "Mobile", "QA", "DevOps"]
TRACK_CORE = {
    "Backend": ["DSA", "LLD", "HLD", "Backend", "Database", "Behavioral"],
    "Frontend": ["DSA", "Frontend", "HLD", "Behavioral"],
    "Fullstack": ["DSA", "LLD", "HLD", "Backend", "Database", "Frontend", "Behavioral"],
    "DevOps": ["DevOps & Cloud", "Backend", "Behavioral"],
    "ML/AI": ["ML/AI", "DSA", "Behavioral"],
}
# Questions tagged with a neighbouring track still help: a Backend candidate should
# see Fullstack and unlabelled ("General") questions too.
RELATED_TRACKS = {
    "Backend": ["Backend", "Fullstack", "General"],
    "Frontend": ["Frontend", "Fullstack", "General"],
    "Fullstack": ["Fullstack", "Backend", "Frontend", "General"],
}


# Engineering levels read off a title, checked in order (so "Senior Software Engineer 1"
# is Senior, not SDE 1). Done in code: LLMs either invented levels for "Software
# Engineer" or dropped clearly stated ones like "Staff".
ENGINEERING_LEVELS = [
    (r"\bintern", "Intern"),
    (r"\bmanager\b", "Engineering Manager"),
    (r"\bprincip", "Principal Engineer"),  # also catches the common "Principle"
    (r"\bstaff\b", "Staff Engineer"),
    (r"\b(senior|sr|lead)\b|\biii\b|\bsde[-\s]?(3|iii)\b|\b3\b", "SDE 3 / Senior"),
    (r"\bii\b|\bsde[-\s]?(2|ii)\b|\b2\b", "SDE 2"),
    (r"new grad|\b(associate|junior|jr|graduate)\b|\bi\b|\bsde[-\s]?(1|i)\b|\b1\b", "SDE 1"),
]


def engineering_level(title: str | None) -> str:
    if not title:
        return UNKNOWN
    t = title.lower()
    return next((level for pattern, level in ENGINEERING_LEVELS if re.search(pattern, t)), UNKNOWN)


@dataclass(frozen=True)
class Scope:
    """Which questions a request is about. Every filter in the app is one of these."""
    company: str
    function: str = DEFAULT_FUNCTION
    position: str | None = None   # None = every position in the function
    track: str | None = None      # engineering only
    since: int | None = None      # interview (or posted) year >= since

    def __post_init__(self):
        if self.function not in FUNCTIONS:
            raise ValueError(f"unknown function: {self.function}")
        if self.position and self.position not in FUNCTIONS[self.function].positions + [UNKNOWN]:
            raise ValueError(f"{self.position} is not a {self.function} position")
        if self.track and self.function != "Engineering":
            object.__setattr__(self, "track", None)  # tracks only mean something in engineering

    def core(self) -> list[str]:
        base = TRACK_CORE.get(self.track) if self.track else None
        core = list(base or FUNCTIONS[self.function].core)
        if self.position in MANAGER_POSITIONS:
            core += FUNCTIONS[self.function].manager_core
        return core

    def search_terms(self) -> list[str]:
        if self.position and self.position != UNKNOWN:
            return [self.position.split(" / ")[0]]
        if self.track:
            return [f"{self.track.lower()} engineer"]
        return FUNCTIONS[self.function].search_terms

    def label(self) -> str:
        parts = [self.function, self.position, f"{self.track} track" if self.track else None,
                 f"since {self.since}" if self.since else None]
        return " · ".join(p for p in parts if p)

    def slug(self) -> str:
        """File name for this scope's saved guide."""
        parts = [self.company, self.function, self.position, self.track]
        return re.sub(r"[^a-z0-9]+", "-", "-".join(p for p in parts if p).lower()).strip("-")
