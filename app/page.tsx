'use client'

import { useState, useRef } from 'react'
import type { ShopResult } from './api/search/route'

// ── i18n ──────────────────────────────────────────────────────────────────────

type Lang = 'en' | 'hi'

const T = {
  en: {
    tagline: 'Shop Finder for India',
    heroTitle: <>Find <em>every shop</em> in your area</>,
    heroSub: 'Search across Google Maps, JustDial & IndiaMART in one click. Built for Indian MSME owners.',
    labelKeyword: <>🔍 What are you looking for? <span className="req">*</span></>,
    labelArea: <>📍 Area / City <span className="req">*</span></>,
    labelComments: '📝 Additional details (optional)',
    placeholderKeyword: 'e.g. CNC laser cutting, stainless steel gate...',
    placeholderArea: 'e.g. Fatehpur, Khaga, Kaushambi...',
    placeholderComments: 'e.g. stainless steel only, near bus stand, wholesale dealer...',
    btnSearch: '🔎 Search Shops',
    quickLabel: 'Quick:',
    searching: 'Searching Google Maps, JustDial, IndiaMART...',
    resultsTitle: (n: number) => <>Found <span>{n}</span> shops</>,
    exportCsv: '📥 Download CSV',
    footer: 'DukaanKhoj — Helping Indian businesses find suppliers & shops.',
    noResults: 'No shops found. Try different keywords or a broader area.',
    noResultsTitle: 'No results found',
    errorMsg: 'Something went wrong. Please try again.',
  },
  hi: {
    tagline: 'भारत के लिए दुकान खोज',
    heroTitle: <>अपने क्षेत्र की <em>हर दुकान</em> खोजें</>,
    heroSub: 'Google Maps, JustDial और IndiaMART पर एक क्लिक में खोजें। भारतीय MSME मालिकों के लिए बनाया गया।',
    labelKeyword: <>🔍 आप क्या खोज रहे हैं? <span className="req">*</span></>,
    labelArea: <>📍 क्षेत्र / शहर <span className="req">*</span></>,
    labelComments: '📝 अतिरिक्त विवरण (वैकल्पिक)',
    placeholderKeyword: 'जैसे: CNC लेजर कटिंग, स्टेनलेस स्टील गेट...',
    placeholderArea: 'जैसे: फतेहपुर, खागा, कौशाम्बी...',
    placeholderComments: 'जैसे: केवल स्टेनलेस स्टील, बस स्टैंड के पास, थोक विक्रेता...',
    btnSearch: '🔎 दुकान खोजें',
    quickLabel: 'जल्दी खोजें:',
    searching: 'Google Maps, JustDial, IndiaMART पर खोज रहे हैं...',
    resultsTitle: (n: number) => <><span>{n}</span> दुकानें मिलीं</>,
    exportCsv: '📥 CSV डाउनलोड करें',
    footer: 'दुकानखोज — भारतीय व्यवसायों को आपूर्तिकर्ता और दुकानें खोजने में मदद।',
    noResults: 'कोई दुकान नहीं मिली। अलग कीवर्ड या बड़ा क्षेत्र आज़माएं।',
    noResultsTitle: 'कोई परिणाम नहीं',
    errorMsg: 'कुछ गलत हो गया। कृपया पुनः प्रयास करें।',
  },
} satisfies Record<Lang, object>

// ── Helpers ───────────────────────────────────────────────────────────────────

function escapeHtml(str: string) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function truncate(str: string, max: number) {
  return str.length > max ? str.slice(0, max) + '…' : str
}

