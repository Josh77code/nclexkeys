import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import Link from "next/link"
import { PaymentForm } from "@/components/payment-form"

export const metadata = {
  title: "Complete Payment",
  description: "Complete your payment to access your NCLEX Virtual School courses.",
}

export default function PaymentPage({ searchParams }) {
  // In a purely frontend app, we don't check user authentication or payment status here.
  // We assume the user has reached this page to make a payment.

  const message = searchParams.message || "Your account has been created. Please make a payment to access your courses."

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-[#f0f4ff] to-[#e0e8ff] py-12 px-4 sm:px-6 lg:px-8">
      <Card className="w-full max-w-md mx-auto shadow-lg rounded-lg p-8">
        <CardHeader className="text-center">
          <CardTitle className="text-3xl font-bold text-gray-800">Complete Your Registration</CardTitle>
          <CardDescription className="text-gray-600 mt-2">{message}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <PaymentForm />
          <p className="mt-6 text-center text-sm text-gray-600">
            Already paid or want to explore?{" "}
            <Link href="/dashboard" className="text-[#4F46E5] hover:underline">
              Go to Dashboard
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
