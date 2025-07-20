"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Upload, Users, BookOpen, Settings, LogOut, Edit, Trash2, X, Loader2 } from "lucide-react"
import { toast } from "@/hooks/use-toast"
import { useAuth } from "@/contexts/AuthContext" // Import useAuth
import { apiRequest, logout } from "@/lib/api" // Import apiRequest and logout

export default function AdminDashboardClientPage() {
  const { user, loading: loadingAuth } = useAuth() // Use user and loading from AuthContext
  const [isAdmin, setIsAdmin] = useState(false)
  const [activeTab, setActiveTab] = useState("courses")

  const [courseTitle, setCourseTitle] = useState("")
  const [courseDescription, setCourseDescription] = useState("")
  const [videoUrl, setVideoUrl] = useState("")
  const [editingCourseId, setEditingCourseId] = useState(null)

  const [selectedFile, setSelectedFile] = useState(null)
  const [isUploadingFile, setIsUploadingFile] = useState(false)

  const [courses, setCourses] = useState([])
  const [users, setUsers] = useState([])

  const [isAddingCourse, setIsAddingCourse] = useState(false)
  const [isDeletingCourse, setIsDeletingCourse] = useState(false)
  const [isUpdatingCourse, setIsUpdatingCourse] = useState(false)

  useEffect(() => {
    const fetchAdminData = async () => {
      if (loadingAuth) return // Wait for AuthContext to load

      if (user && user.role === "admin") {
        setIsAdmin(true)
        try {
          // Fetch courses
          const coursesResponse = await apiRequest("/api/admin/courses/", { method: "GET" })
          const coursesData = await coursesResponse.json()
          if (!coursesResponse.ok) throw new Error(coursesData.detail || "Failed to fetch courses.")
          setCourses(coursesData)

          // Fetch users
          const usersResponse = await apiRequest("/api/admin/users/", { method: "GET" })
          const usersData = await usersResponse.json()
          if (!usersResponse.ok) throw new Error(usersData.detail || "Failed to fetch users.")
          setUsers(usersData)
        } catch (error) {
          console.error("Failed to fetch admin data:", error)
          toast({ title: "Error", description: `Failed to load admin data: ${error.message}`, variant: "destructive" })
        }
      } else if (user && user.role !== "admin") {
        setIsAdmin(false)
        toast({
          title: "Access Denied",
          description: "You are not authorized to view this page.",
          variant: "destructive",
        })
        // Optionally redirect to login or home page
        // router.push('/login');
      } else if (!user && !loadingAuth) {
        // Not logged in
        setIsAdmin(false)
        toast({
          title: "Access Denied",
          description: "Please log in to view this page.",
          variant: "destructive",
        })
        // router.push('/login');
      }
    }

    fetchAdminData()
  }, [user, loadingAuth]) // Depend on user and loadingAuth from context

  const resetForm = () => {
    setCourseTitle("")
    setCourseDescription("")
    setVideoUrl("")
    setEditingCourseId(null)
    setSelectedFile(null)
  }

  const handleCourseFormSubmit = async (e) => {
    e.preventDefault()

    if (!courseTitle || !courseDescription || (!videoUrl && !selectedFile)) {
      toast({ title: "Validation Error", description: "Please fill all required fields.", variant: "destructive" })
      return
    }

    if (editingCourseId) {
      setIsUpdatingCourse(true)
      try {
        const response = await apiRequest(`/api/admin/courses/${editingCourseId}/`, {
          method: "PUT", // Or PATCH
          body: JSON.stringify({ title: courseTitle, description: courseDescription, video_url: videoUrl }),
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "Failed to update course.")

        setCourses((prevCourses) =>
          prevCourses.map((course) =>
            course.id === editingCourseId
              ? { ...course, title: data.title, description: data.description, video_url: data.video_url }
              : course,
          ),
        )
        toast({ title: "Course Updated", description: "Course updated successfully!" })
      } catch (error) {
        console.error("Update course API call failed:", error)
        toast({ title: "Error", description: `Failed to update course: ${error.message}`, variant: "destructive" })
      } finally {
        setIsUpdatingCourse(false)
        resetForm()
      }
    } else {
      setIsAddingCourse(true)
      try {
        const formData = new FormData()
        formData.append("title", courseTitle)
        formData.append("description", courseDescription)
        if (selectedFile) {
          formData.append("video_file", selectedFile)
        } else if (videoUrl) {
          formData.append("video_url", videoUrl)
        }

        const response = await apiRequest("/api/admin/courses/", {
          method: "POST",
          body: formData, // Send FormData for file upload
          headers: {
            // Do NOT set Content-Type for FormData, browser handles it
          },
        })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || "Failed to add course.")

        setCourses((prevCourses) => [data, ...prevCourses])
        toast({ title: "Course Uploaded", description: "Course added successfully!" })
      } catch (error) {
        console.error("Add course API call failed:", error)
        toast({ title: "Error", description: `Failed to add course: ${error.message}`, variant: "destructive" })
      } finally {
        setIsAddingCourse(false)
        resetForm()
      }
    }
  }

  const handleDeleteCourseClick = async (courseId) => {
    if (window.confirm("Are you sure you want to delete this course?")) {
      setIsDeletingCourse(true)
      try {
        const response = await apiRequest(`/api/admin/courses/${courseId}/`, {
          method: "DELETE",
        })

        if (response.ok) {
          setCourses((prevCourses) => prevCourses.filter((course) => course.id !== courseId))
          toast({ title: "Course Deleted", description: "Course deleted successfully!" })
        } else {
          const data = await response.json()
          throw new Error(data.detail || "Failed to delete course.")
        }
      } catch (error) {
        console.error("Delete course API call failed:", error)
        toast({ title: "Error", description: `Failed to delete course: ${error.message}`, variant: "destructive" })
      } finally {
        setIsDeletingCourse(false)
      }
    }
  }

  const handleEditCourseClick = (course) => {
    setEditingCourseId(course.id)
    setCourseTitle(course.title)
    setCourseDescription(course.description)
    setVideoUrl(course.video_url)
    setSelectedFile(null)
  }

  const handleLogout = () => {
    logout() // Use the logout function from lib/api
  }

  if (loadingAuth) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-lg text-gray-600">Loading admin dashboard...</p>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p className="text-lg text-red-600">Access Denied: You are not authorized to view this page.</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <header className="bg-white shadow-sm py-4 px-6 flex items-center justify-between border-b">
        <h1 className="text-2xl font-bold text-gray-800">Admin Dashboard</h1>
        <div className="flex items-center gap-4">
          <Button variant="ghost" className="text-gray-600 hover:text-[#4F46E5]">
            <Settings className="h-5 w-5 mr-2" /> Settings
          </Button>
          <Button onClick={handleLogout} className="bg-[#4F46E5] text-white hover:bg-[#3b34b0]">
            <LogOut className="h-5 w-5 mr-2" /> Logout
          </Button>
        </div>
      </header>

      <div className="container mx-auto px-4 py-8">
        {/* Tab Navigation */}
        <div className="flex border-b border-gray-200 mb-8">
          <Button
            variant="ghost"
            className={`rounded-none border-b-2 ${activeTab === "courses" ? "border-[#4F46E5] text-[#4F46E5]" : "border-transparent text-gray-600 hover:text-gray-800"}`}
            onClick={() => setActiveTab("courses")}
          >
            <BookOpen className="h-5 w-5 mr-2" /> Course Management
          </Button>
          <Button
            variant="ghost"
            className={`rounded-none border-b-2 ${activeTab === "users" ? "border-[#4F46E5] text-[#4F46E5]" : "border-transparent text-gray-600 hover:text-gray-800"}`}
            onClick={() => setActiveTab("users")}
          >
            <Users className="h-5 w-5 mr-2" /> User Monitoring
          </Button>
        </div>

        {/* Tab Content */}
        {activeTab === "courses" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Left Column: Upload/Edit Course & Quick Stats */}
            <div className="lg:col-span-1 space-y-8">
              <Card className="p-6 shadow-md">
                <CardTitle className="text-xl font-semibold mb-4 flex items-center gap-2">
                  <Upload className="h-6 w-6 text-[#4F46E5]" /> {editingCourseId ? "Edit Course" : "Upload New Course"}
                </CardTitle>
                <CardContent className="p-0">
                  <form onSubmit={handleCourseFormSubmit} className="space-y-4">
                    <div className="space-y-2">
                      <Label htmlFor="courseTitle">Course Title</Label>
                      <Input
                        id="courseTitle"
                        name="courseTitle"
                        placeholder="e.g., NCLEX-RN Foundations"
                        value={courseTitle}
                        onChange={(e) => setCourseTitle(e.target.value)}
                        required
                        disabled={isAddingCourse || isUpdatingCourse || isUploadingFile}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="courseDescription">Description</Label>
                      <Textarea
                        id="courseDescription"
                        name="courseDescription"
                        placeholder="Brief description of the course content."
                        value={courseDescription}
                        onChange={(e) => setCourseDescription(e.target.value)}
                        rows={3}
                        required
                        disabled={isAddingCourse || isUpdatingCourse || isUploadingFile}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="videoFile">Upload Video File</Label>
                      <Input
                        id="videoFile"
                        type="file"
                        name="videoFile"
                        accept="video/*"
                        onChange={(e) => setSelectedFile(e.target.files ? e.target.files[0] : null)}
                        disabled={isAddingCourse || isUpdatingCourse || isUploadingFile}
                      />
                      {selectedFile && <p className="text-sm text-gray-500 mt-1">Selected: {selectedFile.name}</p>}
                      <p className="text-sm text-gray-500 mt-1">OR provide a direct URL:</p>
                      <Input
                        id="videoUrl"
                        type="url"
                        name="videoUrl"
                        placeholder="https://youtube.com/watch?v=..."
                        value={videoUrl}
                        onChange={(e) => {
                          setVideoUrl(e.target.value)
                          setSelectedFile(null)
                        }}
                        disabled={isAddingCourse || isUpdatingCourse || isUploadingFile}
                      />
                    </div>
                    <Button
                      type="submit"
                      className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0]"
                      disabled={isAddingCourse || isUpdatingCourse || isUploadingFile}
                    >
                      {isUploadingFile ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Uploading File...
                        </>
                      ) : editingCourseId ? (
                        isUpdatingCourse ? (
                          "Updating..."
                        ) : (
                          "Update Course"
                        )
                      ) : isAddingCourse ? (
                        "Uploading..."
                      ) : (
                        "Upload Course"
                      )}
                    </Button>
                    {editingCourseId && (
                      <Button
                        type="button"
                        variant="outline"
                        onClick={resetForm}
                        className="w-full mt-2 text-gray-700 border-gray-300 hover:bg-gray-100 bg-transparent"
                        disabled={isAddingCourse || isUpdatingCourse || isUploadingFile}
                      >
                        <X className="h-4 w-4 mr-2" /> Cancel Edit
                      </Button>
                    )}
                  </form>
                </CardContent>
              </Card>

              <Card className="p-6 shadow-md">
                <CardTitle className="text-xl font-semibold mb-4">Overview</CardTitle>
                <CardContent className="p-0 space-y-4">
                  <div className="flex items-center justify-between text-gray-700">
                    <span className="flex items-center gap-2">
                      <Users className="h-5 w-5 text-[#4F46E5]" /> Total Users:
                    </span>
                    <span className="font-bold text-lg">{users.length}</span>
                  </div>
                  <div className="flex items-center justify-between text-gray-700">
                    <span className="flex items-center gap-2">
                      <BookOpen className="h-5 w-5 text-[#4F46E5]" /> Total Courses:
                    </span>
                    <span className="font-bold text-lg">{courses.length}</span>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Right Column: Course Management */}
            <div className="lg:col-span-2 space-y-8">
              <Card className="p-6 shadow-md">
                <CardTitle className="text-xl font-semibold mb-4 flex items-center gap-2">
                  <BookOpen className="h-6 w-6 text-[#4F46E5]" /> Manage Courses
                </CardTitle>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Title</TableHead>
                        <TableHead>Description</TableHead>
                        <TableHead>Video URL</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {courses.length > 0 ? (
                        courses.map((course) => (
                          <TableRow key={course.id}>
                            <TableCell className="font-medium">{course.title}</TableCell>
                            <TableCell className="text-sm text-gray-600">{course.description}</TableCell>
                            <TableCell>
                              <a
                                href={course.video_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-[#4F46E5] hover:underline text-sm"
                              >
                                View Link
                              </a>
                            </TableCell>
                            <TableCell className="text-right">
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-gray-600 hover:text-blue-500"
                                onClick={() => handleEditCourseClick(course)}
                                disabled={isAddingCourse || isUpdatingCourse || isDeletingCourse || isUploadingFile}
                              >
                                <Edit className="h-4 w-4" />
                                <span className="sr-only">Edit</span>
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-8 w-8 text-gray-600 hover:text-red-500"
                                onClick={() => handleDeleteCourseClick(course.id)}
                                disabled={isDeletingCourse || isAddingCourse || isUpdatingCourse || isUploadingFile}
                              >
                                <Trash2 className="h-4 w-4" />
                                <span className="sr-only">Delete</span>
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center text-gray-500">
                            No courses found.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          </div>
        )}

        {activeTab === "users" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div className="lg:col-span-2">
              <Card className="p-6 shadow-md">
                <CardTitle className="text-xl font-semibold mb-4 flex items-center gap-2">
                  <Users className="h-6 w-6 text-[#4F46E5]" /> User Progress Monitoring
                </CardTitle>
                <CardContent className="p-0">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>User Name</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead>Role</TableHead>
                        <TableHead className="text-right">Courses Completed</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {users.length > 0 ? (
                        users.map((userProfile) => (
                          <TableRow key={userProfile.id}>
                            <TableCell className="font-medium">{userProfile.full_name || "N/A"}</TableCell>
                            <TableCell>{userProfile.email}</TableCell>
                            <TableCell>{userProfile.role}</TableCell>
                            <TableCell className="text-right">
                              {userProfile.courses_completed_count !== undefined
                                ? userProfile.courses_completed_count
                                : "N/A"}
                            </TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center text-gray-500">
                            No users found.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
