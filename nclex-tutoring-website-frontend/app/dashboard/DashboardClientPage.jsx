"use client"

import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { PlayCircle, BookOpen, TrendingUp, Settings, LogOut, MessageSquare, ClipboardCheck } from "lucide-react"
import { useState, useEffect } from "react"
import { toast } from "@/hooks/use-toast"
import { useAuth } from "@/contexts/AuthContext" // Import useAuth
import { apiRequest, logout } from "@/lib/api" // Import apiRequest and logout

export default function DashboardClientPage() {
  const { user, loading: loadingAuth } = useAuth() // Use user and loading from AuthContext
  const [courses, setCourses] = useState([])
  const [userProgress, setUserProgress] = useState([])
  const [loadingData, setLoadingData] = useState(true) // Separate loading for data fetch

  useEffect(() => {
    const fetchDashboardData = async () => {
      if (loadingAuth) return // Wait for AuthContext to load

      if (user) {
        setLoadingData(true)
        try {
          // Fetch all available courses
          const coursesResponse = await apiRequest("/api/courses/", { method: "GET" })
          const coursesData = await coursesResponse.json()
          if (!coursesResponse.ok) throw new Error(coursesData.detail || "Failed to fetch courses.")
          setCourses(coursesData)

          // Fetch user's specific progress for courses
          const progressResponse = await apiRequest("/api/users/me/progress/", { method: "GET" })
          const progressData = await progressResponse.json()
          if (!progressResponse.ok) throw new Error(progressData.detail || "Failed to fetch user progress.")
          setUserProgress(progressData)
        } catch (error) {
          console.error("Failed to fetch dashboard data:", error)
          toast({
            title: "Error",
            description: `Failed to load dashboard data: ${error.message}`,
            variant: "destructive",
          })
        } finally {
          setLoadingData(false)
        }
      } else if (!user && !loadingAuth) {
        // Not logged in, and AuthContext has finished loading
        toast({
          title: "Authentication Required",
          description: "Please log in to access your dashboard.",
          variant: "destructive",
        })
        // router.push('/login'); // Consider redirecting here
      }
    }

    fetchDashboardData()
  }, [user, loadingAuth]) // Depend on user and loadingAuth from context

  const completedCoursesCount = userProgress.filter((p) => p.progress_percentage === 100).length
  const totalCourses = courses.length
  const overallProgress = totalCourses > 0 ? Math.round((completedCoursesCount / totalCourses) * 100) : 0

  const handleSignOut = () => {
    logout() // Use the logout function from lib/api
  }

  if (loadingAuth || loadingData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-lg text-gray-600">Loading your dashboard...</p>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-lg text-red-600">Authentication required. Please log in.</p>
        <Button asChild className="ml-4">
          <Link href="/login">Go to Login</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white shadow-sm py-4 px-6 flex items-center justify-between border-b">
        <h1 className="text-2xl font-bold text-gray-800">Welcome, {user.full_name || user.email}!</h1>
        <div className="flex items-center gap-4">
          <Button asChild variant="ghost" className="text-gray-600 hover:text-[#4F46E5]">
            <Link href="/dashboard/settings">
              <Settings className="h-5 w-5 mr-2" /> Settings
            </Link>
          </Button>
          <Button onClick={handleSignOut} className="bg-[#4F46E5] text-white hover:bg-[#3b34b0]">
            <LogOut className="h-5 w-5 mr-2" /> Logout
          </Button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8 grid grid-cols-1 lg:grid-cols-4 gap-8">
        <div className="lg:col-span-1 space-y-6">
          <Card className="p-6 shadow-md">
            <CardTitle className="text-xl font-semibold mb-4">My Progress</CardTitle>
            <CardContent className="p-0 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-gray-700">Courses Completed:</span>
                <span className="font-bold text-[#4F46E5]">
                  {completedCoursesCount}/{totalCourses}
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div className="bg-[#4F46E5] h-2.5 rounded-full" style={{ width: `${overallProgress}%` }}></div>
              </div>
              <div className="flex items-center justify-between mt-4">
                <span className="text-gray-700">Practice Questions:</span>
                <span className="font-bold text-[#4F46E5]">N/A</span>
              </div>
              <Button
                asChild
                variant="outline"
                className="w-full mt-6 text-[#4F46E5] border-[#4F46E5] hover:bg-[#4F46E5] hover:text-white bg-transparent"
              >
                <Link href="/dashboard/progress">View Detailed Progress</Link>
              </Button>
            </CardContent>
          </Card>

          <Card className="p-6 shadow-md">
            <CardTitle className="text-xl font-semibold mb-4">Quick Links</CardTitle>
            <CardContent className="p-0 space-y-3">
              <Link href="#" className="flex items-center gap-3 text-gray-700 hover:text-[#4F46E5] transition-colors">
                <BookOpen className="h-5 w-5" /> My Courses
              </Link>
              <Link href="#" className="flex items-center gap-3 text-gray-700 hover:text-[#4F46E5] transition-colors">
                <TrendingUp className="h-5 w-5" /> Performance Analytics
              </Link>
              <Button
                asChild
                variant="ghost"
                className="w-full justify-start text-gray-700 hover:text-[#4F46E5] transition-colors p-0 h-auto"
              >
                <Link href="/dashboard/messages" className="flex items-center gap-3">
                  <MessageSquare className="h-5 w-5" /> Messages
                </Link>
              </Button>
              <Button
                asChild
                variant="ghost"
                className="w-full justify-start text-gray-700 hover:text-[#4F46E5] transition-colors p-0 h-auto"
              >
                <Link href="/dashboard/exam" className="flex items-center gap-3">
                  <ClipboardCheck className="h-5 w-5" /> Exam Integration
                </Link>
              </Button>
              <Button
                asChild
                variant="ghost"
                className="w-full justify-start text-gray-700 hover:text-[#4F46E5] transition-colors p-0 h-auto"
              >
                <Link href="/dashboard/settings" className="flex items-center gap-3">
                  <Settings className="h-5 w-5" /> Account Settings
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-3 space-y-6">
          <h2 className="text-2xl font-bold text-gray-800 mb-4">My Video Courses</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
            {courses.map((course) => (
              <Card key={course.id} className="shadow-md hover:shadow-lg transition-shadow duration-200">
                <CardHeader>
                  <CardTitle className="text-lg font-semibold">{course.title}</CardTitle>
                  <CardDescription className="text-gray-600 text-sm">{course.description}</CardDescription>
                </CardHeader>
                <CardContent className="flex justify-end">
                  <Button asChild className="bg-[#4F46E5] text-white hover:bg-[#3b34b0]">
                    <a href={course.video_url} target="_blank" rel="noopener noreferrer">
                      <PlayCircle className="h-5 w-5 mr-2" /> Watch Video
                    </a>
                  </Button>
                </CardContent>
              </Card>
            ))}
            {courses.length === 0 && (
              <p className="text-gray-600 col-span-full text-center">No courses available yet.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
