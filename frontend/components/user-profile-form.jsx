"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "@/hooks/use-toast"
import { Loader2 } from "lucide-react"
import { updateProfile } from "@/lib/api" // Import the new updateProfile function
import { useAuth } from "@/contexts/AuthContext" // Import useAuth

export function UserProfileForm({ initialFullName, initialEmail }) {
  const { setUser } = useAuth() // Get setUser from AuthContext
  const [fullName, setFullName] = useState(initialFullName || "")
  const [isPending, setIsPending] = useState(false)

  const handleUpdateProfile = async (e) => {
    e.preventDefault()
    setIsPending(true)

    const result = await updateProfile({ full_name: fullName })

    if (result.success) {
      toast({ title: "Profile Updated", description: result.data.message || "Profile updated successfully!" })
      setUser(result.data) // Update user in context with new data from backend
    } else {
      toast({
        title: "Update Failed",
        description: result.error?.message || "Failed to update profile.",
        variant: "destructive",
      })
    }
    setIsPending(false)
  }

  return (
    <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8">
      <CardHeader className="text-center">
        <CardTitle className="text-3xl font-bold text-gray-800">Edit Profile</CardTitle>
        <CardDescription className="text-gray-600 mt-2">Update your personal information.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleUpdateProfile} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="fullName">Full Name</Label>
            <Input
              id="fullName"
              name="fullName"
              type="text"
              placeholder="Your Full Name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              disabled={isPending}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email Address</Label>
            <Input
              id="email"
              type="email"
              placeholder="Your Email"
              value={initialEmail}
              disabled // Email is typically not editable directly via profile form
            />
            <p className="text-xs text-gray-500">Email cannot be changed here. Contact support for email changes.</p>
          </div>
          <Button
            type="submit"
            className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
            disabled={isPending}
          >
            {isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Saving...
              </>
            ) : (
              "Save Changes"
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
