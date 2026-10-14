import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Support AcePressure",
  description: "A quiet, exact-amount support page for the AcePressure stream.",
  icons: { icon: "/favicon.svg" }
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
