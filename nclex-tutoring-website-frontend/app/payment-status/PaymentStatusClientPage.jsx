"use client"

import { useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import Link from "next/link"
import { CheckCircle, XCircle, Info, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "@/hooks/use-toast"
import { apiRequest } from "@/lib/api" // Import apiRequest

export default function PaymentStatusClientPage() {
  const searchParams = useSearchParams()
  const status = searchParams.get("status")
  const message = searchParams.get("message")
  const transactionId = searchParams.get("transaction_id")
  const [enrollmentStatus, setEnrollmentStatus] = useState("idle") // idle, checking, enrolling, enrolled, error
  const [enrollmentMessage, setEnrollmentMessage] = useState("")

  let title = ""
  let description = ""
  let icon = null
  let iconColor = ""

  if (status === "success") {
    title = "Payment Successful!"
    description = "Your payment has been processed successfully."
    icon = <CheckCircle className="h-16 w-16 text-green-500" />
    iconColor = "text-green-500"
  } else if (status === "failed") {
    title = "Payment Failed"
    description = message || "Your payment could not be processed. Please try again."
    icon = <XCircle className="h-16 w-16 text-red-500" />
    iconColor = "text-red-500"
  } else {
    title = "Payment Status"
    description = message || "Checking your payment status..."
    icon = <Info className="h-16 w-16 text-blue-500" />
    iconColor = "text-blue-500"
  }

  useEffect(() => {
    const handleEnrollment = async () => {
      if (status === "success" && transactionId && enrollmentStatus === "idle") {
        setEnrollmentStatus("checking")
        setEnrollmentMessage("Verifying payment and enrolling you in courses...")

        try {
          const response = await apiRequest(`/api/payments/status/${transactionId}/`, {
            method: "GET",
          })

          const data = await response.json()

          if (response.ok && data.status === "success" && data.enrollment_status === "enrolled") {
            setEnrollmentStatus("enrolled")
            setEnrollmentMessage(data.message || "You have been successfully enrolled in all available courses!")
            toast({ title: "Enrollment Complete", description: "You are now enrolled in your courses." })
          } else {
            setEnrollmentStatus("error")
            setEnrollmentMessage(data.message || "Failed to enroll you in courses. Please contact support.")
            toast({
              title: "Enrollment Failed",
              description: data.message || "Please contact support.",
              variant: "destructive",
            })
          }
        } catch (error) {
          console.error("Payment status/enrollment API call failed:", error)
          setEnrollmentStatus("error")
          setEnrollmentMessage("Network error during enrollment. Please contact support.")
          toast({
            title: "Enrollment Error",
            description: "Network issue. Please contact support.",
            variant: "destructive",
          })
        }
      }
    }
    handleEnrollment()
  }, [status, transactionId, enrollmentStatus])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f0f4ff] to-[#e0e8ff] py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8 text-center">
        <CardHeader className="flex flex-col items-center">
          <div className={`mb-4 ${iconColor}`}>{icon}</div>
          <CardTitle className={`text-3xl font-bold ${iconColor}`}>{title}</CardTitle>
          <CardDescription className="text-gray-600 mt-2">{description}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {status === "success" && (
            <div className="mt-4 text-center">
              {(enrollmentStatus === "checking" || enrollmentStatus === "enrolling") && (
                <p className="text-blue-600 flex items-center justify-center gap-2">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" /> {enrollmentMessage}
                </p>
              )}
              {enrollmentStatus === "enrolled" && (
                <p className="text-green-600 flex items-center justify-center gap-2">
                  <CheckCircle className="mr-2 h-5 w-5" /> {enrollmentMessage}
                </p>
              )}
              {enrollmentStatus === "error" && (
                <p className="text-red-600 flex items-center justify-center gap-2">
                  <XCircle className="mr-2 h-5 w-5" /> {enrollmentMessage}
                </p>
              )}
            </div>
          )}
          <Button
            asChild
            className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
          >
            <Link href="/dashboard">Go to Dashboard</Link>
          </Button>
          {status !== "success" && (
            <Button
              asChild
              variant="outline"
              className="w-full text-[#4F46E5] border-[#4F46E5] hover:bg-[#4F46E5] hover:text-white bg-transparent"
            >
              <Link href="/register">Try Payment Again</Link>
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
