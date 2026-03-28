import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Options Edge",
  description: "AI-powered options trade thesis platform",
};

const navLinks = [
  { href: "/", label: "Discovery" },
  { href: "/validate", label: "Validate" },
  { href: "/watchlist", label: "Watchlist" },
  { href: "/history", label: "History" },
  { href: "/active", label: "Active Trades" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen flex flex-col">
        <header className="bg-slate-900 text-white shadow-md">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center gap-8">
            <span className="text-xl font-bold tracking-tight text-blue-400">
              Options Edge
            </span>
            <nav className="flex gap-6">
              {navLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="text-sm text-slate-300 hover:text-white transition-colors"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">{children}</main>
        <footer className="bg-slate-100 border-t text-center text-xs text-slate-400 py-3">
          Options Edge — for research and educational purposes only. Not financial advice.
        </footer>
      </body>
    </html>
  );
}
