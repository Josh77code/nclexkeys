"use client"

import { Button } from "@/components/ui/button"
import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Input } from "@/components/ui/input"
import { Search, Loader2 } from "lucide-react"
import { toast } from "@/hooks/use-toast"
import { apiRequest } from "@/lib/api" // Import apiRequest

export function ConversationList({ currentUserId, onSelectConversation }) {
  const [users, setUsers] = useState([])
  const [searchTerm, setSearchTerm] = useState("")
  const [isLoadingUsers, setIsLoadingUsers] = useState(true)

  useEffect(() => {
    const fetchConversations = async () => {
      setIsLoadingUsers(true)
      if (!currentUserId) {
        setUsers([])
        setIsLoadingUsers(false)
        return
      }

      try {
        const response = await apiRequest("/api/messages/conversations/", {
          method: "GET",
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "Failed to fetch conversations.")
        // Filter out the current user from the list if they appear in the conversation list
        const filteredData = data.filter((user) => user.user_id !== currentUserId)
        setUsers(filteredData)
      } catch (error) {
        console.error("Failed to fetch conversations:", error)
        toast({ title: "Error", description: "Could not load conversations.", variant: "destructive" })
        setUsers([])
      } finally {
        setIsLoadingUsers(false)
      }
    }

    fetchConversations()
  }, [currentUserId])

  const filteredUsers = users.filter(
    (user) =>
      user.full_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      user.email.toLowerCase().includes(searchTerm.toLowerCase()),
  )

  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="border-b p-4">
        <CardTitle className="text-lg">Conversations</CardTitle>
        <div className="relative mt-4">
          <Input
            placeholder="Search users..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
        </div>
      </CardHeader>
      <CardContent className="flex-1 p-0 overflow-hidden">
        <ScrollArea className="h-full">
          {isLoadingUsers ? (
            <div className="flex items-center justify-center h-full text-gray-500 py-4">
              <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading users...
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="text-center text-gray-500 py-4">No users found.</div>
          ) : (
            filteredUsers.map((user) => (
              <Button
                key={user.user_id}
                variant="ghost"
                className="w-full justify-start p-4 h-auto rounded-none border-b last:border-b-0"
                onClick={() => onSelectConversation(user)}
              >
                <Avatar className="h-10 w-10 mr-3">
                  <AvatarImage src="https://images.unsplash.com/photo-153571387500-fd428796c875?q=80&w=1964&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D" />
                  <AvatarFallback>{user.full_name ? user.full_name.charAt(0) : user.email.charAt(0)}</AvatarFallback>
                </Avatar>
                <div className="flex flex-col items-start">
                  <span className="font-medium text-gray-800">{user.full_name || "Unknown User"}</span>
                  <span className="text-sm text-gray-500">{user.email}</span>
                </div>
              </Button>
            ))
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  )
}
