import { Header } from "@/components/layout/header"
import { Footer } from "@/components/layout/footer"
import { HeroSection } from "@/components/sections/hero-section"
import { AboutSchoolSection } from "@/components/sections/about-school-section"
import { OurCoursesSection } from "@/components/sections/our-courses-section"
import { TestimonialsSection } from "@/components/sections/testimonials-section"
import { ContactUsSection } from "@/components/sections/contact-us-section"
import { OurServicesSection } from "@/components/sections/our-services-section" // Added import

export const metadata = {
  title: "Home", // This will combine with the template from layout.tsx to become "Home | NCLEX Virtual School"
  description:
    "Start your journey to NCLEX success with NCLEX Virtual School. Comprehensive courses, expert tutors, and flexible learning.",
  openGraph: {
    title: "Home | NCLEX Virtual School",
    description:
      "Start your journey to NCLEX success with NCLEX Virtual School. Comprehensive courses, expert tutors, and flexible learning.",
    url: "https://www.nclexvirtualschool.com", // Replace with your actual domain
  },
  // You can add more specific metadata here if needed, e.g., specific keywords for the homepage
}

export default function HomePage() {
  return (
    <div className="flex flex-col min-h-screen">
      <Header />
      <main className="flex-1">
        <HeroSection />
        {/* <NclexAdSection /> Removed usage */}
        <AboutSchoolSection />
        <OurServicesSection /> {/* Added OurServicesSection here */}
        <OurCoursesSection />
        <TestimonialsSection />
        <ContactUsSection />
      </main>
      <Footer />
    </div>
  )
}
