import type { Metadata } from 'next'
import { Libre_Baskerville, DM_Sans, Noto_Sans_Devanagari } from 'next/font/google'
import './globals.css'

const libreBaskerville = Libre_Baskerville({
  weight: ['400', '700'],
  subsets: ['latin'],
  variable: '--font-serif',
  display: 'swap',
})

const dmSans = DM_Sans({
  weight: ['400', '500', '600', '700'],
  subsets: ['latin'],
  variable: '--font-sans',
  display: 'swap',
})

const notoDevanagari = Noto_Sans_Devanagari({
  weight: ['400', '600', '700'],
  subsets: ['devanagari'],
  variable: '--font-devanagari',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'DukaanKhoj - Shop Finder for Indian Businesses',
  description: 'Search across Google Maps, JustDial & IndiaMART in one click. Built for Indian MSME owners.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${dmSans.variable} ${libreBaskerville.variable} ${notoDevanagari.variable}`}>
        {children}
      </body>
    </html>
  )
}
