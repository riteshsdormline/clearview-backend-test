import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Clearview",
  description: "Clearview image inspection and object detection",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
