import { MessagesClientWrapper } from "./messages-client"

export const metadata = {
  title: "Messages",
  description: "Communicate with tutors and other students.",
}

export default function MessagesPage() {
  // In a purely frontend app, we don't check user authentication here.
  // We assume a user is "logged in" for the purpose of displaying the UI.
  const mockUserId = "mock-user-id-123" // Hardcode a mock user ID

  return <MessagesClientWrapper currentUserId={mockUserId} />
}
