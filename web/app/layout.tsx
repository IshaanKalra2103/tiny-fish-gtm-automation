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
          <div className="mx-auto max-w-5xl px-4 py-1 flex items-center justify-between gap-x-4">
            <Link href="/" className="text-xl font-semibold text-ink no-underline py-2.5 whitespace-nowrap">
              {APP_NAME}
            </Link>
            <nav aria-label="Main" className="flex gap-4 text-base">
              <Link href="/demo" className="py-2.5 text-ink/90 no-underline hover:underline">Examples</Link>
              <Link href="/catalog" className="py-2.5 text-ink/90 no-underline hover:underline">Tool catalog</Link>
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
