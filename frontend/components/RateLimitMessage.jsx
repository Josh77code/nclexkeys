"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button" // Assuming you have a Button component

const RateLimitMessage = ({ error, onRetry }) => {
  const [timeLeft, setTimeLeft] = useState(error.retryAfter)

  useEffect(() => {
    if (timeLeft <= 0) return

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer)
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [timeLeft])

  const formatTime = (seconds) => {
    if (seconds < 60) return `${seconds}s`
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}m ${remainingSeconds}s`
  }

  return (
    <div className="bg-red-50 border border-red-200 rounded-md p-4 mt-4">
      <div className="flex">
        <div className="ml-3">
          <h3 className="text-sm font-medium text-red-800">Rate Limit Exceeded</h3>
          <div className="mt-2 text-sm text-red-700">
            <p>{error.message}</p>
            {timeLeft > 0 ? (
              <p className="mt-1">
                Try again in: <span className="font-mono">{formatTime(timeLeft)}</span>
              </p>
            ) : (
              <Button
                onClick={onRetry}
                className="mt-2 bg-red-600 text-white px-3 py-1 rounded text-sm hover:bg-red-700"
              >
                Try Again
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default RateLimitMessage
