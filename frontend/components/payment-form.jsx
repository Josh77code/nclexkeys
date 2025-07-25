"use client"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { toast } from "@/hooks/use-toast"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { Loader2 } from "lucide-react"
import { apiRequest } from "@/lib/api" // Import apiRequest

export function PaymentForm() {
  const router = useRouter()
  const [isProcessing, setIsProcessing] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setIsProcessing(true)

    const paymentMethod = e.target.paymentMethod.value
    const cardNumber = e.target.cardNumber.value
    const expiryDate = e.target.expiryDate.value
    const cvv = e.target.cvv.value

    try {
      const response = await apiRequest("/api/payments/initiate/", {
        method: "POST",
        body: JSON.stringify({
          payment_method: paymentMethod,
          card_details: { cardNumber, expiryDate, cvv },
          amount: 60, // Example amount, should be dynamic based on selected course/plan
          currency: "USD", // Example currency
        }),
      })

      const data = await response.json()

      if (response.ok) {
        toast({
          title: "Payment Initiated",
          description: data.message || "Redirecting to payment status page...",
        })
        router.push(`/payment-status?status=success&transaction_id=${data.transaction_id}`)
      } else {
        toast({
          title: "Payment Failed",
          description: data.detail || "Invalid payment details. Please check your card information.",
          variant: "destructive",
        })
        router.push(`/payment-status?status=failed&message=${encodeURIComponent(data.detail || "Payment failed.")}`)
      }
    } catch (error) {
      console.error("Payment initiation API call failed:", error)
      toast({
        title: "Error",
        description: "Network error or server issue during payment initiation.",
        variant: "destructive",
      })
      router.push(`/payment-status?status=failed&message=${encodeURIComponent("Network error during payment.")}`)
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="paymentMethod">Payment Method</Label>
        <Select name="paymentMethod" required disabled={isProcessing}>
          <SelectTrigger id="paymentMethod">
            <SelectValue placeholder="Select a payment method" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="credit_card">Credit Card</SelectItem>
            <SelectItem value="paystack">Paystack</SelectItem>
            <SelectItem value="flutterwave">Flutterwave</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-2">
        <Label htmlFor="cardNumber">Card Number</Label>
        <Input
          id="cardNumber"
          name="cardNumber"
          type="text"
          placeholder="**** **** **** ****"
          maxLength={16}
          required
          disabled={isProcessing}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="expiryDate">Expiry Date</Label>
          <Input
            id="expiryDate"
            name="expiryDate"
            type="text"
            placeholder="MM/YY"
            maxLength={5}
            required
            disabled={isProcessing}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="cvv">CVV</Label>
          <Input id="cvv" name="cvv" type="text" placeholder="***" maxLength={3} required disabled={isProcessing} />
        </div>
      </div>
      <Button
        type="submit"
        className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors py-2.5 text-base"
        disabled={isProcessing}
      >
        {isProcessing ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processing Payment...
          </>
        ) : (
          "Pay Now"
        )}
      </Button>
    </form>
  )
}
