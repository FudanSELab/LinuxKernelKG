from dataclasses import dataclass

@dataclass
class LinkingCandidate:
    mention: str
    title: str
    url: str
    summary: str = ''
    confidence: float = 0.0
    is_disambiguation: bool = False
    page: "WikipediaPage" = None

    def to_dict(self):
        """将对象转换为可序列化的字典，排除page字段"""
        return {
            "mention": self.mention,
            "title": self.title,
            "url": self.url
        }
