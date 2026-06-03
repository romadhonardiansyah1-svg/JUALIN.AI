import "./globals.css";

export const metadata = {
  title: "JUALIN.AI — AI Sales Assistant untuk UMKM",
  description:
    "Otomasi chat penjualan, proses pesanan, dan follow-up pembayaran dengan AI yang memahami katalog produkmu. Gratis untuk UMKM mikro.",
  keywords: "AI, sales assistant, UMKM, chatbot, jual online, toko online",
};

export default function RootLayout({ children }) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
