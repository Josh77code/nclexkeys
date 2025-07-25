"use client"

import { useState, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Loader2, Send } from "lucide-react"
import { toast } from "@/hooks/use-toast"
import { apiRequest } from "@/lib/api" // Import apiRequest

export function ChatInterface({ currentUserId, otherUser }) {
  const [messages, setMessages] = useState([])
  const [newMessageContent, setNewMessageContent] = useState("")
  const [isLoadingMessages, setIsLoadingMessages] = useState(true)
  const [isSending, setIsSending] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    const fetchMessages = async () => {
      setIsLoadingMessages(true)
      if (!currentUserId || !otherUser?.id) {
        setMessages([])
        setIsLoadingMessages(false)
        return
      }

      try {
        const response = await apiRequest(`/api/messages/conversation/${otherUser.id}/`, {
          method: "GET",
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "Failed to fetch messages.")
        setMessages(data)
      } catch (error) {
        console.error("Failed to fetch messages:", error)
        toast({ title: "Error", description: "Could not load messages for this conversation.", variant: "destructive" })
        setMessages([])
      } finally {
        setIsLoadingMessages(false)
      }
    }

    fetchMessages()
  }, [currentUserId, otherUser?.id])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  const handleSendMessage = async (e) => {
    e.preventDefault()
    if (!newMessageContent.trim() || !currentUserId || !otherUser?.id) return

    setIsSending(true)

    try {
      const response = await apiRequest("/api/messages/send/", {
        method: "POST",
        body: JSON.stringify({
          receiver_id: otherUser.id,
          content: newMessageContent,
        }),
      })

      const data = await response.json()

      if (response.ok) {
        setMessages((prevMessages) => [...prevMessages, data])
        setNewMessageContent("")
        toast({ title: "Message Sent", description: "Message sent successfully!" })
      } else {
        toast({ title: "Send Failed", description: data.detail || "Failed to send message.", variant: "destructive" })
      }
    } catch (error) {
      console.error("Send message API call failed:", error)
      toast({ title: "Error", description: "Network error during message send.", variant: "destructive" })
    } finally {
      setIsSending(false)
    }
  }

  if (!otherUser) {
    return (
      <Card className="flex flex-col h-full">
        <CardHeader>
          <CardTitle>Select a Conversation</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 flex items-center justify-center text-gray-500">
          Please select a user from the left to start chatting.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="flex flex-col h-full">
      <CardHeader className="flex flex-row items-center gap-4 border-b p-4">
        <Avatar className="h-10 w-10">
          <AvatarImage src="https://images.unsplash.com/photo-153571387500-fd428796c875?q=80&w=1964&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D" />
          <AvatarFallback>
            {otherUser.full_name ? otherUser.full_name.charAt(0) : otherUser.email.charAt(0)}
          </AvatarFallback>
        </Avatar>
        <div>
          <CardTitle className="text-lg">{otherUser.full_name || otherUser.email}</CardTitle>
          <p className="text-sm text-gray-500">{otherUser.email}</p>
        </div>
      </CardHeader>
      <CardContent className="flex-1 p-4 overflow-hidden">
        <ScrollArea className="h-full pr-4">
          {isLoadingMessages ? (
            <div className="flex items-center justify-center h-full text-gray-500">
              <Loader2 className="h-6 w-6 animate-spin mr-2" /> Loading messages...
            </div>
          ) : messages.length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-500">
              No messages yet. Start the conversation!
            </div>
          ) : (
            messages.map((msg, index) => (
              <div
                key={msg.id || index}
                className={`flex items-end gap-2 mb-4 ${msg.sender_id === currentUserId ? "justify-end" : "justify-start"}`}
              >
                {msg.sender_id !== currentUserId && (
                  <Avatar className="h-8 w-8">
                    <AvatarImage src="https://images.unsplash.com/photo-153571387500-fd428796c875?q=80&w=1964&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D" />
                    <AvatarFallback>
                      {otherUser.full_name ? otherUser.full_name.charAt(0) : otherUser.email.charAt(0)}
                    </AvatarFallback>
                  </Avatar>
                )}
                <div
                  className={`max-w-[70%] p-3 rounded-lg ${
                    msg.sender_id === currentUserId
                      ? "bg-[#4F46E5] text-white rounded-br-none"
                      : "bg-gray-200 text-gray-800 rounded-bl-none"
                  }`}
                >
                  <p className="text-sm">{msg.content}</p>
                  <p className={`text-xs mt-1 ${msg.sender_id === currentUserId ? "text-gray-200" : "text-gray-500"}`}>
                    {new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </p>
                </div>
                {msg.sender_id === currentUserId && (
                  <Avatar className="h-8 w-8">
                    <AvatarImage src="https://images.unsplash.com/photo-153571387500-fd428796c875?q=80&w=1964&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D" />
                    <AvatarFallback>You</AvatarFallback>
                  </Avatar>
                )}
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </ScrollArea>
      </CardContent>
      <CardFooter className="border-t p-4">
        <form onSubmit={handleSendMessage} className="flex w-full gap-2">
          <Input
            placeholder="Type your message..."
            value={newMessageContent}
            onChange={(e) => setNewMessageContent(e.target.value)}
            className="flex-1"
            disabled={isSending}
          />
          <Button type="submit" disabled={isSending}>
            {isSending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            <span className="sr-only">Send message</span>
          </Button>
        </form>
      </CardFooter>
    </Card>
  )
}
