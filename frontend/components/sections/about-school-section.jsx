import { CheckCircle } from "lucide-react"

export function AboutSchoolSection() {
  return (
    <section id="about-school" className="py-16 md:py-24 bg-white">
      <div className="container mx-auto px-4 md:px-6 grid grid-cols-1 gap-12 items-center">
        {" "}
        {/* Changed to grid-cols-1 */}
        <div className="space-y-6 animate-fade-in-left text-center md:text-left">
          {" "}
          {/* Added text-center for smaller screens */}
          <h2 className="text-3xl md:text-4xl font-bold text-gray-800">About Our NCLEX Tutoring School</h2>
          <p className="text-gray-600 leading-relaxed">
            Welcome to NCLEX Prep, your dedicated partner in achieving success on the NCLEX examination. We provide a
            virtual learning environment designed to equip aspiring nurses with the knowledge, strategies, and
            confidence needed to pass their exams. Our comprehensive programs are tailored to meet individual learning
            styles, ensuring every student receives the support they need.
          </p>
          <ul className="space-y-3 text-gray-700 max-w-2xl mx-auto md:mx-0">
            {" "}
            {/* Added max-w-2xl and mx-auto for centering */}
            <li className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-[#4F46E5] flex-shrink-0" />
              PERSONALIZED GUIDANCE AND SUPPORT
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-[#4F46E5] flex-shrink-0" />
              EXCLUSIVE ONLINE GROUPS (WHATSAPP & TELEGRAM)
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-[#4F46E5] flex-shrink-0" />
              FOR DAILY LEARNING AND Q&A
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-[#4F46E5] flex-shrink-0" />
              LIVE TEACHING SESSIONS (9 HOURS A WEEK)
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-[#4F46E5] flex-shrink-0" />
              CUSTOMIZED STUDY PLANS AND TIMETABLES
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-[#4F46E5] flex-shrink-0" />
              WEEKLY CONTACT HOURS (4 HOURS) WITH SEASONED TUTORS
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-[#4F46E5] flex-shrink-0" />
              DAILY UWORLD QUESTIONS
            </li>
            <li className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-[#4F46E5] flex-shrink-0" />
              UNLIMITED ACCESS TO TUTORS AND RESOURCES
            </li>
          </ul>
        </div>
        {/* Removed the Image section entirely */}
      </div>
    </section>
  )
}