function exportCSV(results: ShopResult[]) {
  const headers = ['Shop Name', 'Address', 'Area', 'Phone', 'Website', 'Rating', 'Reviews', 'Status', 'Hours', 'Maps Link', 'Source']
  const rows = results.map(r => [
    r.name, r.address, r.area, r.phone, r.website,
    r.rating, r.reviews, r.status, r.hours, r.maps_link, r.source,
  ])
  let csv = '\uFEFF' + headers.join(',') + '\n'
  for (const row of rows) {
    csv += row.map(v => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',') + '\n'
  }
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `dukaankhoj_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ── Components ────────────────────────────────────────────────────────────────

function ShopCard({ shop, index }: { shop: ShopResult; index: number }) {
  const stars = shop.rating
    ? '★'.repeat(Math.round(Number(shop.rating))) + '☆'.repeat(5 - Math.round(Number(shop.rating)))
    : ''

  return (
    <div className="shop-card" style={{ animationDelay: `${index * 0.06}s` }}>
      {shop.area && <div className="shop-area-tag">{shop.area}</div>}
      <div className="shop-card-top">
        <div className="shop-name">{shop.name}</div>
        <span className="shop-badge badge-maps">{shop.source}</span>
      </div>
      <div className="shop-meta">
        {shop.address && (
          <div className="meta-row">
            <span className="icon">📍</span>
            <span dangerouslySetInnerHTML={{ __html: escapeHtml(shop.address) }} />
          </div>
        )}
        {shop.phone && (
          <div className="meta-row">
            <span className="icon">📞</span>
            <a href={`tel:${shop.phone}`}>{shop.phone}</a>
          </div>
        )}
        {shop.website && (
          <div className="meta-row">
            <span className="icon">🌐</span>
            <a href={shop.website} target="_blank" rel="noopener noreferrer">
              {truncate(shop.website, 50)}
            </a>
          </div>
        )}
        {shop.hours && (
          <div className="meta-row">
            <span className="icon">🕐</span>
            <span>{truncate(shop.hours, 80)}</span>
          </div>
        )}
        {shop.maps_link && (
          <div className="meta-row">
            <span className="icon">🗺️</span>
            <a href={shop.maps_link} target="_blank" rel="noopener noreferrer">Open in Google Maps</a>
          </div>
        )}
      </div>
      {shop.rating && (
        <div className="shop-rating">
          <span className="stars">{stars}</span>
          {shop.rating} ({shop.reviews ?? 0} reviews)
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Home() {
  const [lang, setLang] = useState<Lang>('en')
  const [keywords, setKeywords] = useState('')
  const [areas, setAreas] = useState('')
  const [comments, setComments] = useState('')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<ShopResult[] | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const resultsRef = useRef<HTMLDivElement>(null)
  const t = T[lang]

  function showToast(msg: string) {
    setToast(msg)
    setTimeout(() => setToast(null), 4000)
  }

  function quickFill(kw: string, area: string) {
    setKeywords(kw)
    setAreas(area)
  }

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!keywords.trim() || !areas.trim()) return

    setLoading(true)
    setResults(null)

    try {
      const resp = await fetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keywords, areas, comments }),
      })

      const data = await resp.json()

      if (!resp.ok) {
        throw new Error(data.message ?? t.errorMsg)
      }

      setResults(data.results ?? [])
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(t.errorMsg)
      showToast(msg)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      {/* Header */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <div className="logo-icon">🏪</div>
            <div>
              <div className="logo-text">Dukaan<span>Khoj</span></div>
              <div className="logo-sub">{t.tagline}</div>
            </div>
          </div>
          <div className="lang-toggle">
            <button
              className={`lang-btn ${lang === 'en' ? 'active' : ''}`}
              onClick={() => setLang('en')}
            >EN</button>
            <button
              className={`lang-btn ${lang === 'hi' ? 'active' : ''}`}
              onClick={() => setLang('hi')}
            >हिं</button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="hero">
        <div className="hero-inner">
          <h1>{t.heroTitle}</h1>
          <p>{t.heroSub}</p>
        </div>
      </section>

      {/* Search */}
      <section className="search-section">
        <div className="search-card">
          <form onSubmit={handleSearch}>
            <div className="form-row">
              <div className="field">
                <label>{t.labelKeyword}</label>
                <input
                  type="text"
                  value={keywords}
                  onChange={e => setKeywords(e.target.value)}
                  placeholder={t.placeholderKeyword}
                  required
                />
              </div>
              <div className="field">
                <label>{t.labelArea}</label>
                <input
                  type="text"
                  value={areas}
                  onChange={e => setAreas(e.target.value)}
                  placeholder={t.placeholderArea}
                  required
                />
              </div>
            </div>
            <div className="form-row">
              <div className="field full">
                <label>{t.labelComments}</label>
                <textarea
                  value={comments}
                  onChange={e => setComments(e.target.value)}
                  rows={2}
                  placeholder={t.placeholderComments}
                />
              </div>
            </div>
            <div className="search-actions">
              <button type="submit" className="btn-search" disabled={loading}>
                {loading
                  ? <span className="spinner" />
                  : t.btnSearch
                }
              </button>
            </div>
          </form>

          <div className="quick-tags">
            <span>{t.quickLabel}</span>
            <button className="tag" onClick={() => quickFill('CNC laser cutting', 'Fatehpur, Khaga')}>CNC Laser Cutting</button>
            <button className="tag" onClick={() => quickFill('stainless steel gate railing', 'Fatehpur')}>SS Gate & Railing</button>
            <button className="tag" onClick={() => quickFill('steel fabrication welding', 'Kaushambi')}>Steel Fabrication</button>
            <button className="tag" onClick={() => quickFill('iron dealer', 'Khaga, Fatehpur')}>Iron Dealer</button>
            <button className="tag" onClick={() => quickFill('aluminium works', 'Khaga')}>Aluminium Works</button>
          </div>
        </div>
      </section>

      {/* Loading */}
      {loading && (
        <div className="loading-state">
          <div className="loader-dots">
            <span /><span /><span />
          </div>
          <p>{t.searching}</p>
        </div>
      )}

      {/* Results */}
      {results !== null && !loading && (
        <section className="results-section" ref={resultsRef}>
          <div className="results-header">
            <h2 className="results-count">{t.resultsTitle(results.length)}</h2>
            {results.length > 0 && (
              <button className="btn-export" onClick={() => exportCSV(results)}>
                {t.exportCsv}
              </button>
            )}
          </div>
          <div className="results-grid">
            {results.length === 0 ? (
              <div className="empty-state">
                <div className="icon">🔍</div>
                <h3>{t.noResultsTitle}</h3>
                <p>{t.noResults}</p>
              </div>
            ) : (
              results.map((shop, i) => <ShopCard key={`${shop.name}-${i}`} shop={shop} index={i} />)
            )}
          </div>
        </section>
      )}

      {/* Footer */}
      <footer className="footer">
        <p>{t.footer}</p>
      </footer>

      {/* Toast */}
      {toast && <div className="toast">{toast}</div>}
    </>
  )
}
