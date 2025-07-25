import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ClipboardCheck, Languages, Users } from "lucide-react"

export function OurServicesSection() {
  const services = [
    {
      title: "NCLEX-RN Prep",
      description: "Comprehensive preparation for the NCLEX-RN examination, covering all essential topics.",
      icon: ClipboardCheck,
      delay: "delay-100",
    },
    {
      title: "NCLEX-LPN Prep",
      description: "Tailored study programs for the NCLEX-LPN exam, focusing on practical nursing skills.",
      icon: ClipboardCheck,
      delay: "delay-200",
    },
    {
      title: "IELTS Coaching",
      description: "Expert coaching for the IELTS exam, helping you achieve your desired band score.",
      icon: Languages,
      delay: "delay-300",
    },
    {
      title: "Personalized Tutoring",
      description: "One-on-one and group tutoring sessions with experienced instructors for all subjects.",
      icon: Users,
      delay: "delay-400",
    },
  ]

  return (
    <section id="our-services" className="py-16 md:py-24 bg-white">
      <div className="container mx-auto px-4 md:px-6 text-center">
        <h2 className="text-3xl md:text-4xl font-bold text-gray-800 mb-12 animate-slide-in-up">
          Our Comprehensive Services
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 max-w-6xl mx-auto">
          {services.map((service, index) => (
            <Card
              key={index}
              // Added 'group' class for hover effects on children
              className={`group flex flex-col items-center text-center p-6 rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 ease-in-out transform hover:-translate-y-2 animate-slide-in-up ${service.delay}`}
            >
              <CardHeader className="flex flex-col items-center p-0 pb-4">
                {/* Added group-hover:animate-pulse for icon animation */}
                <service.icon className="h-12 w-12 text-[#4F46E5] mb-4 transition-transform duration-300 group-hover:scale-110 group-hover:animate-pulse" />
                <CardTitle className="text-xl font-bold text-gray-900">{service.title}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <p className="text-gray-600">{service.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
