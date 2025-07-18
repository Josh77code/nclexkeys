"use client" // Error components must be Client Components

import { useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import Link from "next/link"

export default function Error({ error, reset }) {
  useEffect(() => {
    // Log the error to an error reporting service
    console.error(error)
  }, [error])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f0f4ff] to-[#e0e8ff] py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8 text-center">
        <CardHeader>
          <CardTitle className="text-3xl font-bold text-red-600">Oops! Something Went Wrong</CardTitle>
          <CardDescription className="text-gray-600 mt-2">
            We apologize, but an unexpected error occurred.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <p className="text-gray-700 text-lg">
            {error.message || "Please try again or navigate back to the homepage."}
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Button
              onClick={
                // Attempt to recover by trying to re-render the segment
                // Ensure reset is a function before calling it
                typeof reset === "function" ? () => reset() : undefined
              }
              className="bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
              disabled={typeof reset !== "function"}
            >
              Try Again
            </Button>
            <Button
              asChild
              variant="outline"
              className="text-[#4F46E5] border-[#4F46E5] hover:bg-[#4F46E5] hover:text-white bg-transparent"
            >
              <Link href="/">Go to Homepage</Link>
            </Button>
          </div>
          {error.digest && <p className="text-xs text-gray-500 mt-4">Error ID: {error.digest}</p>}
        </CardContent>
      </Card>
    </div>
  )
}
