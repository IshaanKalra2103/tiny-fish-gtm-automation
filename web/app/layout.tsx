import type { Metadata } from "next";
import { Fraunces, Source_Sans_3 } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { APP_NAME, TAGLINE } from "@/lib/brand";

const fraunces = Fraunces({ variable: "--font-fraunces", subsets: ["latin"] });
const source = Source_Sans_3({ variable: "--font-source", subsets: ["latin"] });

export const metadata: Metadata = {
  title: { default: APP_NAME, template: `%s | ${APP_NAME}` },
  description: TAGLINE,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${fraunces.variable} ${source.variable}`}>
      <body className="min-h-screen flex flex-col overflow-x-hidden">
        <header className="border-b border-line">
          <div className="mx-auto max-w-5xl px-4 py-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-1">
            <Link href="/" className="font-serif text-2xl font-semibold text-ink no-underline py-2">
              {APP_NAME}
            </Link>
            <nav aria-label="Main" className="flex gap-5">
              <Link href="/demo" className="py-2 text-ink">Example businesses</Link>
              <Link href="/catalog" className="py-2 text-ink">Tool catalog</Link>
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-line mt-16">
          <div className="mx-auto max-w-5xl px-4 py-8 text-soft text-base">
            {APP_NAME} is a prototype built for the AI for Small Business hackathon. Scores marked simulated come from
            practice runs, not real customers.
          </div>
        </footer>
      </body>
    </html>
  );
}
