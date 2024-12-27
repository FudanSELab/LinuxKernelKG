from dataclasses import dataclass

@dataclass
class LinkingCandidate:
    mention: str
    title: str
    url: str
    summary: str
    confidence: float
    is_disambiguation: bool 