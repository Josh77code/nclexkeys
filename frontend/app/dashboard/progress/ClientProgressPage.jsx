"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { toast } from "@/hooks/use-toast"
import { CheckCircle, Circle, Loader2, PlayCircle, Search } from "lucide-react"
import Link from "next/link"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Input } from "@/components/ui/input"
import { useAuth } from "@/contexts/AuthContext" // Import useAuth
import { apiRequest } from "@/lib/api" // Import apiRequest

export default function ClientProgressPage() {
  const { user, loading: loadingAuth } = useAuth() // Use user and loading from AuthContext
  const [courses, setCourses] = useState([])
  const [userProgress, setUserProgress] = useState([])
  const [loadingData, setLoadingData] = useState(true) // Separate loading for data fetch
  const [filterStatus, setFilterStatus] = useState("all")
  const [searchTerm, setSearchTerm] = useState("")
  const [isUpdating, setIsUpdating] = useState(false)

  useEffect(() => {
    const fetchUserDataAndCourses = async () => {
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
          toast({ title: "Error", description: `Failed to load data: ${error.message}`, variant: "destructive" })
        } finally {
          setLoadingData(false)
        }
      } else if (!user && !loadingAuth) {
        // Not logged in, and AuthContext has finished loading
        toast({
          title: "Authentication Required",
          description: "Please log in to access your progress.",
          variant: "destructive",
        })
        // router.push('/login'); // Consider redirecting here
      }
    }

    fetchUserDataAndCourses()
  }, [user, loadingAuth]) // Depend on user and loadingAuth from context

  const getCourseProgress = (courseId) => {
    const progress = userProgress.find((p) => p.course_id === courseId)
    return progress ? progress.progress_percentage : 0
  }

  const getCompletedAt = (courseId) => {
    const progress = userProgress.find((p) => p.course_id === courseId)
    return progress?.completed_at ? new Date(progress.completed_at).toLocaleDateString() : null
  }

  const handleMarkComplete = async (courseId, currentProgress) => {
    setIsUpdating(true)

    const newProgressValue = currentProgress === 100 ? 0 : 100
    // The backend should handle setting/clearing completed_at based on progress_percentage
    // We send only progress_percentage

    try {
      const response = await apiRequest(`/api/users/me/progress/${courseId}/`, {
        method: "PUT", // Or PATCH
        body: JSON.stringify({ progress_percentage: newProgressValue }),
      })

      const data = await response.json()

      if (response.ok) {
        // Update local state with the response from the backend
        setUserProgress((prevProgress) => {
          const existingIndex = prevProgress.findIndex((p) => p.course_id === courseId && p.user_id === user.id)
          if (existingIndex > -1) {
            const updatedProgress = [...prevProgress]
            updatedProgress[existingIndex] = {
              ...updatedProgress[existingIndex],
              progress_percentage: data.progress_percentage,
              completed_at: data.completed_at,
            }
            return updatedProgress
          } else {
            // If no existing progress, add a new entry (should ideally be handled by backend on first interaction)
            return [...prevProgress, data]
          }
        })
        toast({ title: "Progress Updated", description: "Course progress updated successfully!" })
      } else {
        toast({
          title: "Update Failed",
          description: data.detail || "Failed to update course progress.",
          variant: "destructive",
        })
      }
    } catch (error) {
      console.error("Update progress API call failed:", error)
      toast({ title: "Error", description: "Network error during progress update.", variant: "destructive" })
    } finally {
      setIsUpdating(false)
    }
  }

  const filteredCourses = courses.filter((course) => {
    const progress = getCourseProgress(course.id)
    const isCompleted = progress === 100
    const matchesSearch = course.title.toLowerCase().includes(searchTerm.toLowerCase())

    if (filterStatus === "completed" && !isCompleted) {
      return false
    }
    if (filterStatus === "incomplete" && isCompleted) {
      return false
    }
    return matchesSearch
  })

  if (loadingAuth || loadingData) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-lg text-gray-600">Loading your progress...</p>
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
    <div className="min-h-screen bg-gray-100 py-12 px-4 md:px-6">
      <div className="container mx-auto">
        <div className="flex flex-col sm:flex-row items-center justify-between mb-8 gap-4">
          <h1 className="text-3xl font-bold text-gray-800">My Detailed Progress</h1>
          <Button
            asChild
            variant="outline"
            className="text-[#4F46E5] border-[#4F46E5] hover:bg-[#4F46E5] hover:text-white bg-transparent"
          >
            <Link href="/dashboard">Back to Dashboard</Link>
          </Button>
        </div>

        <div className="flex flex-col md:flex-row gap-4 mb-8">
          <div className="relative flex-1">
            <Input
              placeholder="Search courses..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10"
            />
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
          </div>
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-full md:w-[180px]">
              <SelectValue placeholder="Filter by status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Courses</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="incomplete">Incomplete</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {filteredCourses.length === 0 ? (
          <Card className="p-6 text-center shadow-md">
            <CardTitle className="text-xl font-semibold">No Courses Found</CardTitle>
            <CardDescription className="mt-2 text-gray-600">
              {searchTerm
                ? `No courses match "${searchTerm}".`
                : "It looks like there are no courses to track yet or no courses match your filter."}
            </CardDescription>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredCourses.map((course) => {
              const progress = getCourseProgress(course.id)
              const isCompleted = progress === 100
              const completedAt = getCompletedAt(course.id)
              return (
                <Card key={course.id} className="shadow-md hover:shadow-lg transition-shadow duration-200">
                  <CardHeader>
                    <CardTitle className="text-lg font-semibold">{course.title}</CardTitle>
                    <CardDescription className="text-gray-600 text-sm">{course.description}</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex items-center justify-between text-sm text-gray-700">
                      <span>Progress:</span>
                      <span className="font-bold">{progress}%</span>
                    </div>
                    <Progress value={progress} className="w-full h-2" />
                    {isCompleted && completedAt && (
                      <p className="text-xs text-gray-500 text-right">Completed on: {completedAt}</p>
                    )}
                    <Button
                      type="button"
                      variant={isCompleted ? "outline" : "default"}
                      className={`w-full mt-4 ${isCompleted ? "text-green-600 border-green-600 hover:bg-green-50 hover:text-green-700" : "bg-[#4F46E5] text-white hover:bg-[#3b34b0]"}`}
                      onClick={() => handleMarkComplete(course.id, progress)}
                      disabled={isUpdating}
                    >
                      {isUpdating ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : isCompleted ? (
                        <CheckCircle className="mr-2 h-4 w-4" />
                      ) : (
                        <Circle className="mr-2 h-4 w-4" />
                      )}
                      {isCompleted ? "Mark as Incomplete" : "Mark as Complete"}
                    </Button>
                    <Button asChild variant="ghost" className="w-full justify-center text-[#4F46E5] hover:underline">
                      <a href={course.video_url} target="_blank" rel="noopener noreferrer">
                        <PlayCircle className="h-5 w-5 mr-2" /> Watch Video
                      </a>
                    </Button>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
