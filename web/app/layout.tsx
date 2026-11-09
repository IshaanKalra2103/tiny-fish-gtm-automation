import type { Metadata } from "next";
import { Fraunces, Source_Sans_3 } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { APP_NAME, TAGLINE } from "@/lib/brand";
import NavLinks from "@/components/NavLinks";

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
        <header className="border-b border-line/70 bg-white/60 backdrop-blur">
          <div className="mx-auto max-w-5xl px-4 py-1 flex items-center justify-between gap-x-4">
            <Link href="/" className="text-xl font-semibold text-ink !no-underline py-2.5 whitespace-nowrap">
              {APP_NAME}<span aria-hidden className="ml-1 inline-block size-1.5 rounded-full bg-accent align-middle" />
            </Link>
            <NavLinks />
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-line/70 mt-16">
          <div className="mx-auto max-w-5xl px-4 py-8 text-soft text-base">
            {APP_NAME} is a prototype built for the AI for Small Business hackathon. Scores marked simulated come from
            practice runs, not real customers.
          </div>
        </footer>
      </body>
    </html>
  );
}
