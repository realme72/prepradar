"""Merge near-duplicate questions.

Two questions are duplicates when cosine similarity of their embeddings is
>= threshold. Each merged group keeps one representative text and every source
it was reported in; times_reported counts distinct sources, so one page
repeating itself doesn't inflate the count.
"""
import numpy as np
from pydantic import BaseModel

from prepradar.models import ExtractedQuestion
from prepradar.store.embeddings import embed


class MergedQuestion(BaseModel):
    question: ExtractedQuestion  # representative
    variants: list[str]          # other phrasings that were merged in
    sources: list[str]

    @property
    def times_reported(self) -> int:
        return len(self.sources)


def similarity_matrix(questions: list[ExtractedQuestion]) -> np.ndarray:
    vecs = embed([q.text for q in questions])
    return vecs @ vecs.T


def close_pairs(questions: list[ExtractedQuestion], low: float, high: float = 1.0):
    """Pairs with similarity in [low, high), most similar first. Used to pick a threshold."""
    sim = similarity_matrix(questions)
    pairs = [
        (float(sim[i, j]), questions[i], questions[j])
        for i in range(len(questions))
        for j in range(i + 1, len(questions))
        if low <= sim[i, j] < high
    ]
    return sorted(pairs, key=lambda p: -p[0])


def dedupe(questions: list[ExtractedQuestion], threshold: float) -> list[MergedQuestion]:
    """Greedy clustering: each question joins the first group whose representative it matches."""
    if not questions:
        return []
    sim = similarity_matrix(questions)
    # prefer specific, longer phrasings as representatives
    order = sorted(range(len(questions)), key=lambda i: (not questions[i].specific, -len(questions[i].text)))
    groups: list[tuple[int, list[int]]] = []
    for i in order:
        for rep, members in groups:
            if sim[i, rep] >= threshold:
                members.append(i)
                break
        else:
            groups.append((i, [i]))

    merged = []
    for rep, members in groups:
        q = questions[rep]
        merged.append(
            MergedQuestion(
                question=q,
                variants=[questions[m].text for m in members if m != rep],
                sources=sorted({str(questions[m].source_url) for m in members}),
            )
        )
    return merged
