"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ArrowLeft, Loader2, CheckCircle } from "lucide-react"

export default function ClientExamPage() {
  const [isVerifying, setIsVerifying] = useState(true)
  const [verificationComplete, setVerificationComplete] = useState(false)
  const externalExamUrl = "https://www.exam.com" // Placeholder for the external exam website

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsVerifying(false)
      setVerificationComplete(true)
    }, 3000) // Simulate a 3-second verification process

    return () => clearTimeout(timer)
  }, [])

  const handleProceedToExam = () => {
    window.open(externalExamUrl, "_blank") // Open the external URL in a new tab
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f0f4ff] to-[#e0e8ff] py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8 text-center">
        <CardHeader>
          <CardTitle className="text-3xl font-bold text-gray-800">
            {isVerifying ? "Verifying Connection" : "Verification Complete!"}
          </CardTitle>
          <CardDescription className="text-gray-600 mt-2">
            {isVerifying
              ? "Verifying you are human. This may take a few seconds."
              : "Your connection has been secured. You can now proceed to the exam."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {isVerifying ? (
            <div className="flex flex-col items-center justify-center gap-4">
              <Loader2 className="h-16 w-16 text-[#4F46E5] animate-spin" />
              <p className="text-lg text-gray-700">Verifying...</p>
              <p className="text-sm text-gray-500">
                {externalExamUrl.replace("https://", "")} needs to review the security of your connection before
                proceeding.
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center gap-4">
              <CheckCircle className="h-16 w-16 text-green-500" />
              <p className="text-lg text-gray-700">Ready to proceed!</p>
              <Button
                onClick={handleProceedToExam}
                className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
              >
                Proceed to {externalExamUrl.replace("https://", "")}
              </Button>
            </div>
          )}

          <Button
            asChild
            variant="outline"
            className="w-full text-[#4F46E5] border-[#4F46E5] hover:bg-[#4F46E5] hover:text-white bg-transparent"
          >
            <Link href="/dashboard">
              <ArrowLeft className="h-4 w-4 mr-2" /> Back to Dashboard
            </Link>
          </Button>

          <div className="text-xs text-gray-500 mt-8">
            <p>Ray ID: {Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15)}</p>
            <p>
              Performance & security by{" "}
              <a href="https://www.cloudflare.com" target="_blank" rel="noopener noreferrer" className="underline">
                Cloudflare
              </a>
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
