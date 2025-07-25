"use client"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { MenuIcon, Stethoscope } from "lucide-react"
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet"

export function Header() {
  return (
    <header className="flex items-center justify-between h-20 px-4 md:px-6 bg-white/80 backdrop-blur-sm shadow-sm fixed w-full z-50 top-0">
      <Link href="#" className="flex items-center gap-2 text-xl font-bold text-gray-800">
        <Stethoscope className="h-8 w-8 text-[#4F46E5]" />
        NCLEX KEYS
      </Link>
      <nav className="hidden md:flex items-center gap-8 text-base font-medium">
        <Link href="/" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
          Home
        </Link>
        <Link href="#about-school" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
          About
        </Link>
        <Link href="#our-courses" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
          Programs
        </Link>
        <Link href="#our-services" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
          {" "}
          {/* Added Services link */}
          Services
        </Link>
        <Link href="#contact-us" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
          Contact
        </Link>
      </nav>
      <div className="hidden md:flex items-center gap-3">
        <Button
          asChild
          variant="ghost"
          className="text-gray-700 hover:bg-gray-100 hover:text-[#4F46E5] transition-colors"
        >
          <Link href="/login">Sign In</Link>
        </Button>
        <Button asChild className="bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors px-6 py-2 rounded-md">
          <Link href="/register">Get Started</Link>
        </Button>
      </div>
      <Sheet>
        <SheetTrigger asChild>
          <Button variant="outline" size="icon" className="md:hidden bg-transparent">
            <MenuIcon className="h-6 w-6" />
            <span className="sr-only">Toggle navigation menu</span>
          </Button>
        </SheetTrigger>
        <SheetContent side="right">
          <div className="flex flex-col gap-6 pt-6">
            <Link href="/" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
              Home
            </Link>
            <Link href="#about-school" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
              About
            </Link>
            <Link href="#our-courses" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
              Programs
            </Link>
            <Link href="#our-services" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
              {" "}
              {/* Added Services link */}
              Services
            </Link>
            <Link href="#contact-us" className="text-gray-600 hover:text-[#4F46E5] transition-colors">
              Contact
            </Link>
            <Button
              asChild
              variant="ghost"
              className="text-gray-700 hover:bg-gray-100 hover:text-[#4F46E5] transition-colors"
            >
              <Link href="/login">Sign In</Link>
            </Button>
            <Button asChild className="bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors">
              <Link href="/register">Get Started</Link>
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </header>
  )
}
