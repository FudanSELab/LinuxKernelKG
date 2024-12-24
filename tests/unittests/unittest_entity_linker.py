import unittest
from unittest.mock import MagicMock
from pipeline.entity_linker import EntityLinker

class TestEntityLinker(unittest.TestCase):
    def setUp(self):
        # 创建 EntityLinker 实例并模拟 config
        self.entity_linker = EntityLinker(config=MagicMock())
        self.entity_linker.config.NGRAM_DELIMITERS = ' -_'

    def test_generate_ngrams(self):
        text = "Linux kernel memory management"
        expected_ngrams = [
            "Linux", "kernel", "memory", "management",
            "Linux kernel", "kernel memory", "memory management",
            "Linux kernel memory", "kernel memory management"
        ]
        result = self.entity_linker._generate_ngrams(text, min_n=1, max_n=3)
        self.assertEqual(result, expected_ngrams)

    def test_generate_ngrams_with_custom_delimiters(self):
        self.entity_linker.config.NGRAM_DELIMITERS = ' -_'
        text = "Linux_kernel memory-management"
        expected_ngrams = [
            "Linux", "kernel", "memory", "management",
            "Linux kernel", "kernel memory", "memory management",
            "Linux kernel memory", "kernel memory management"
        ]
        result = self.entity_linker._generate_ngrams(text, min_n=1, max_n=3)
        self.assertEqual(result, expected_ngrams)

if __name__ == '__main__':
    unittest.main()