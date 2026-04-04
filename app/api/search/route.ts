import { NextRequest, NextResponse } from 'next/server'
import { privateKeyToAccount } from 'viem/accounts'
import { getAddress } from 'viem'

const STABLEENRICH = 'https://stableenrich.dev'
const WALLET_PRIVATE_KEY = process.env.WALLET_PRIVATE_KEY ?? ''

const AREA_COORDS: Record<string, { lat: number; lng: number }> = {
  fatehpur:   { lat: 25.93, lng: 80.81 },
  khaga:      { lat: 25.74, lng: 81.00 },
  kaushambi:  { lat: 25.53, lng: 81.37 },
  manjhanpur: { lat: 25.53, lng: 81.37 },
  sirathu:    { lat: 25.63, lng: 81.34 },
  prayagraj:  { lat: 25.43, lng: 81.84 },
  allahabad:  { lat: 25.43, lng: 81.84 },
  kanpur:     { lat: 26.45, lng: 80.35 },
  lucknow:    { lat: 26.85, lng: 80.95 },
  agra:       { lat: 27.18, lng: 78.02 },
  varanasi:   { lat: 25.32, lng: 83.01 },
  banda:      { lat: 25.48, lng: 80.34 },
  delhi:      { lat: 28.61, lng: 77.23 },
  noida:      { lat: 28.57, lng: 77.32 },
  ghaziabad:  { lat: 28.67, lng: 77.42 },
  jaipur:     { lat: 26.91, lng: 75.79 },
  patna:      { lat: 25.60, lng: 85.10 },
  bhopal:     { lat: 23.26, lng: 77.41 },
  indore:     { lat: 22.72, lng: 75.86 },
  mumbai:     { lat: 19.08, lng: 72.88 },
  pune:       { lat: 18.52, lng: 73.86 },
  hyderabad:  { lat: 17.39, lng: 78.49 },
  bangalore:  { lat: 12.97, lng: 77.59 },
  chennai:    { lat: 13.08, lng: 80.27 },
  kolkata:    { lat: 22.57, lng: 88.36 },
  ahmedabad:  { lat: 23.02, lng: 72.57 },
  surat:      { lat: 21.17, lng: 72.83 },
  nagpur:     { lat: 21.15, lng: 79.09 },
  raipur:     { lat: 21.25, lng: 81.63 },
  meerut:     { lat: 28.98, lng: 77.71 },
  bareilly:   { lat: 28.37, lng: 79.42 },
  gorakhpur:  { lat: 26.76, lng: 83.37 },
  burhanpur:  { lat: 21.31, lng: 76.23 },
}

export interface ShopResult {
  name: string
  address: string
  area: string
  phone: string
  website: string
  rating: number | string
  reviews: number | string
  status: string
  hours: string
  maps_link: string
  source: string
}

// ── x402 payment ──────────────────────────────────────────────────────────────

interface Accept {
  scheme: string
  network: string
  amount: string
  asset: string
  payTo: string
  maxTimeoutSeconds?: number
  extra?: { name?: string; version?: string }
}

interface PaymentRequired {
  x402Version: number
  accepts: Accept[]
  resource?: string
  extensions?: Record<string, unknown>
}

async function signX402Payment(accept: Accept, paymentRequired: PaymentRequired): Promise<object> {
  const key = (WALLET_PRIVATE_KEY.startsWith('0x') ? WALLET_PRIVATE_KEY : `0x${WALLET_PRIVATE_KEY}`) as `0x${string}`
  const account = privateKeyToAccount(key)

  const now = Math.floor(Date.now() / 1000)
  const nonce = `0x${Buffer.from(crypto.getRandomValues(new Uint8Array(32))).toString('hex')}` as `0x${string}`

  const authorization = {
    from: account.address,
    to: getAddress(accept.payTo),
    value: accept.amount,
    validAfter: (now - 600).toString(),
    validBefore: (now + (accept.maxTimeoutSeconds ?? 300)).toString(),
    nonce,
  }

  const signature = await account.signTypedData({
    domain: {
      name: accept.extra?.name ?? 'USD Coin',
      version: accept.extra?.version ?? '2',
      chainId: 8453,
      verifyingContract: getAddress(accept.asset) as `0x${string}`,
    },
    types: {
      TransferWithAuthorization: [
        { name: 'from',        type: 'address' },
        { name: 'to',          type: 'address' },
        { name: 'value',       type: 'uint256' },
        { name: 'validAfter',  type: 'uint256' },
        { name: 'validBefore', type: 'uint256' },
        { name: 'nonce',       type: 'bytes32' },
      ],
    },
    primaryType: 'TransferWithAuthorization',
    message: {
      from: account.address,
      to: getAddress(accept.payTo) as `0x${string}`,
      value: BigInt(accept.amount),
      validAfter: BigInt(authorization.validAfter),
      validBefore: BigInt(authorization.validBefore),
      nonce,
    },
  })

  // x402 v2 payload: includes accepted + resource (no scheme/network at top level)
  return {
    x402Version: 2,
    payload: { authorization, signature },
    extensions: paymentRequired.extensions ?? {},
    resource: paymentRequired.resource,
    accepted: accept,
  }
}

