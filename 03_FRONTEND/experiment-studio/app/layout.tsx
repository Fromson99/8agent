import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'),
  title: 'AX Experiment Studio',
  description: '온톨로지와 Golden 기반으로 기업 AX 실험을 설계·비교·승격하는 실험 운영 환경',
  openGraph: {
    title: 'AX Experiment Studio',
    description: 'Golden으로 증명하는 기업 AX 실험 환경',
    images: ['/og.png'],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AX Experiment Studio',
    description: 'Golden으로 증명하는 기업 AX 실험 환경',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
