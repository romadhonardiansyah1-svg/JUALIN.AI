# Claims Register — JUALIN.AI

Status awal klaim publik/dashboard per Phase 0.5.
Setiap klaim harus memiliki owner, evidence, qualifier, dan review expiry.
Tidak ada klaim `unverified` di surface publik.

| Claim saat ini/potensial | Surface | Status awal | Copy aman sampai ada evidence | Evidence yang dibutuhkan | Owner |
|---|---|---|---|---|---|
| “300× lebih cepat” | landing | unverified → dihapus | “Respons cepat” | benchmark reproducible + baseline latency | product/eng |
| “100% chat terbalas” | landing | false/absolute → diubah | “Dapat membantu merespons di luar jam operasional.” | production delivery/coverage data, uptime | product |
| “Setup 5 menit” | landing | unverified → diubah | “Setup terpandu.” | usability timing sample (n users, median) | ux-research |
| “Dipercaya UMKM seluruh Indonesia” | landing | unverified → diubah | “Dirancang untuk UMKM Indonesia.” | verified customer distribution, count, region | product/legal |
| “AI hanya menjawab berdasarkan katalog” | landing/FAQ | overclaim → diubah | “AI diarahkan menggunakan data katalog dan tetap dapat keliru.” | adversarial/eval result, accuracy metric | ai-quality |
| “Revenue Recovered” | dashboard | causal overclaim → diubah | “Pembayaran teramati” | ledger + method + disclaimer | eng/product |
| `+12/+8/+15%` | dashboard | hardcoded → dihapus | — (tampilkan dash atau data nyata) | computed metric + denominator | eng |
| “Follow-up AI aktif” | dashboard | capability-dependent → diubah | tampil hanya jika capability benar | capability + successful checks | eng |
| payment/channel/pricing support | landing/pricing | unverified per provider | qualify per tested provider/plan | live staging and billing contract | eng/ops |

## Gate

- PR yang menambah claim harus memperbarui file ini.
- CI wajib gagal bila claim baru belum mempunyai owner/evidence mapping.
- Landing tidak boleh memuat klaim dari kolom “Claim saat ini/potensial” tanpa evidence `verified`.
- Dashboard tidak boleh menampilkan `+12/+8/+15%` atau “Revenue Recovered” sebagai causal tanpa ledger method.

## Review Expiry

- Setiap klaim `verified` harus direview ulang minimal tiap 90 hari.
- Klaim yang expired kembali ke `unverified` dan copy aman harus dipakai.

## References

- Bagian 21 Product truth di SUPER_IMPLEMENTATION_PLAN
- Bagian 22 Copy deck Bahasa Indonesia
