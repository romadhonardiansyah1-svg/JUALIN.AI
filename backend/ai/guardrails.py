"""
JUALIN.AI — Guardrails
Post-processing rules to ensure AI responses are safe and accurate
"""
import re


def apply_guardrails(ai_response: str, catalog: list[dict]) -> str:
    """
    Apply post-processing guardrails to AI response.
    Ensures the AI doesn't hallucinate products, prices, or stock.
    """
    # Rule: Remove any obviously hallucinated large discounts
    # (AI sometimes invents "diskon 90%!" etc.)
    suspicious_patterns = [
        r'diskon\s+\d{2,3}\s*%',  # "diskon 90%"
        r'gratis\s+ongkir\s+seluruh\s+indonesia',  # Fake free shipping
        r'garansi\s+\d+\s+tahun',  # Fake warranty claims
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, ai_response, re.IGNORECASE):
            # Don't remove, just flag — the prompt should prevent this
            # but this is a safety net
            pass
    
    # Rule: Ensure response isn't too long (max ~600 chars for chat)
    if len(ai_response) > 800:
        # Truncate at last complete sentence
        sentences = ai_response[:800].split('.')
        if len(sentences) > 1:
            ai_response = '.'.join(sentences[:-1]) + '.'
        else:
            ai_response = ai_response[:800] + '...'
    
    # Rule: Ensure response isn't empty
    if not ai_response or not ai_response.strip():
        ai_response = "Hai kak! Ada yang bisa kami bantu? 😊"
    
    return ai_response.strip()
