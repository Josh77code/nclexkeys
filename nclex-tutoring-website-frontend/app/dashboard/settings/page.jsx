import { UserProfileForm } from "@/components/user-profile-form"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"

// Mock user data for frontend-only
const mockUser = {
  id: "mock-user-id-123",
  email: "student@example.com",
  full_name: "Mock Student",
}

export const metadata = {
  title: "Account Settings",
  description: "Manage your profile and account settings for NCLEX Virtual School.",
}

export default function UserSettingsPage() {
  // In a real app, you'd fetch user data here. For frontend-only, we use mock data.
  const user = mockUser
  const profile = { full_name: mockUser.full_name } // Simulate profile data

  if (!user) {
    // In a real app, this would redirect to login. Here, we just show a message.
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-lg text-gray-600">Please log in to view settings.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-4 md:px-6">
      <div className="container mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold text-gray-800">Account Settings</h1>
          <Button
            asChild
            variant="outline"
            className="text-[#4F46E5] border-[#4F46E5] hover:bg-[#4F46E5] hover:text-white bg-transparent"
          >
            <Link href="/dashboard">
              <ArrowLeft className="h-4 w-4 mr-2" /> Back to Dashboard
            </Link>
          </Button>
        </div>
        <UserProfileForm initialFullName={profile?.full_name || ""} initialEmail={user.email} />

        <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8 mt-8">
          <CardHeader>
            <CardTitle className="text-xl font-bold text-gray-800">Change Password</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600">
              To change your password, please use the{" "}
              <Link href="/forgot-password" className="text-[#4F46E5] hover:underline">
                Forgot Password
              </Link>{" "}
              feature.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
