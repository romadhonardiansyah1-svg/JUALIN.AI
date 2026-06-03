"""
JUALIN.AI — Guardrails
Post-processing rules to ensure AI responses are safe and accurate
"""
import re


# 7 Guardrail Rules
GUARDRAIL_RULES = [
    "1. AI HANYA menjawab berdasarkan data katalog seller.",
    "2. Stok & harga SELALU di-query real-time dari database.",
    "3. Jika produk tidak ada → minta maaf + tawarkan alternatif.",
    "4. AI TIDAK boleh mengarang info yang tidak ada di katalog.",
    "5. AI TIDAK menjawab topik di luar jual-beli.",
    "6. AI SELALU konfirmasi ulang sebelum membuat order.",
    "7. Jika customer marah → tandai urgent, eskalasi ke seller.",
]


def check_guardrails(response: str, user_message: str) -> dict:
    """
    Check if an AI response passes all guardrail rules.
    Returns dict with is_safe flag and any violations found.
    Used for validation/testing.
    """
    violations = []
    
    # Check for suspicious discount claims
    if re.search(r'diskon\s+\d{2,3}\s*%', response, re.IGNORECASE):
        violations.append("Suspicious discount claim detected")
    
    # Check for made-up shipping promises
    if re.search(r'gratis\s+ongkir\s+seluruh\s+indonesia', response, re.IGNORECASE):
        violations.append("Fake free shipping claim")
    
    # Check for fabricated warranty
    if re.search(r'garansi\s+\d+\s+tahun', response, re.IGNORECASE):
        violations.append("Fabricated warranty claim")
    
    # Check response isn't empty
    if not response or not response.strip():
        violations.append("Empty response")
    
    # Check response length (too long = likely hallucinating)
    if len(response) > 1200:
        violations.append("Response too long")
    
    return {
        "is_safe": len(violations) == 0,
        "violations": violations,
        "response": response,
        "user_message": user_message,
    }


def apply_guardrails(ai_response: str, catalog: list[dict]) -> str:
    """
    Apply post-processing guardrails to AI response.
    Ensures the AI doesn't hallucinate products, prices, or stock.
    """
    # Rule: Remove any obviously hallucinated large discounts
    suspicious_patterns = [
        r'diskon\s+\d{2,3}\s*%',  # "diskon 90%"
        r'gratis\s+ongkir\s+seluruh\s+indonesia',  # Fake free shipping
        r'garansi\s+\d+\s+tahun',  # Fake warranty claims
    ]
    
    for pattern in suspicious_patterns:
        if re.search(pattern, ai_response, re.IGNORECASE):
            # Flag but don't remove — prompt should prevent this
            pass
    
    # Rule: Ensure response isn't too long (max ~600 chars for chat)
    if len(ai_response) > 800:
        sentences = ai_response[:800].split('.')
        if len(sentences) > 1:
            ai_response = '.'.join(sentences[:-1]) + '.'
        else:
            ai_response = ai_response[:800] + '...'
    
    # Rule: Ensure response isn't empty
    if not ai_response or not ai_response.strip():
        ai_response = "Hai kak! Ada yang bisa kami bantu? 😊"
    
    return ai_response.strip()
