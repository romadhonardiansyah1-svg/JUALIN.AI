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
    Post-processing minimal yang JUJUR:
    - respons kosong -> fallback ramah
    - batas panjang dinaikkan ke 1500 dan JANGAN memotong template order/link bayar
      (truncation 800 char lama pernah memutus 'ORDER CONFIRMED' -> order gagal diam-diam).
    Guardrail harga yang sesungguhnya hidup di services/agent_os/negotiation.py (engine + text firewall).
    """
    if not ai_response or not ai_response.strip():
        return "Hai kak! Ada yang bisa kami bantu? 😊"

    text = ai_response.strip()
    if len(text) > 1500 and "ORDER CONFIRMED" not in text.upper() and "/pay/" not in text:
        sentences = text[:1500].split('.')
        text = '.'.join(sentences[:-1]) + '.' if len(sentences) > 1 else text[:1500] + '...'
    return text
