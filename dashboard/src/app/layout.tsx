import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Science AI — Research Dashboard",
  description: "AI-driven scientific research assistant for optical phased arrays",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased">
        {/* Floating orbs */}
        <div className="orb orb-1" />
        <div className="orb orb-2" />
        <div className="orb orb-3" />

        <Sidebar />

        <main className="ml-72 p-6 min-h-screen">
          {children}
        </main>
      </body>
    </html>
  );
}
