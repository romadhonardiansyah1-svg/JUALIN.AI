import { Inter, Plus_Jakarta_Sans, Sora } from "next/font/google";
import "./globals.css";
import AuthProvider from "@/components/AuthProvider";

// Self-hosted by next/font: no render-blocking request to fonts.googleapis.com.
// No `weight` = variable font, so the full 100–900 range the CSS uses stays available.
const inter = Inter({ subsets: ["latin"], display: "swap", variable: "--font-inter" });
const jakarta = Plus_Jakarta_Sans({ subsets: ["latin"], display: "swap", variable: "--font-jakarta" });
const sora = Sora({ subsets: ["latin"], display: "swap", variable: "--font-sora" });

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
  themeColor: "#6366f1",
};

export default function RootLayout({ children }) {
  return (
    <html lang="id" className={`${inter.variable} ${jakarta.variable} ${sora.variable}`}>
      <head>
        <meta name="theme-color" content="#6366f1" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
        <link rel="manifest" href="/manifest.json" />
      </head>
      <body>
        <AuthProvider>{children}</AuthProvider>
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
