import type React from "react"
import type { Metadata } from "next"
import "./globals.css"
import { AuthProvider } from "@/contexts/AuthContext" // Import AuthProvider
import { Toaster } from "@/components/ui/toaster" // Assuming you have a Toaster component for toasts

export const metadata: Metadata = {
  title: {
    default: "NCLEX Virtual School - Master Your Exam",
    template: "%s | NCLEX Virtual School",
  },
  description:
    "Your trusted partner for NCLEX success. Providing expert virtual tutoring and comprehensive resources for aspiring nurses.",
  keywords: ["NCLEX", "nursing", "tutoring", "exam prep", "virtual school", "nursing school", "NCLEX-RN", "NCLEX-PN"],
  authors: [{ name: "NCLEX Virtual School Team" }],
  creator: "NCLEX Virtual School",
  publisher: "NCLEX Virtual School",
  openGraph: {
    title: "NCLEX Virtual School - Master Your Exam",
    description:
      "Your trusted partner for NCLEX success. Providing expert virtual tutoring and comprehensive resources for aspiring nurses.",
    url: "https://www.nclexvirtualschool.com", // Replace with your actual domain
    siteName: "NCLEX Virtual School",
    images: [
      {
        url: "/placeholder.svg?height=630&width=1200", // Replace with a relevant image for social sharing
        width: 1200,
        height: 630,
        alt: "NCLEX Virtual School Banner",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "NCLEX Virtual School - Master Your Exam",
    description:
      "Your trusted partner for NCLEX success. Providing expert virtual tutoring and comprehensive resources for aspiring nurses.",
    images: ["/placeholder.svg?height=675&width=1200"], // Replace with a relevant image for Twitter
    creator: "@NCLEXVirtual", // Replace with your Twitter handle
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  icons: {
    icon: "/favicon.ico", // Ensure you have a favicon.ico in your public folder
    shortcut: "/favicon-16x16.png",
    apple: "/apple-touch-icon.png",
  },
  manifest: "/site.webmanifest",
    generator: 'v0.dev'
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          {children}
          <Toaster /> {/* Ensure Toaster is rendered for toast notifications */}
        </AuthProvider>
      </body>
    </html>
  )
}
