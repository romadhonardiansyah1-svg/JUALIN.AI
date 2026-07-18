import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("NEXT_NOT_FOUND"); } }));
import PublicStorefrontPage, { generateMetadata } from "./page";

const storefrontResponse = () => ({
  ok: true,
  status: 200,
  json: async () => ({
    store: { name: "Toko Aman", slug: "toko-aman", description: "Produk pilihan" },
    storefront: {
      title: "Toko Aman", tagline: "Belanja mudah",
      seo_title: "Belanja di Toko Aman", seo_description: "Katalog aman dan lengkap",
    },
    sections: [
      {
        id: 7, type: "featured_products", title: "Produk Unggulan", order: 1,
        content: { limit: 6 },
      },
      {
        id: 8, type: "cta", title: "Hubungi Kami", order: 2,
        content: { text: "Butuh bantuan?", cta_text: "Mulai Chat", cta_url: "/chat/toko-aman" },
      },
    ],
    products: [{ id: 1, name: "Produk Satu", price: 25000, description: "Bagus" }],
  }),
});

describe("PublicStorefrontPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders configured sections in returned order with safe CTA links", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(storefrontResponse()));

    const { container } = render(
      await PublicStorefrontPage({ params: Promise.resolve({ slug: "toko-aman" }) }),
    );

    expect(screen.getByRole("heading", { name: "Toko Aman" })).toBeInTheDocument();
    expect(screen.getByText("Produk Satu")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mulai Chat" })).toHaveAttribute("href", "/chat/toko-aman");
    expect(container.textContent.indexOf("Produk Unggulan"))
      .toBeLessThan(container.textContent.indexOf("Hubungi Kami"));
  });

  it("does not expose products when every configured section is hidden", async () => {
    const response = storefrontResponse();
    response.json = async () => ({
      store: { name: "Toko Aman", slug: "toko-aman", description: "Produk pilihan" },
      storefront: { title: "Toko Aman", tagline: "Belanja mudah" },
      sections: [],
      products: [{ id: 1, name: "Produk Rahasia", price: 25000 }],
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));

    render(await PublicStorefrontPage({ params: Promise.resolve({ slug: "toko-aman" }) }));

    expect(screen.queryByText("Produk Rahasia")).not.toBeInTheDocument();
  });

  it("exports metadata from the published storefront SEO contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(storefrontResponse()));

    const metadata = await generateMetadata({ params: Promise.resolve({ slug: "toko-aman" }) });

    expect(metadata).toEqual({
      title: "Belanja di Toko Aman",
      description: "Katalog aman dan lengkap",
    });
  });
});
