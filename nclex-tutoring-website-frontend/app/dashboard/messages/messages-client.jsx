"use client"

import { ChatInterface } from "@/components/messaging/chat-interface"
import { ConversationList } from "@/components/messaging/conversation-list"
import { Button } from "@/components/ui/button"
import Link from "next/link"
import { ArrowLeft } from "lucide-react"
import { useState } from "react"
import { useAuth } from "@/contexts/AuthContext" // Import useAuth

export function MessagesClientWrapper() {
  const { user, loading } = useAuth() // Use user and loading from AuthContext
  const [selectedOtherUser, setSelectedOtherUser] = useState(null)

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-lg text-gray-600">Loading messages interface...</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-lg text-red-600">Authentication required to access messages. Please log in.</p>
        <Button asChild className="ml-4">
          <Link href="/login">Go to Login</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-100 py-12 px-4 md:px-6">
      <div className="container mx-auto h-[calc(100vh-100px)] flex flex-col">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-3xl font-bold text-gray-800">Messages</h1>
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

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 flex-1">
          <div className="md:col-span-1">
            <ConversationList currentUserId={user.id} onSelectConversation={setSelectedOtherUser} />
          </div>
          <div className="md:col-span-2">
            <ChatInterface currentUserId={user.id} otherUser={selectedOtherUser} />
          </div>
        </div>
      </div>
    </div>
  )
}
