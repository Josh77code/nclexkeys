import { Button } from "@/components/ui/button"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { ArrowRight } from "lucide-react"
import Link from "next/link"

export function OurCoursesSection() {
  const pricingData = [
    {
      category: "EXCLUSIVE",
      regions: [
        { region: "NIGERIA", price: "30,000 NGN", per: "PER MONTH" },
        { region: "AFRICAN", price: "35,000 NGN", per: "PER MONTH" },
        { region: "USA/CANADA", price: "60 DOLLARS", per: "PER MONTH" },
        { region: "EUROPE", price: "35 POUNDS", per: "PER MONTH" },
      ],
    },
    {
      category: "EXCLUSIVE",
      subCategory: "WITH ONE ON ONE PUSH",
      regions: [
        { region: "NIGERIA", price: "60,000 NGN", per: "PER MONTH" },
        { region: "AFRICAN", price: "65,000 NGN", per: "PER MONTH" },
        { region: "USA/CANADA", price: "100 DOLLARS", per: "PER MONTH" },
        { region: "EUROPE", price: "50 POUNDS", per: "PER MONTH" },
      ],
    },
  ]

  return (
    <section id="our-courses" className="py-16 md:py-24 bg-gray-50">
      <div className="container mx-auto px-4 md:px-6 text-center">
        <h2 className="text-3xl md:text-4xl font-bold text-gray-800 mb-12 animate-fade-in-up">
          Our Comprehensive NCLEX Programs & Pricing
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8 max-w-6xl mx-auto">
          {pricingData.map((categoryData, categoryIndex) =>
            categoryData.regions.map((item, regionIndex) => (
              <Card
                key={`${categoryIndex}-${regionIndex}`}
                className="flex flex-col overflow-hidden rounded-xl shadow-lg hover:shadow-xl transition-all duration-300 ease-in-out transform hover:-translate-y-2 animate-fade-in-up p-6 text-center bg-white text-gray-800"
              >
                <CardHeader className="flex-grow p-0 pb-4">
                  <CardTitle className="text-xl font-bold mb-2 text-gray-900">{item.region}</CardTitle>
                  <p className="text-sm font-semibold text-[#4F46E5]">
                    {categoryData.category}
                    {categoryData.subCategory && (
                      <span className="text-xs font-normal flex items-center justify-center gap-1 text-gray-600 mt-1">
                        {categoryData.subCategory.split("WITH ")[1]} <ArrowRight className="h-3 w-3" />
                      </span>
                    )}
                  </p>
                </CardHeader>
                <CardContent className="p-0">
                  <span className="text-3xl font-bold text-[#4F46E5]">{item.price}</span>
                  <span className="text-base text-gray-600 block">{item.per}</span>
                </CardContent>
                <CardFooter className="pt-6 p-0">
                  <Button className="w-full bg-[#4F46E5] text-white hover:bg-[#3b34b0] transition-colors" asChild>
                    <Link href="/register">Learn More</Link>
                  </Button>
                </CardFooter>
              </Card>
            )),
          )}
        </div>
      </div>
    </section>
  )
}
