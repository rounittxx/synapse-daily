import logging
import math
from datetime import datetime, timezone
from typing import List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from .collector import Article

log = logging.getLogger(__name__)

# what we consider "AI/ML relevant" - these anchor phrases define the topic space
_ANCHORS = [
    "artificial intelligence machine learning deep learning",
    "large language model neural network transformer",
    "natural language processing computer vision reinforcement learning",
    "foundation model generative AI diffusion model",
    "AI research paper model training inference",
    "AI safety alignment hallucination benchmark",
    "robotics autonomous systems multimodal AI",
    "AI startup funding product launch deployment",
    "GPU compute dataset open source AI model",
    "LLM fine-tuning RLHF prompt engineering",
]

RELEVANCE_THRESHOLD = 0.25   # below this = not really AI/ML
DUPLICATE_CUTOFF = 0.92      # above this = same story from different source
RECENCY_HALFLIFE = 24.0      # hours until recency score halves

_model = None


def _load_model():
    global _model
    if _model is None:
        log.info("loading sentence-transformer model...")
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _recency(published: datetime) -> float:
    age_h = max((datetime.now(timezone.utc) - published).total_seconds() / 3600, 0)
    return math.exp(-math.log(2) * age_h / RECENCY_HALFLIFE)


def _embed(articles: List[Article], model) -> np.ndarray:
    texts = [f"{a.title}. {a.summary}" for a in articles]
    return model.encode(texts, batch_size=32, show_progress_bar=False, normalize_embeddings=True)


def _relevance(embeddings: np.ndarray, model) -> np.ndarray:
    anchor_vecs = model.encode(_ANCHORS, batch_size=16, show_progress_bar=False, normalize_embeddings=True)
    sims = cosine_similarity(embeddings, anchor_vecs)
    return sims.max(axis=1)


def _deduplicate(articles, embeddings, cutoff=DUPLICATE_CUTOFF):
    sims = cosine_similarity(embeddings)
    n = len(articles)
    keep = [True] * n

    for i in range(n):
        if not keep[i]:
            continue
        for j in range(i + 1, n):
            if keep[j] and sims[i, j] >= cutoff:
                log.debug(f"dup removed: '{articles[j].title[:50]}' (sim={sims[i,j]:.2f})")
                keep[j] = False

    kept_articles = [a for a, k in zip(articles, keep) if k]
    kept_embs = embeddings[[i for i, k in enumerate(keep) if k]]
    return kept_articles, kept_embs


def rank_articles(articles: List[Article], top_n: int = 15) -> List[Article]:
    if not articles:
        return []

    model = _load_model()
    log.info(f"ranking {len(articles)} articles...")

    embeddings = _embed(articles, model)
    rel_scores = _relevance(embeddings, model)

    # filter out stuff that's clearly not AI/ML
    filtered = [
        (a, e, r) for a, e, r in zip(articles, embeddings, rel_scores)
        if r >= RELEVANCE_THRESHOLD
    ]

    if not filtered:
        log.warning("nothing passed relevance filter, using everything")
        filtered = list(zip(articles, embeddings, rel_scores))

    f_arts, f_embs_list, f_rels = zip(*filtered)
    f_arts = list(f_arts)
    f_embs = np.vstack(f_embs_list)
    f_rels = np.array(f_rels)

    log.info(f"{len(f_arts)} passed relevance filter")

    f_arts, f_embs = _deduplicate(f_arts, f_embs)
    f_rels = _relevance(f_embs, model)

    log.info(f"{len(f_arts)} after dedup")

    recency = np.array([_recency(a.published) for a in f_arts])
    scores = 0.6 * f_rels + 0.4 * recency

    for art, rel, score in zip(f_arts, f_rels, scores):
        art.relevance_score = float(rel)
        art.combined_score = float(score)

    ranked = sorted(f_arts, key=lambda a: a.combined_score, reverse=True)
    return ranked[:top_n]
