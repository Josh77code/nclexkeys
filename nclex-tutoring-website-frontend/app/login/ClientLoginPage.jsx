"use client"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useState } from "react"
import { toast } from "@/hooks/use-toast"
import { login } from "@/lib/api" // Import the new login function
import RateLimitMessage from "@/components/RateLimitMessage" // Import RateLimitMessage
import { useRouter } from "next/navigation" // Import useRouter

export default function ClientLoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [isPending, setIsPending] = useState(false)
  const [message, setMessage] = useState("")
  const [rateLimitError, setRateLimitError] = useState(null)
  const [requires2FA, setRequires2FA] = useState(false)
  const [twoFactorToken, setTwoFactorToken] = useState("")
  const [backupCode, setBackupCode] = useState("")

  const handleLogin = async (e) => {
    e.preventDefault()
    setIsPending(true)
    setMessage("")
    setRateLimitError(null)
    setRequires2FA(false)

    const result = await login({ email, password, twoFactorToken, backupCode })

    if (result.success) {
      toast({
        title: "Login Successful",
        description: "Redirecting to dashboard...",
      })
      router.push("/dashboard")
    } else if (result.requires2FA) {
      setRequires2FA(true)
      setMessage("Two-factor authentication required. Please enter your 2FA token or backup code.")
      toast({
        title: "2FA Required",
        description: "Please enter your 2FA token or backup code.",
        variant: "default",
      })
    } else if (result.error?.isRateLimited) {
      setRateLimitError(result.error)
      toast({
        title: "Rate Limit Exceeded",
        description: result.error.message,
        variant: "destructive",
      })
    } else if (result.error?.isLocked) {
      setMessage(result.error.message)
      toast({
        title: "Account Locked",
        description: result.error.message,
        variant: "destructive",
      })
    } else {
      setMessage(result.error?.message || "Login failed. Please check your credentials.")
      toast({
        title: "Login Failed",
        description: result.error?.message || "Invalid email or password.",
        variant: "destructive",
      })
    }
    setIsPending(false)
  }

  const handleRetry = () => {
    setRateLimitError(null)
    // Optionally re-enable form fields or trigger login attempt again
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f0f4ff] to-[#e0e8ff] py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8">
        <CardHeader className="text-center">
          <CardTitle className="text-3xl font-bold text-gray-800">Sign In</CardTitle>
          <CardDescription className="text-gray-600 mt-2">Access your NCLEX Prep account.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="email">Email Address</Label>
              <Input
                id="email"
                type="email"
                name="email"
                placeholder="you@example.com"
                required
                disabled={isPending || requires2FA}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                name="password"
                placeholder="********"
                required
                disabled={isPending || requires2FA}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {requires2FA && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="twoFactorToken">2FA Token</Label>
                  <Input
                    id="twoFactorToken"
                    type="text"
                    name="twoFactorToken"
                    placeholder="Enter 2FA code"
                    required
                    disabled={isPending}
                    value={twoFactorToken}
                    onChange={(e) => setTwoFactorToken(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="backupCode">Backup Code (Optional)</Label>
                  <Input
                    id="backupCode"
                    type="text"
                    name="backupCode"
                    placeholder="Enter backup code"
                    disabled={isPending}
                    value={backupCode}
                    onChange={(e) => setBackupCode(e.target.value)}
                  />
                </div>
              </>
            )}

            <Button
              type="submit"
              className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
              disabled={isPending}
            >
              {isPending ? "Signing In..." : "Sign In"}
            </Button>
          </form>
          {message && (
            <p
              className={`mt-4 text-center text-sm ${message.includes("failed") || message.includes("Locked") ? "text-red-500" : "text-green-500"}`}
            >
              {message}
            </p>
          )}
          {rateLimitError && <RateLimitMessage error={rateLimitError} onRetry={handleRetry} />}
          <p className="mt-6 text-center text-sm text-gray-600">
            Don't have an account?{" "}
            <Link href="/register" className="text-[#4F46E5] hover:underline">
              Register Now
            </Link>
          </p>
          <p className="mt-2 text-center text-sm text-gray-600">
            <Link href="/forgot-password" className="text-[#4F46E5] hover:underline">
              Forgot Password?
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