async function x402Post(url: string, body: object): Promise<unknown> {
  const init: RequestInit = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }

  let res: Response
  try {
    res = await fetch(url, init)
  } catch (err) {
    console.error(`[x402] Network error fetching ${url}:`, err)
    throw new Error(`Cannot reach stableenrich.dev — check your internet connection or DNS. (${(err as Error).message})`)
  }

  if (res.status === 402) {
    if (!WALLET_PRIVATE_KEY) {
      console.error('[x402] WALLET_PRIVATE_KEY not set')
      return null
    }
    try {
      // payment-required header is base64-encoded JSON (x402 v2)
      const payHeader = res.headers.get('payment-required')
      if (!payHeader) {
        console.error('[x402] No payment-required header')
        return null
      }

      const paymentRequired = JSON.parse(Buffer.from(payHeader, 'base64').toString()) as PaymentRequired

      // Pick the Base network accept
      const accept = paymentRequired.accepts.find(a => a.network === 'eip155:8453')
      if (!accept) {
        console.error('[x402] No eip155:8453 option in accepts')
        return null
      }

      const payment = await signX402Payment(accept, paymentRequired)
      // x402 v2: header is PAYMENT-SIGNATURE, value is base64-encoded JSON
      const paymentEncoded = Buffer.from(JSON.stringify(payment)).toString('base64')

      res = await fetch(url, {
        ...init,
        headers: { 'Content-Type': 'application/json', 'PAYMENT-SIGNATURE': paymentEncoded },
      })

      if (!res.ok) {
        const errText = await res.text()
        console.error(`[x402] retry failed ${res.status}:`, errText)
        return null
      }
    } catch (err) {
      console.error('[x402] Payment error:', err)
      return null
    }
  }

  if (!res.ok) {
    console.error(`[stableenrich] ${res.status} ${url}`)
    return null
  }

  return res.json()
}

// ── Firecrawl ─────────────────────────────────────────────────────────────────

interface SearchResult {
  title: string
  url: string
  description: string
  snippet?: string
}

async function firecrawlSearch(query: string, limit = 5): Promise<SearchResult[]> {
  const data = await x402Post(`${STABLEENRICH}/api/firecrawl/search`, { query, limit }) as { results?: SearchResult[] } | null
  return data?.results ?? []
}

async function firecrawlScrape(url: string): Promise<string> {
  const data = await x402Post(`${STABLEENRICH}/api/firecrawl/scrape`, { url }) as { content?: string; markdown?: string } | null
  return data?.content ?? data?.markdown ?? ''
}

// ── Markdown parser ───────────────────────────────────────────────────────────

