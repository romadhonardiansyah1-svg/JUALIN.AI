"use client";
import { useEffect, useState, useRef } from "react";
import { api } from "@/lib/api";
import styles from "./products.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

export default function ProductsPage() {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [search, setSearch] = useState("");
  const [form, setForm] = useState({ nama: "", deskripsi: "", harga: "", stok: "", kategori: "umum" });
  const [uploading, setUploading] = useState(null); // product id being uploaded
  const fileInputRef = useRef(null);
  const [uploadTargetId, setUploadTargetId] = useState(null);

  useEffect(() => {
    loadProducts();
  }, []);

  async function loadProducts() {
    try {
      const data = await api.getProducts();
      setProducts(data);
    } catch (e) {
      // Demo data for offline
      setProducts([
        { id: 1, nama: "Baju Pink Satin", harga: 89000, stok: 15, kategori: "dress", deskripsi: "Baju satin warna pink soft", is_active: 1, foto_url: "" },
        { id: 2, nama: "Dress Emerald Elegan", harga: 189000, stok: 8, kategori: "dress", deskripsi: "Dress panjang emerald", is_active: 1, foto_url: "" },
        { id: 3, nama: "Kaos Oversize Hitam", harga: 59000, stok: 30, kategori: "kaos", deskripsi: "Kaos oversize cotton combed", is_active: 1, foto_url: "" },
        { id: 4, nama: "Blouse Brukat Gold", harga: 145000, stok: 10, kategori: "blouse", deskripsi: "Blouse brukat bordir bunga", is_active: 1, foto_url: "" },
        { id: 5, nama: "Hoodie Abu-abu", harga: 125000, stok: 18, kategori: "hoodie", deskripsi: "Hoodie fleece hangat", is_active: 1, foto_url: "" },
        { id: 6, nama: "T-shirt Band Vintage", harga: 75000, stok: 0, kategori: "kaos", deskripsi: "T-shirt sablon vintage edisi terbatas", is_active: 1, foto_url: "" },
        { id: 7, nama: "Gamis Pesta Navy", harga: 225000, stok: 6, kategori: "gamis", deskripsi: "Gamis wolfis premium", is_active: 1, foto_url: "" },
        { id: 8, nama: "Rok Plisket Cream", harga: 79000, stok: 20, kategori: "rok", deskripsi: "Rok plisket premium", is_active: 1, foto_url: "" },
      ]);
    }
    setLoading(false);
  }

  const handleSave = async (e) => {
    e.preventDefault();
    try {
      if (editingProduct) {
        await api.updateProduct(editingProduct.id, { ...form, harga: Number(form.harga), stok: Number(form.stok) });
      } else {
        await api.createProduct({ ...form, harga: Number(form.harga), stok: Number(form.stok) });
      }
      setShowModal(false);
      setEditingProduct(null);
      setForm({ nama: "", deskripsi: "", harga: "", stok: "", kategori: "umum" });
      loadProducts();
    } catch (e) {
      alert(e.message);
    }
  };

  const handleEdit = (product) => {
    setEditingProduct(product);
    setForm({ nama: product.nama, deskripsi: product.deskripsi, harga: product.harga, stok: product.stok, kategori: product.kategori });
    setShowModal(true);
  };

  const handleDelete = async (id) => {
    if (!confirm("Hapus produk ini?")) return;
    try {
      await api.deleteProduct(id);
      loadProducts();
    } catch (e) {
      alert(e.message);
    }
  };

  const handleUploadClick = (productId) => {
    setUploadTargetId(productId);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !uploadTargetId) return;

    // Validate on frontend too
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      alert("Format file harus JPG, PNG, atau WebP");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      alert("Ukuran file maksimal 5MB");
      return;
    }

    setUploading(uploadTargetId);
    try {
      const result = await api.uploadProductImage(uploadTargetId, file);
      // Update product in state
      setProducts(prev => prev.map(p => 
        p.id === uploadTargetId ? { ...p, foto_url: result.foto_url } : p
      ));
    } catch (e) {
      alert("Gagal upload: " + e.message);
    }
    setUploading(null);
    setUploadTargetId(null);
    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const getImageUrl = (fotoUrl) => {
    if (!fotoUrl) return null;
    if (fotoUrl.startsWith("http")) return fotoUrl;
    return `${API_BASE}${fotoUrl}`;
  };

  const filtered = products.filter((p) =>
    p.nama.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 20, padding: 0 }}>
        {[1,2,3,4,5,6,7,8].map(i => (
          <div key={i} style={{ 
            height: 280, borderRadius: 12, 
            background: "linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)",
            backgroundSize: "200% 100%", animation: "shimmer 1.5s infinite" 
          }} />
        ))}
      </div>
    );
  }

  return (
    <div className={styles.productsPage}>
      {/* Hidden file input for uploads */}
      <input 
        ref={fileInputRef}
        type="file" 
        accept="image/jpeg,image/png,image/webp"
        style={{ display: "none" }}
        onChange={handleFileChange}
      />

      {/* Header */}
      <div className={styles.header}>
        <div>
          <h2 className={styles.title}>Katalog Produk</h2>
          <p className="text-muted text-sm">{products.length} produk aktif · {products.filter(p => p.stok === 0).length} habis</p>
        </div>
        <div className={styles.headerActions}>
          <input
            type="text"
            className="input"
            placeholder="🔍 Cari produk..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 240 }}
          />
          <button className="btn btn-primary" onClick={() => { setEditingProduct(null); setForm({ nama: "", deskripsi: "", harga: "", stok: "", kategori: "umum" }); setShowModal(true); }}>
            + Tambah Produk
          </button>
        </div>
      </div>

      {/* Product Grid */}
      <div className={styles.productGrid}>
        {filtered.map((p) => (
          <div key={p.id} className={`${styles.productCard} ${p.stok === 0 ? styles.outOfStock : ""}`}>
            <div 
              className={styles.productImage}
              onClick={() => handleUploadClick(p.id)}
              title="Klik untuk upload foto"
            >
              {p.foto_url ? (
                <img 
                  src={getImageUrl(p.foto_url)} 
                  alt={p.nama}
                  className={styles.productImg}
                  onError={(e) => { e.target.style.display = "none"; e.target.nextSibling.style.display = "flex"; }}
                />
              ) : null}
              <div className={styles.productImagePlaceholder} style={p.foto_url ? { display: "none" } : {}}>
                {uploading === p.id ? (
                  <span className={styles.uploadingText}>⏳ Uploading...</span>
                ) : (
                  <>
                    <span className={styles.productImageIcon}>📷</span>
                    <span className={styles.uploadHint}>Klik untuk upload foto</span>
                  </>
                )}
              </div>
              {p.foto_url && (
                <div className={styles.imageOverlay}>
                  <span>📷 Ganti Foto</span>
                </div>
              )}
            </div>
            <div className={styles.productInfo}>
              <span className={`badge ${getCategoryBadge(p.kategori)}`}>{p.kategori}</span>
              <h4 className={styles.productName}>{p.nama}</h4>
              <p className={styles.productPrice}>Rp {p.harga.toLocaleString("id-ID")}</p>
              <div className={styles.stockRow}>
                <span className={`${styles.stockDot} ${p.stok > 0 ? styles.stockGreen : styles.stockRed}`}></span>
                <span className="text-sm">{p.stok > 0 ? `Stok: ${p.stok}` : "Habis"}</span>
              </div>
            </div>
            <div className={styles.productActions}>
              <button className="btn btn-ghost btn-sm" onClick={() => handleEdit(p)}>✏️</button>
              <button className="btn btn-ghost btn-sm" onClick={() => handleDelete(p.id)}>🗑️</button>
            </div>
          </div>
        ))}
      </div>

      {/* Modal */}
      {showModal && (
        <div className={styles.modalOverlay} onClick={() => setShowModal(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3>{editingProduct ? "Edit Produk" : "Tambah Produk Baru"}</h3>
            <form onSubmit={handleSave} className={styles.modalForm}>
              <div className={styles.field}>
                <label className="label">Nama Produk</label>
                <input className="input" value={form.nama} onChange={(e) => setForm({ ...form, nama: e.target.value })} required />
              </div>
              <div className={styles.field}>
                <label className="label">Deskripsi</label>
                <textarea className="input" rows={3} value={form.deskripsi} onChange={(e) => setForm({ ...form, deskripsi: e.target.value })} />
              </div>
              <div className={styles.fieldRow}>
                <div className={styles.field}>
                  <label className="label">Harga (Rp)</label>
                  <input className="input" type="number" value={form.harga} onChange={(e) => setForm({ ...form, harga: e.target.value })} required />
                </div>
                <div className={styles.field}>
                  <label className="label">Stok</label>
                  <input className="input" type="number" value={form.stok} onChange={(e) => setForm({ ...form, stok: e.target.value })} required />
                </div>
              </div>
              <div className={styles.field}>
                <label className="label">Kategori</label>
                <select className="select" value={form.kategori} onChange={(e) => setForm({ ...form, kategori: e.target.value })}>
                  <option value="umum">Umum</option>
                  <option value="dress">Dress</option>
                  <option value="kaos">Kaos</option>
                  <option value="celana">Celana</option>
                  <option value="hoodie">Hoodie</option>
                  <option value="kemeja">Kemeja</option>
                  <option value="gamis">Gamis</option>
                  <option value="blouse">Blouse</option>
                  <option value="jaket">Jaket</option>
                  <option value="rok">Rok</option>
                </select>
              </div>
              <p className="text-xs text-muted">💡 Foto bisa diupload setelah produk dibuat — klik area foto di kartu produk.</p>
              <div className={styles.modalActions}>
                <button type="button" className="btn btn-outline" onClick={() => setShowModal(false)}>Batal</button>
                <button type="submit" className="btn btn-primary">
                  {editingProduct ? "Simpan Perubahan" : "Tambah Produk"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function getCategoryBadge(cat) {
  const map = { dress: "badge-success", kaos: "badge-info", celana: "badge-warning", hoodie: "badge-neutral", gamis: "badge-primary", blouse: "badge-danger", rok: "badge-info", kemeja: "badge-warning", jaket: "badge-neutral" };
  return map[cat] || "badge-neutral";
}
