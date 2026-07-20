import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Culprit",
  description:
    "Deployment-aware root cause analysis: what changed, and is that the cause?",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* ponytail: dark palette only for v1 — light theme lands with the
          design-system pass, per docs/08-ui-design.md */}
      <body className="min-h-full flex flex-col bg-zinc-950 text-zinc-200">
        <header className="border-b border-zinc-800 px-6 py-3 flex items-center gap-6">
          <Link href="/incidents" className="font-semibold tracking-tight text-zinc-50">
            Culprit
          </Link>
          <nav className="text-sm text-zinc-400">
            <Link href="/incidents" className="hover:text-zinc-100">
              Incidents
            </Link>
          </nav>
          <span className="ml-auto text-xs text-zinc-600 font-mono">
            simulation data · harness v1
          </span>
        </header>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
