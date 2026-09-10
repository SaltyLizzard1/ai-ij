import { Inter } from "next/font/google";
import "./globals.css";
import Nav from "@/components/Nav";
import type { Metadata } from "next";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Your Voice",
  description: "Content creation trained on your voice",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-stone-50 min-h-screen`}>
        <Nav />
        <main className="max-w-3xl mx-auto px-6 py-12">{children}</main>
      </body>
    </html>
  );
}
