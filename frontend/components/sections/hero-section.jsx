import Image from "next/image"
import { Button } from "@/components/ui/button"
import { PlayCircle, Users, Scale, BookOpen } from "lucide-react"
import Link from "next/link" // Import Link

export function HeroSection() {
  return (
    <section className="relative w-full py-24 md:py-32 lg:py-40 pt-32 md:pt-40 lg:pt-48">
      {" "}
      {/* Added top padding to account for fixed header */}
      <div className="container mx-auto px-4 md:px-6 grid lg:grid-cols-2 gap-12 items-center">
        {/* Left Content Section */}
        <div className="space-y-6 text-center lg:text-left animate-fade-in">
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-extrabold leading-tight text-gray-900 animate-slide-in-up">
            Master the <span className="text-[#4F46E5]">NCLEX</span> with Expert Guidance
          </h1>
          <p className="text-lg md:text-xl text-gray-700 animate-slide-in-up delay-100">
            Join thousands of nursing students who have successfully passed their NCLEX exam with our comprehensive
            virtual tutoring program.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start pt-4 animate-slide-in-up delay-200">
            <Button
              asChild
              className="bg-[#4F46E5] text-white px-8 py-3 text-lg rounded-md hover:bg-[#3b34b0] transition-colors shadow-md"
            >
              <Link href="/register">Start Learning Today</Link>
            </Button>
            <Button
              variant="ghost"
              className="text-gray-700 hover:bg-gray-100 hover:text-[#4F46E5] transition-colors flex items-center gap-2 px-6 py-3 text-lg rounded-md"
            >
              <PlayCircle className="h-6 w-6" />
              Watch Demo
            </Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8 pt-8 text-gray-800 animate-slide-in-up delay-300">
            <div className="flex flex-col items-center lg:items-start">
              <Users className="h-10 w-10 text-[#4F46E5] mb-2" />
              <span className="text-3xl font-bold">10,000+</span>
              <span className="text-sm text-gray-600">Students Enrolled</span>
            </div>
            <div className="flex flex-col items-center lg:items-start">
              <Scale className="h-10 w-10 text-[#4F46E5] mb-2" />
              <span className="text-3xl font-bold">95%</span>
              <span className="text-sm text-gray-600">Pass Rate</span>
            </div>
            <div className="flex flex-col items-center lg:items-start">
              <BookOpen className="h-10 w-10 text-[#4F46E5] mb-2" />
              <span className="text-3xl font-bold">500+</span>
              <span className="text-sm text-gray-600">Practice Questions</span>
            </div>
          </div>
        </div>

        {/* Right Image Section */}
        <div className="relative h-80 md:h-[400px] lg:h-[500px] w-full rounded-xl shadow-xl overflow-hidden flex items-center justify-center animate-fade-in delay-400">
          <Image
            src="https://images.unsplash.com/photo-1576091160550-fd428796c875?q=80&w=2070&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D"
            alt="Nursing student studying"
            layout="fill"
            objectFit="cover"
            className="transition-transform duration-500 hover:scale-105"
          />
        </div>
      </div>
    </section>
  )
}
