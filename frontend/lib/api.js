"use client"

import { toast } from "@/hooks/use-toast"

// --- Helper for API Error Handling ---
export const handleApiError = async (response) => {
  if (response.status === 429) {
    const data = await response.json()
    return {
      isRateLimited: true,
      message: data.detail,
      retryAfter: data.retry_after,
      retryAfterHuman: data.retry_after_human,
    }
  }
  // Handle 423 Locked accounts specifically
  if (response.status === 423) {
    const data = await response.json()
    return {
      isLocked: true,
      message: data.detail,
    }
  }

  // Handle other errors
  const data = await response.json()
  return {
    isRateLimited: false,
    isLocked: false,
    message: data.detail || "An unexpected error occurred.",
    errors: data.errors || {}, // For validation errors
  }
}

// --- Token Refresh Function ---
export const refreshToken = async () => {
  const refresh_token = localStorage.getItem("refresh_token")

  if (!refresh_token) {
    console.warn("No refresh token found. Redirecting to login.")
    window.location.href = "/login"
    return null
  }

  try {
    const response = await fetch("http://127.0.0.1:8000/api/auth/refresh/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token }),
    })

    if (response.ok) {
      const data = await response.json()
      localStorage.setItem("access_token", data.access_token)
      localStorage.setItem("refresh_token", data.refresh_token) // Refresh token might also rotate
      return data.access_token
    } else {
      const error = await handleApiError(response)
      console.error("Token refresh failed:", error)
      toast({
        title: "Session Expired",
        description: error.message || "Please log in again.",
        variant: "destructive",
      })
      window.location.href = "/login" // Redirect to login if refresh fails
      return null
    }
  } catch (error) {
    console.error("Network error during token refresh:", error)
    toast({
      title: "Network Error",
      description: "Could not refresh session. Please check your connection.",
      variant: "destructive",
    })
    window.location.href = "/login"
    return null
  }
}

// --- API Request Helper for Authenticated Calls ---
export const apiRequest = async (url, options = {}) => {
  const token = localStorage.getItem("access_token")

  const makeRequest = async (currentAccessToken) => {
    return fetch(url, {
      ...options,
      headers: {
        Authorization: `Bearer ${currentAccessToken}`,
        "Content-Type": options.body instanceof FormData ? undefined : "application/json", // Set Content-Type unless FormData
        ...options.headers,
      },
    })
  }

  let response = await makeRequest(token)

  // Auto-refresh token if 401 Unauthorized
  if (response.status === 401) {
    const newToken = await refreshToken()
    if (newToken) {
      response = await makeRequest(newToken) // Retry request with new token
    } else {
      // If token refresh failed, the refreshToken function already redirected to login
      return new Response(JSON.stringify({ detail: "Authentication failed, please log in." }), { status: 401 })
    }
  }

  return response
}

// --- Core Authentication Functions ---

