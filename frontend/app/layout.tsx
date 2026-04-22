import type { Metadata } from "next";
import Script from "next/script";

import "./globals.css";

export const metadata: Metadata = {
  title: "RAVEN",
  description: "Semi-autonomous IT remediation platform",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Script id="theme-init" strategy="beforeInteractive">
          {`(() => {
            const stored = window.localStorage.getItem("raven-theme");
            const preferred = stored === "dark" || stored === "light"
              ? stored
              : (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
            document.documentElement.classList.toggle("dark", preferred === "dark");
            document.documentElement.dataset.theme = preferred;
          })();`}
        </Script>
        {children}
      </body>
    </html>
  );
}
