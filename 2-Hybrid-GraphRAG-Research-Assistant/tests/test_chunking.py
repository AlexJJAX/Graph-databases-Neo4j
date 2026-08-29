from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from chunking import build_chunks, chunk_words, corpus_hash, load_corpus  # noqa: E402


class ChunkingTests(unittest.TestCase):
    def test_word_chunks_are_bounded_and_overlap(self):
        words = [f"word-{index}" for index in range(50)]

        chunks = chunk_words(" ".join(words), max_words=20, overlap_words=5)

        self.assertEqual([len(chunk.split()) for chunk in chunks], [20, 20, 20])
        self.assertEqual(chunks[0].split()[-5:], chunks[1].split()[:5])
        self.assertEqual(chunks[1].split()[-5:], chunks[2].split()[:5])

    def test_invalid_chunk_settings_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "at least 20"):
            chunk_words("text", max_words=19)
        with self.assertRaisesRegex(ValueError, "between 0"):
            chunk_words("text", max_words=20, overlap_words=20)

    def test_curated_corpus_produces_stable_ids_and_hashes(self):
        papers = load_corpus(PROJECT_DIR / "data" / "papers.json")
        chunks = [chunk for paper in papers for chunk in build_chunks(paper)]

        self.assertEqual(len(papers), 8)
        self.assertEqual(len(chunks), 24)
        self.assertEqual(chunks[0].chunk_id, "attention-2017:s00:p00")
        self.assertEqual(len({chunk.chunk_id for chunk in chunks}), 24)
        self.assertEqual(
            corpus_hash(papers[0], build_chunks(papers[0])),
            corpus_hash(papers[0], build_chunks(papers[0])),
        )

    def test_unknown_citation_is_rejected(self):
        corpus = [
            {
                "paperId": "paper-1",
                "title": "Test paper",
                "year": 2025,
                "abstract": "An abstract.",
                "sourceUrl": "https://example.com/paper",
                "authors": ["A. Author"],
                "topics": ["RAG"],
                "methods": [],
                "datasets": [],
                "cites": ["missing-paper"],
                "sections": [{"heading": "Summary", "text": "Some text."}],
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing-paper"):
                load_corpus(path)

    def test_duplicate_paper_ids_are_rejected(self):
        corpus_path = PROJECT_DIR / "data" / "papers.json"
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
        corpus.append(corpus[0])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corpus.json"
            path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate paperId"):
                load_corpus(path)


if __name__ == "__main__":
    unittest.main()
