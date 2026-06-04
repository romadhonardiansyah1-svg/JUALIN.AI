import "./globals.css";

export const metadata = {
  title: "JUALIN.AI — AI Sales Assistant untuk UMKM",
  description:
    "Otomasi chat penjualan, proses pesanan, dan follow-up pembayaran dengan AI yang memahami katalog produkmu. Gratis untuk UMKM mikro.",
  keywords: "AI, sales assistant, UMKM, chatbot, jual online, toko online",
  manifest: "/manifest.json",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: "no",
  themeColor: "#6366f1",
};

export default function RootLayout({ children }) {
  return (
    <html lang="id">
      <head>
        <meta name="theme-color" content="#6366f1" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <link rel="manifest" href="/manifest.json" />
      </head>
      <body>
        {children}
        <script
          dangerouslySetInnerHTML={{
            __html: `
              if ('serviceWorker' in navigator) {
                window.addEventListener('load', function() {
                  navigator.serviceWorker.register('/sw.js').catch(function() {});
                });
              }
            `,
          }}
        />
      </body>
    </html>
  );
}