export const register = async (userData) => {
  const response = await fetch("http://127.0.0.1:8000/api/auth/register/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: userData.email,
      full_name: userData.fullName,
      password: userData.password,
      confirm_password: userData.confirmPassword,
    }),
  })

  if (response.ok) {
    return { success: true, data: await response.json() }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const verifyEmail = async (token) => {
  const response = await fetch("http://127.0.0.1:8000/api/auth/verify-email/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  })

  if (response.ok) {
    return { success: true }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const login = async (credentials) => {
  const response = await fetch("http://127.0.0.1:8000/api/auth/login/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: credentials.email,
      password: credentials.password,
      two_factor_token: credentials.twoFactorToken,
      backup_code: credentials.backupCode,
    }),
  })

  if (response.ok) {
    const data = await response.json()
    localStorage.setItem("access_token", data.access_token)
    localStorage.setItem("refresh_token", data.refresh_token)
    return { success: true, data }
  }

  // Handle 2FA requirement
  if (response.status === 400) {
    const error = await response.json()
    if (error.requires_2fa) {
      return { success: false, requires2FA: true }
    }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const logout = async () => {
  const refresh_token = localStorage.getItem("refresh_token")
  if (refresh_token) {
    try {
      await apiRequest("http://127.0.0.1:8000/api/auth/logout/", {
        method: "POST",
        body: JSON.stringify({ refresh_token }),
      })
    } catch (error) {
      console.error("Logout API call failed:", error)
      // Continue to clear tokens even if API call fails
    }
  }
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
  window.location.href = "/" // Redirect to home or login
}

export const logoutAll = async () => {
  try {
    await apiRequest("http://127.0.0.1:8000/api/auth/logout-all/", {
      method: "POST",
    })
  } catch (error) {
    console.error("Logout All API call failed:", error)
  } finally {
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    window.location.href = "/login"
  }
}

// --- Password Management ---

export const forgotPassword = async (email) => {
  const response = await fetch("http://127.0.0.1:8000/api/auth/forgot-password/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  })

  if (response.ok) {
    return { success: true }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const resetPassword = async (token, newPassword) => {
  const response = await fetch("http://127.0.0.1:8000/api/auth/reset-password/confirm/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      token,
      new_password: newPassword,
      confirm_new_password: newPassword,
    }),
  })

  if (response.ok) {
    return { success: true }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const changePassword = async (passwordData) => {
  const response = await apiRequest("http://127.0.0.1:8000/api/auth/change-password/", {
    method: "POST",
    body: JSON.stringify({
      current_password: passwordData.currentPassword,
      new_password: passwordData.newPassword,
      confirm_new_password: passwordData.confirmNewPassword,
    }),
  })

  if (response.ok) {
    return { success: true }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

// --- Two-Factor Authentication (2FA) ---

export const enable2FA = async () => {
  const response = await apiRequest("http://127.0.0.1:8000/api/auth/2fa/enable/", {
    method: "POST",
  })

  if (response.ok) {
    const data = await response.json()
    return {
      success: true,
      qrCode: data.qr_code,
      secret: data.secret,
      instructions: data.instructions,
    }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const confirm2FA = async (token) => {
  const response = await apiRequest("/api/auth/2fa/confirm/", {
    method: "POST",
    body: JSON.stringify({ token }),
  })

  if (response.ok) {
    return { success: true }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const disable2FA = async (password, token) => {
  const response = await apiRequest("http://127.0.0.1:8000/api/auth/2fa/disable/", {
    method: "POST",
    body: JSON.stringify({ password, token }),
  })

  if (response.ok) {
    return { success: true }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const generateBackupCodes = async () => {
  const response = await apiRequest("http://127.0.0.1:8000/api/auth/2fa/backup-codes/", {
    method: "POST",
  })

  if (response.ok) {
    const data = await response.json()
    return {
      success: true,
      backupCodes: data.backup_codes,
      message: data.message,
    }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const get2FAStatus = async () => {
  const response = await apiRequest("http://127.0.0.1:8000/api/auth/2fa/status/")

  if (response.ok) {
    return { success: true, data: await response.json() }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const emergencyDisable2FA = async (email, password) => {
  const response = await fetch("http://127.0.0.1:8000/api/auth/2fa/emergency-disable/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  })

  if (response.ok) {
    return { success: true, data: await response.json() }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

// --- User Profile Management ---

export const getUserProfile = async () => {
  const response = await apiRequest("http://127.0.0.1:8000/api/users/me/")

  if (response.ok) {
    return { success: true, data: await response.json() }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const updateProfile = async (profileData) => {
  const response = await apiRequest("http://127.0.0.1:8000/api/me/update/", {
    method: "PUT", // Or PATCH, depending on your API
    body: JSON.stringify(profileData),
  })

  if (response.ok) {
    return { success: true, data: await response.json() }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const getAccountStatus = async () => {
  const response = await apiRequest("/api/auth/account-status/")

  if (response.ok) {
    return { success: true, data: await response.json() }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

// --- Account Management ---

export const deleteAccount = async (password) => {
  const response = await apiRequest("http://127.0.0.1:8000/api/auth/delete-account/", {
    method: "POST",
    body: JSON.stringify({
      password,
      confirm_deletion: true,
    }),
  })

  if (response.ok) {
    const data = await response.json()
    return { success: true, deletionScheduledFor: data.deletion_scheduled_for }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const cancelDeletion = async (password) => {
  const response = await apiRequest("http://127.0.0.1:8000/api/auth/cancel-deletion/", {
    method: "POST",
    body: JSON.stringify({ password }),
  })

  if (response.ok) {
    return { success: true }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}

export const deleteAccountImmediate = async (password) => {
  const response = await apiRequest("http://127.0.0.1:8000/api/auth/delete-account-immediate/", {
    method: "POST",
    body: JSON.stringify({
      password,
      confirm_deletion: true,
    }),
  })

  if (response.ok) {
    localStorage.removeItem("access_token")
    localStorage.removeItem("refresh_token")
    window.location.href = "/goodbye" // Or appropriate redirect
    return { success: true }
  }

  const error = await handleApiError(response)
  return { success: false, error }
}
