"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useState } from "react"
import { toast } from "@/hooks/use-toast"
import { forgotPassword } from "@/lib/api" // Import the new forgotPassword function
import RateLimitMessage from "@/components/RateLimitMessage" // Import RateLimitMessage

export default function ForgotPasswordClientPage() {
  const [email, setEmail] = useState("")
  const [isPending, setIsPending] = useState(false)
  const [message, setMessage] = useState("")
  const [rateLimitError, setRateLimitError] = useState(null)

  const handleResetPassword = async (e) => {
    e.preventDefault()
    setIsPending(true)
    setMessage("")
    setRateLimitError(null)

    const result = await forgotPassword(email)

    if (result.success) {
      setMessage("Password reset email sent. Check your inbox!")
      toast({ title: "Reset Link Sent", description: "Check your inbox for the reset link." })
    } else if (result.error?.isRateLimited) {
      setRateLimitError(result.error)
      toast({
        title: "Rate Limit Exceeded",
        description: result.error.message,
        variant: "destructive",
      })
    } else {
      setMessage(result.error?.message || "Failed to send reset link. Please check the email address.")
      toast({
        title: "Error",
        description: result.error?.message || "Failed to send reset link.",
        variant: "destructive",
      })
    }
    setIsPending(false)
  }

  const handleRetry = () => {
    setRateLimitError(null)
    // Optionally re-enable form fields or trigger reset attempt again
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f0f4ff] to-[#e0e8ff] py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8">
        <CardHeader className="text-center">
          <CardTitle className="text-3xl font-bold text-gray-800">Forgot Password?</CardTitle>
          <CardDescription className="text-gray-600 mt-2">
            Enter your email to receive a password reset link.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleResetPassword} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="email">Email Address</Label>
              <Input
                id="email"
                type="email"
                name="email"
                placeholder="you@example.com"
                required
                disabled={isPending}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <Button
              type="submit"
              className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
              disabled={isPending}
            >
              {isPending ? "Sending Link..." : "Send Reset Link"}
            </Button>
          </form>
          {message && (
            <p className={`mt-4 text-center text-sm ${message.includes("Error") ? "text-red-500" : "text-green-500"}`}>
              {message}
            </p>
          )}
          {rateLimitError && <RateLimitMessage error={rateLimitError} onRetry={handleRetry} />}
          <p className="mt-6 text-center text-sm text-gray-600">
            Remember your password?{" "}
            <Link href="/login" className="text-[#4F46E5] hover:underline">
              Sign In
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
