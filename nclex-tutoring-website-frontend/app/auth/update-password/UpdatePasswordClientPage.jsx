"use client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useState, useEffect } from "react"
import { toast } from "@/hooks/use-toast"
import { resetPassword } from "@/lib/api" // Import the new resetPassword function
import RateLimitMessage from "@/components/RateLimitMessage" // Import RateLimitMessage
import { useSearchParams, useRouter } from "next/navigation" // Import useSearchParams and useRouter

export default function UpdatePasswordClientPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [isPending, setIsPending] = useState(false)
  const [message, setMessage] = useState("")
  const [rateLimitError, setRateLimitError] = useState(null)
  const [resetToken, setResetToken] = useState(null)

  useEffect(() => {
    const token = searchParams.get("token")
    if (token) {
      setResetToken(token)
    } else {
      setMessage("No reset token found in the URL. Please use the 'Forgot Password' link.")
      toast({
        title: "Invalid Link",
        description: "No reset token found. Please request a new password reset link.",
        variant: "destructive",
      })
    }
  }, [searchParams])

  const handleUpdatePassword = async (e) => {
    e.preventDefault()
    setIsPending(true)
    setMessage("")
    setRateLimitError(null)

    if (!resetToken) {
      setMessage("Missing reset token. Cannot update password.")
      toast({ title: "Error", description: "Missing reset token.", variant: "destructive" })
      setIsPending(false)
      return
    }

    if (password !== confirmPassword) {
      setMessage("Passwords do not match.")
      toast({ title: "Update Failed", description: "Passwords do not match.", variant: "destructive" })
      setIsPending(false)
      return
    }

    const result = await resetPassword(resetToken, password)

    if (result.success) {
      setMessage("Your password has been updated successfully!")
      toast({
        title: "Password Updated",
        description: "Your password has been updated successfully!",
      })
      setPassword("")
      setConfirmPassword("")
      router.push("/login") // Redirect to login page
    } else if (result.error?.isRateLimited) {
      setRateLimitError(result.error)
      toast({
        title: "Rate Limit Exceeded",
        description: result.error.message,
        variant: "destructive",
      })
    } else {
      setMessage(result.error?.message || "Failed to update password. Please try again.")
      toast({
        title: "Update Failed",
        description: result.error?.message || "Failed to update password.",
        variant: "destructive",
      })
    }
    setIsPending(false)
  }

  const handleRetry = () => {
    setRateLimitError(null)
    // Optionally re-enable form fields or trigger update attempt again
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f0f4ff] to-[#e0e8ff] py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8">
        <CardHeader className="text-center">
          <CardTitle className="text-3xl font-bold text-gray-800">Set New Password</CardTitle>
          <CardDescription className="text-gray-600 mt-2">Enter your new password below.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleUpdatePassword} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="password">New Password</Label>
              <Input
                id="password"
                type="password"
                name="password"
                placeholder="********"
                required
                disabled={isPending || !resetToken}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm New Password</Label>
              <Input
                id="confirmPassword"
                type="password"
                name="confirmPassword"
                placeholder="********"
                required
                disabled={isPending || !resetToken}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>

            <Button
              type="submit"
              className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
              disabled={isPending || !resetToken}
            >
              {isPending ? "Updating Password..." : "Update Password"}
            </Button>
          </form>
          {message && (
            <p
              className={`mt-4 text-center text-sm ${message.includes("match") || message.includes("Error") || message.includes("Missing") ? "text-red-500" : "text-green-500"}`}
            >
              {message}
            </p>
          )}
          {rateLimitError && <RateLimitMessage error={rateLimitError} onRetry={handleRetry} />}
        </CardContent>
      </Card>
    </div>
  )
}