function parseShopsFromMarkdown(content: string, sourceUrl: string, areaName: string): ShopResult[] {
  const source = sourceUrl.includes('justdial') ? 'JustDial'
    : sourceUrl.includes('indiamart') ? 'IndiaMART'
    : 'Web'

  const shops: ShopResult[] = []

  // Extract shop name from markdown link text: [Name](url) → Name
  function stripMarkdownLinks(line: string): string {
    return line.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/[*#_|]/g, '').trim()
  }

  // JustDial format: shop entries start with "## [Shop Name](url)"
  // Split on h2 headings which mark each shop entry
  const shopBlocks = content.split(/(?=^## )/m).filter(b => b.startsWith('## '))

  for (const block of shopBlocks) {
    const lines = block.split('\n').map(l => l.trim()).filter(Boolean)
    if (lines.length < 2) continue

    // First line is always "## [Shop Name](url)"
    const name = stripMarkdownLinks(lines[0])
    if (!name || name.length < 4 || name.length > 80) continue
    // Skip article headings and navigation — real shop names don't start like this
    if (/^(table of contents|history of|types of|applications|manufacturing|factors to|indian market|maintenance|introduction|overview|what is|how to|benefits|advantages|disadvantages|find|search|top|popular|home|menu|footer|advertisement|skip to)/i.test(name)) continue
    // Real shop listings have ratings or address nearby — article pages don't
    const hasShopSignal = /\d\.\d/.test(block) || /Ratings?/i.test(block) || /Opens?\s+at/i.test(block) || /Show Number/i.test(block)
    if (!hasShopSignal) continue

    // Rating: "- 4.9" followed by "- 72 Ratings"
    const ratingMatch = block.match(/[-\s](\d\.\d)\s*\n/)
    const rating = ratingMatch ? parseFloat(ratingMatch[1]) : ''

    const reviewMatch = block.match(/(\d+)\s*Ratings?/i)
    const reviews = reviewMatch ? parseInt(reviewMatch[1]) : ''

    // Address: line with location keywords
    const address = lines.find(l => {
      const clean = stripMarkdownLinks(l)
      return clean !== name && clean.length > 10 &&
        /(\d{6}|\b(uttar\s*pradesh|fatehpur|khaga|kaushambi|kanpur|lucknow|allahabad|prayagraj|delhi|mumbai|road|nagar|colony|market|chowk|bazaar|sector|phase|block)\b)/i.test(clean)
    })?.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1').replace(/[*#_|]/g, '').trim() ?? ''

    // Phone: Indian mobile (6-9 prefix, 10 digits)
    const phoneMatch = block.match(/(?:\+91[\s-]?)?[6-9]\d{9}/)
    const phone = phoneMatch ? phoneMatch[0].trim() : ''

    const opensMatch = block.match(/Opens?\s+at\s+[\d:]+\s*[ap]m/i)
    const hours = opensMatch ? opensMatch[0].trim() : ''

    shops.push({
      name,
      address,
      area: areaName,
      phone,
      website: sourceUrl,
      rating,
      reviews,
      status: /opens?\s+at/i.test(block) ? 'OPERATIONAL' : '',
      hours,
      maps_link: '',
      source,
    })
  }

  return shops
}

// ── Area parsing ──────────────────────────────────────────────────────────────

function parseAreas(areaText: string): Array<{ name: string }> | null {
  const lower = areaText.toLowerCase().trim()
  const matched = Object.keys(AREA_COORDS)
    .filter(name => lower.includes(name))
    .map(name => ({ name: name.charAt(0).toUpperCase() + name.slice(1) }))
  return matched.length > 0 ? matched : null
}

// ── Route ─────────────────────────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  let body: Record<string, string> = {}
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 })
  }

  const keywords = (body.keywords ?? '').trim()
  const areasInput = (body.areas ?? '').trim()
  const comments = (body.comments ?? '').trim()

  if (!keywords || !areasInput) {
    return NextResponse.json({ error: 'keywords and areas are required' }, { status: 400 })
  }

  if (!WALLET_PRIVATE_KEY) {
    return NextResponse.json(
      { error: 'server_misconfigured', message: 'WALLET_PRIVATE_KEY is not set on the server.' },
      { status: 503 },
    )
  }

  const areaList = parseAreas(areasInput)
  if (!areaList) {
    const known = Object.keys(AREA_COORDS).sort().join(', ')
    return NextResponse.json(
      { error: 'area_not_recognized', message: `Could not find "${areasInput}" in our list. Try: ${known}` },
      { status: 400 },
    )
  }

  const results: ShopResult[] = []
  const seen = new Set<string>()
  const query = comments ? `${keywords} ${comments}` : keywords

  try {
  for (const area of areaList) {
    // Search JustDial and IndiaMART in parallel
    const [jdResults, imResults] = await Promise.all([
      firecrawlSearch(`${query} ${area.name} Uttar Pradesh site:justdial.com`, 5),
      firecrawlSearch(`${query} ${area.name} site:indiamart.com`, 5),
    ])

    // Scrape top 3 listing pages (mix of JD + IM)
    const toScrape = [...jdResults, ...imResults]
      .filter(r => (r.url.includes('justdial.com') || r.url.includes('indiamart.com')) && !r.url.includes('/jdmart/'))
      .slice(0, 3)
      .map(r => r.url)

    const markdowns = await Promise.all(toScrape.map(url => firecrawlScrape(url)))

    for (let i = 0; i < toScrape.length; i++) {
      const shops = parseShopsFromMarkdown(markdowns[i], toScrape[i], area.name)
      for (const shop of shops) {
        const key = shop.name.toLowerCase().trim()
        if (!seen.has(key)) {
          seen.add(key)
          results.push(shop)
        }
      }
    }
  }

  } catch (err) {
    const message = (err as Error).message ?? 'Unknown error'
    console.error('[search] fatal error:', err)
    return NextResponse.json(
      { error: 'search_failed', message },
      { status: 502 },
    )
  }

  return NextResponse.json({
    results,
    count: results.length,
    search: { keywords, areas: areasInput, comments },
    timestamp: new Date().toISOString(),
  })
}
