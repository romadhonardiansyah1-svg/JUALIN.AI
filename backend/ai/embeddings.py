"""
JUALIN.AI — Embedding Module
Sentence-transformer lokal untuk semantic search
"""
from config import get_settings

settings = get_settings()

_embed_model = None


def get_embedding_model():
    """Lazy-load embedding model (only loaded once on first use)."""
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        print(f"✅ Embedding model loaded: {settings.EMBEDDING_MODEL}")
    return _embed_model


def generate_embedding(text: str) -> list[float]:
    """Generate embedding vector from text."""
    model = get_embedding_model()
    return model.encode(text).tolist()


def build_embed_text(product: dict) -> str:
    """Build text for embedding from product data."""
    parts = [
        product.get("nama", ""),
        product.get("deskripsi", ""),
        product.get("kategori", ""),
        f"harga {product.get('harga', 0)}",
    ]
    return " ".join(p for p in parts if p)
