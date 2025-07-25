"use client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useState, useRef } from "react"
import { toast } from "@/hooks/use-toast"
import { Loader2 } from "lucide-react"

export function ContactUsSection() {
  const [isPending, setIsPending] = useState(false)
  const formRef = useRef(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsPending(true)

    const formData = new FormData(e.target)
    const name = formData.get("name")
    const email = formData.get("email")
    const subject = formData.get("subject")
    const message = formData.get("message")

    // Basic validation
    if (!name || !email || !subject || !message) {
      toast({ title: "Submission Failed", description: "All fields are required.", variant: "destructive" })
      setIsPending(false)
      return
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      toast({ title: "Submission Failed", description: "Please enter a valid email address.", variant: "destructive" })
      setIsPending(false)
      return
    }

    // Simulate sending message
    console.log("Contact Form Submission (Simulated):")
    console.log(`Name: ${name}`)
    console.log(`Email: ${email}`)
    console.log(`Subject: ${subject}`)
    console.log(`Message: ${message}`)

    await new Promise((resolve) => setTimeout(resolve, 1500))

    toast({ title: "Message Sent", description: "Your message has been sent successfully (simulated)!" })
    formRef.current?.reset() // Clear the form on success
    setIsPending(false)
  }

  return (
    <section id="contact-us" className="py-16 md:py-24 bg-gray-100">
      <div className="container mx-auto px-4 md:px-6 text-center">
        <h2 className="text-3xl md:text-4xl font-bold text-gray-800 mb-12 animate-fade-in-up">Get in Touch</h2>
        <div className="max-w-2xl mx-auto bg-white p-8 rounded-xl shadow-lg animate-fade-in-up">
          <p className="text-gray-600 mb-8">
            Have questions about our courses or need assistance? Fill out the form below, and we'll get back to you as
            soon as possible.
          </p>
          <form ref={formRef} onSubmit={handleSubmit} className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="space-y-2 text-left">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                name="name"
                placeholder="Your Name"
                required
                className="border-gray-300 focus:border-[#4F46E5] focus:ring-[#4F46E5]"
                disabled={isPending}
              />
            </div>
            <div className="space-y-2 text-left">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                name="email"
                placeholder="your@example.com"
                required
                className="border-gray-300 focus:border-[#4F46E5] focus:ring-[#4F46E5]"
                disabled={isPending}
              />
            </div>
            <div className="space-y-2 md:col-span-2 text-left">
              <Label htmlFor="subject">Subject</Label>
              <Input
                id="subject"
                name="subject"
                placeholder="Subject of your inquiry"
                required
                className="border-gray-300 focus:border-[#4F46E5] focus:ring-[#4F46E5]"
                disabled={isPending}
              />
            </div>
            <div className="space-y-2 md:col-span-2 text-left">
              <Label htmlFor="message">Message</Label>
              <Textarea
                id="message"
                name="message"
                placeholder="Your message..."
                rows={5}
                required
                className="border-gray-300 focus:border-[#4F46E5] focus:ring-[#4F46E5]"
                disabled={isPending}
              />
            </div>
            <div className="md:col-span-2">
              <Button type="submit" className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0]" disabled={isPending}>
                {isPending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Sending Message...
                  </>
                ) : (
                  "Send Message"
                )}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </section>
  )
}
