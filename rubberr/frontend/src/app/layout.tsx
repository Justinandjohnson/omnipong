import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import VoiceAgentWrapper from "@/components/VoiceAgentWrapper";

import { ArcadeProvider } from "@/context/ArcadeContext";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Rubberr - AI Coach",
  description: "Next-gen Table Tennis Intelligence",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <ArcadeProvider>
          {children}
          <VoiceAgentWrapper />
        </ArcadeProvider>
      </body>
    </html>
  );
}
