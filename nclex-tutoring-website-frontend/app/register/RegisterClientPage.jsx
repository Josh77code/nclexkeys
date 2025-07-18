"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "@/hooks/use-toast"
import { Checkbox } from "@/components/ui/checkbox"
import { Loader2 } from "lucide-react"
import { register } from "@/lib/api" // Import the new register function
import RateLimitMessage from "@/components/RateLimitMessage" // Import RateLimitMessage

export default function RegisterClientPage() {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [acceptTerms, setAcceptTerms] = useState(false)
  const [isPending, setIsPending] = useState(false)
  const [message, setMessage] = useState("")
  const [rateLimitError, setRateLimitError] = useState(null)

  const handleRegister = async (e) => {
    e.preventDefault()
    setIsPending(true)
    setMessage("")
    setRateLimitError(null)

    if (password !== confirmPassword) {
      setMessage("Passwords do not match.")
      toast({ title: "Registration Failed", description: "Passwords do not match.", variant: "destructive" })
      setIsPending(false)
      return
    }

    if (!acceptTerms) {
      setMessage("You must accept the terms and conditions.")
      toast({
        title: "Registration Failed",
        description: "You must accept the terms and conditions.",
        variant: "destructive",
      })
      setIsPending(false)
      return
    }

    const result = await register({ fullName: name, email, password, confirmPassword })

    if (result.success) {
      setMessage(result.data.message || "Registration successful! Check email to confirm your account.")
      toast({
        title: "Registration Successful",
        description: result.data.message || "Check email to confirm your account.",
        variant: "default",
      })
      // Clear form on successful registration
      setName("")
      setEmail("")
      setPassword("")
      setConfirmPassword("")
      setAcceptTerms(false)
    } else if (result.error?.isRateLimited) {
      setRateLimitError(result.error)
      toast({
        title: "Rate Limit Exceeded",
        description: result.error.message,
        variant: "destructive",
      })
    } else {
      setMessage(result.error?.message || "Registration failed. Please try again.")
      toast({
        title: "Registration Failed",
        description: result.error?.message || "Registration failed.",
        variant: "destructive",
      })
    }
    setIsPending(false)
  }

  const handleRetry = () => {
    setRateLimitError(null)
    // Optionally re-enable form fields or trigger registration attempt again
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f0f4ff] to-[#e0e8ff] py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8">
        <CardHeader className="text-center">
          <CardTitle className="text-3xl font-bold text-gray-800">Register for NCLEX Prep</CardTitle>
          <CardDescription className="text-gray-600 mt-2">
            Create your account to access comprehensive tutoring.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleRegister} className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="name">Full Name</Label>
              <Input
                id="name"
                type="text"
                name="name"
                placeholder="John Doe"
                required
                disabled={isPending}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
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
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                name="password"
                placeholder="********"
                required
                disabled={isPending}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm Password</Label>
              <Input
                id="confirmPassword"
                type="password"
                name="confirmPassword"
                placeholder="********"
                required
                disabled={isPending}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="terms"
                checked={acceptTerms}
                onCheckedChange={setAcceptTerms}
                required
                className="border-[#4F46E5]"
                disabled={isPending}
              />
              <Label htmlFor="terms" className="text-sm font-normal">
                I agree to the{" "}
                <Link href="#" className="text-[#4F46E5] hover:underline">
                  Terms and Conditions
                </Link>
              </Label>
            </div>
            <Button
              type="submit"
              className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
              disabled={isPending}
            >
              {isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Registering...
                </>
              ) : (
                "Register Account"
              )}
            </Button>
          </form>
          {message && (
            <p
              className={`mt-4 text-center text-sm ${message.includes("successful") ? "text-green-500" : "text-red-500"}`}
            >
              {message}
            </p>
          )}
          {rateLimitError && <RateLimitMessage error={rateLimitError} onRetry={handleRetry} />}
          <p className="mt-6 text-center text-sm text-gray-600">
            Already have an account?{" "}
            <Link href="/login" className="text-[#4F46E5] hover:underline">
              Sign In
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
