import Link from "next/link";
import { notFound } from "next/navigation";
import styles from "./storefront.module.css";

export const dynamic = "force-dynamic";

async function loadStorefront(slug) {
  const apiBase = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const response = await fetch(
    `${apiBase}/api/storefront/public/${encodeURIComponent(slug)}`,
    { cache: "no-store" },
  );
  if (response.status === 404) notFound();
  if (!response.ok) throw new Error("Storefront belum dapat dimuat");
  return response.json();
}

function safeChatHref(value, slug) {
  const expected = `/chat/${slug}`;
  return value === expected ? value : expected;
}

function ProductGrid({ products }) {
  if (products.length === 0) {
    return <p className={styles.empty}>Belum ada produk aktif yang ditampilkan.</p>;
  }
  return (
    <div className={styles.grid}>
      {products.map((product) => (
        <article className={styles.card} key={product.id}>
          <h3>{product.name}</h3>
          {product.description && <p>{product.description}</p>}
          <strong>Rp {Number(product.price || 0).toLocaleString("id-ID")}</strong>
        </article>
      ))}
    </div>
  );
}

export async function generateMetadata({ params }) {
  const { slug } = await params;
  const { store, storefront } = await loadStorefront(slug);
  return {
    title: storefront.seo_title || storefront.title || store.name,
    description: storefront.seo_description || store.description || "",
  };
}

export default async function PublicStorefrontPage({ params }) {
  const { slug } = await params;
  const data = await loadStorefront(slug);
  const { store, storefront, products = [], sections = [] } = data;
  const visibleSections = sections;

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>JUALIN.AI Store</p>
          <h1>{storefront.title || store.name}</h1>
          {storefront.tagline && <p className={styles.tagline}>{storefront.tagline}</p>}
        </div>
        <Link className="btn btn-primary" href={`/chat/${store.slug}`}>Chat dengan toko</Link>
      </header>

      {store.description && <p className={styles.description}>{store.description}</p>}
      {visibleSections.map((section) => {
        const content = section.content || {};
        const headingId = `store-section-${section.id}`;

        if (section.type === "hero") {
          return (
            <section className={`${styles.section} ${styles.heroSection}`} aria-labelledby={headingId} key={section.id}>
              <h2 id={headingId}>{content.headline || section.title}</h2>
              {content.subheadline && <p className={styles.sectionText}>{content.subheadline}</p>}
              {content.cta_text && (
                <Link className="btn btn-primary" href={safeChatHref(content.cta_url, store.slug)}>
                  {content.cta_text}
                </Link>
              )}
            </section>
          );
        }

        if (section.type === "featured_products") {
          const requestedLimit = Number(content.limit);
          const limit = Number.isInteger(requestedLimit) ? Math.min(Math.max(requestedLimit, 1), 12) : 12;
          return (
            <section className={styles.section} aria-labelledby={headingId} key={section.id}>
              <h2 id={headingId}>{section.title || "Produk"}</h2>
              <ProductGrid products={products.slice(0, limit)} />
            </section>
          );
        }

        if (section.type === "categories") {
          const categories = [...new Set(products.map((product) => product.category).filter(Boolean))];
          return (
            <section className={styles.section} aria-labelledby={headingId} key={section.id}>
              <h2 id={headingId}>{section.title || "Kategori Produk"}</h2>
              {categories.length > 0 ? (
                <ul className={styles.categoryList}>
                  {categories.map((category) => <li key={category}>{category}</li>)}
                </ul>
              ) : <p className={styles.empty}>Belum ada kategori produk.</p>}
            </section>
          );
        }

        if (section.type === "testimonials") {
          const items = Array.isArray(content.items) ? content.items.slice(0, 10) : [];
          return (
            <section className={styles.section} aria-labelledby={headingId} key={section.id}>
              <h2 id={headingId}>{section.title || "Apa Kata Pelanggan"}</h2>
              {items.length > 0 ? (
                <div className={styles.testimonialGrid}>
                  {items.map((item, index) => (
                    <blockquote className={styles.testimonial} key={`${item.name || "customer"}-${index}`}>
                      <p>{item.text}</p>
                      {item.name && <cite>{item.name}</cite>}
                    </blockquote>
                  ))}
                </div>
              ) : <p className={styles.empty}>Belum ada testimoni.</p>}
            </section>
          );
        }

        if (section.type === "cta") {
          return (
            <section className={`${styles.section} ${styles.ctaSection}`} aria-labelledby={headingId} key={section.id}>
              <div>
                <h2 id={headingId}>{section.title || "Hubungi Kami"}</h2>
                {content.text && <p className={styles.sectionText}>{content.text}</p>}
              </div>
              {content.cta_text && (
                <Link className="btn btn-primary" href={safeChatHref(content.cta_url, store.slug)}>
                  {content.cta_text}
                </Link>
              )}
            </section>
          );
        }

        return null;
      })}
    </main>
  );
}
