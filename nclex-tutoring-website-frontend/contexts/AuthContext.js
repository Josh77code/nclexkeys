"use client"

import { createContext, useContext, useEffect, useState } from "react"
import { getUserProfile, login, logout, register } from "@/lib/api" // Import functions from your new api.js

const AuthContext = createContext(undefined)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadUser = async () => {
      const token = localStorage.getItem("access_token")
      if (token) {
        const result = await getUserProfile()
        if (result.success) {
          setUser(result.data)
        } else {
          // If token is invalid or expired, clear it
          localStorage.removeItem("access_token")
          localStorage.removeItem("refresh_token")
          setUser(null)
        }
      }
      setLoading(false)
    }
    loadUser()
  }, [])

  const value = {
    user,
    setUser,
    loading,
    login,
    logout,
    register,
    // You can expose other auth functions here if needed in the context
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
