import Link from "next/link"
import { Facebook, Instagram, Linkedin, Twitter, Stethoscope } from "lucide-react"

export function Footer() {
  return (
    <footer className="bg-gray-800 text-gray-300 py-12 md:py-16">
      <div className="container mx-auto px-4 md:px-6 grid grid-cols-1 md:grid-cols-4 gap-8">
        <div className="space-y-4">
          <Link href="#" className="flex items-center gap-2 text-2xl font-bold text-white">
            <Stethoscope className="h-8 w-8 text-white" /> {/* Changed icon to Stethoscope */}
            NCLEX KEYS {/* Changed text to NCLEX KEYS */}
          </Link>
          <p className="text-sm leading-relaxed">
            Your trusted partner for NCLEX success. Providing expert tutoring and comprehensive resources.
          </p>
          <div className="flex gap-4">
            <a href="#" className="text-gray-400 hover:text-white transition-colors">
              <Facebook className="h-6 w-6" />
              <span className="sr-only">Facebook</span>
            </a>
            <a href="#" className="text-gray-400 hover:text-white transition-colors">
              <Twitter className="h-6 w-6" />
              <span className="sr-only">Twitter</span>
            </a>
            <a href="#" className="text-gray-400 hover:text-white transition-colors">
              <Instagram className="h-6 w-6" />
              <span className="sr-only">Instagram</span>
            </a>
            <a href="#" className="text-gray-400 hover:text-white transition-colors">
              <Linkedin className="h-6 w-6" />
              <span className="sr-only">LinkedIn</span>
            </a>
          </div>
        </div>

        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-white mb-2">Quick Links</h3>
          <ul className="space-y-2 text-sm">
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                About Us
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                Our Courses
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                Our Tutors
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                Blog
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                Contact
              </Link>
            </li>
          </ul>
        </div>

        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-white mb-2">Support</h3>
          <ul className="space-y-2 text-sm">
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                FAQ
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                Privacy Policy
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                Terms of Service
              </Link>
            </li>
            <li>
              <Link href="#" className="hover:text-white transition-colors">
                Sitemap
              </Link>
            </li>
          </ul>
        </div>

        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-white mb-2">Contact Us</h3>
          <p className="text-sm">
            123 Virtual School Rd, <br />
            Online City, Global 12345
          </p>
          <p className="text-sm">Email: info@nclexprep.com</p>
        </div>
      </div>

      <div className="border-t border-gray-700 mt-12 pt-8 text-center text-sm text-gray-400">
        &copy; {new Date().getFullYear()} NCLEX Prep. All rights reserved.
      </div>
    </footer>
  )
}
