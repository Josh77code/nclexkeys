# Backend Integration Guide for Django Engineer - NCLEX Virtual School

This document outlines the required API endpoints and backend logic for integrating a Django backend with the existing Next.js frontend application. The frontend is currently operating with mock data and client-side simulations. Your task is to implement the necessary backend services to provide real data persistence, authentication, and business logic.

## General Backend Requirements

1.  **Framework:** Django with Django REST Framework (DRF) is recommended for building RESTful APIs.
2.  **Authentication:**
    *   Implement a robust authentication system. JWT (JSON Web Tokens) is highly recommended for stateless API authentication.
    *   Endpoints should return a token upon successful login/registration, which the frontend will store and send with subsequent authenticated requests (e.g., in the `Authorization: Bearer <token>` header).
    *   Implement token refresh mechanisms if using short-lived access tokens.
3.  **Authorization:**
    *   Implement permissions to control access to resources based on user roles (e.g., `user`, `admin`).
    *   Ensure only authenticated and authorized users can perform specific actions (e.g., only admins can create/update/delete courses).
4.  **CORS (Cross-Origin Resource Sharing):**
    *   Configure Django to allow requests from your frontend's origin (e.g., `http://localhost:3000` during development, and your Vercel deployment URL in production). Use `django-cors-headers`.
5.  **Database Schema:**
    *   Design appropriate database models for Users, Courses, User Progress, Messages, etc.
    *   Consider fields like `created_at`, `updated_at` for auditing.
6.  **Error Handling:**
    *   Return meaningful HTTP status codes (e.g., 200 OK, 201 Created, 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 500 Internal Server Error).
    *   Provide clear, consistent JSON error responses (e.g., `{"detail": "Error message here"}`).
7.  **Environment Variables:**
    *   Manage sensitive information (database credentials, API keys, secret keys) using Django's settings and environment variables.

---

## Specific API Endpoints Required

### 1. Authentication & User Management

**Frontend Components:** `app/login/ClientLoginPage.jsx`, `app/register/RegisterClientPage.jsx`, `app/forgot-password/ForgotPasswordClientPage.jsx`, `app/auth/update-password/UpdatePasswordClientPage.jsx`, `components/user-profile-form.jsx`

*   **User Model:** Needs fields for `email`, `password` (hashed), `full_name`, `role` (e.g., 'user', 'admin'), `created_at`, `updated_at`.

#### 1.1. User Registration

*   **Endpoint:** `/api/auth/register/`
*   **Method:** `POST`
*   **Request Body (JSON):**
    \`\`\`json
    {
      "full_name": "John Doe",
      "email": "john.doe@example.com",
      "password": "securepassword123",
      "confirm_password": "securepassword123" // Backend should validate this
    }
    \`\`\`
*   **Expected Response (201 Created - JSON):**
    \`\`\`json
    {
      "message": "Registration successful. Please check your email to confirm your account.",
      "user": {
        "id": "uuid-of-user",
        "email": "john.doe@example.com",
        "full_name": "John Doe",
        "role": "user"
      }
    }
    \`\`\`
*   **Error Responses (400 Bad Request - JSON):**
    *   `{"detail": "Passwords do not match."}`
    *   `{"detail": "Email already registered."}`
    *   `{"detail": "Invalid input data."}`

#### 1.2. User Login

*   **Endpoint:** `/api/auth/login/`
*   **Method:** `POST`
*   **Request Body (JSON):**
    \`\`\`json
    {
      "email": "john.doe@example.com",
      "password": "securepassword123"
    }
    \`\`\`
*   **Expected Response (200 OK - JSON):**
    \`\`\`json
    {
      "message": "Login successful.",
      "token": "your_jwt_token_here", // Or access_token/refresh_token pair
      "user": {
        "id": "uuid-of-user",
        "email": "john.doe@example.com",
        "full_name": "John Doe",
        "role": "user"
      }
    }
    \`\`\`
*   **Error Responses (401 Unauthorized - JSON):**
    *   `{"detail": "Invalid credentials."}`

#### 1.3. Forgot Password (Request Reset Link)

*   **Endpoint:** `/api/auth/forgot-password/`
*   **Method:** `POST`
*   **Request Body (JSON):**
    \`\`\`json
    {
      "email": "john.doe@example.com"
    }
    \`\`\`
*   **Expected Response (200 OK - JSON):**
    \`\`\`json
    {
      "message": "Password reset link sent to your email."
    }
    \`\`\`
*   **Notes:** This should generate a unique, time-limited token and send it to the user's email address.

#### 1.4. Update Password (Using Reset Token)

*   **Endpoint:** `/api/auth/reset-password/confirm/` (or similar, including token in URL/body)
*   **Method:** `POST`
*   **Request Body (JSON):**
    \`\`\`json
    {
      "token": "the_reset_token_from_email",
      "new_password": "newsecurepassword",
      "confirm_new_password": "newsecurepassword"
    }
    \`\`\`
*   **Expected Response (200 OK - JSON):**
    \`\`\`json
    {
      "message": "Your password has been updated successfully."
    }
    \`\`\`
*   **Error Responses (400 Bad Request - JSON):**
    *   `{"detail": "Invalid or expired token."}`
    *   `{"detail": "Passwords do not match."}`

#### 1.5. User Profile Update

*   **Endpoint:** `/api/users/me/` (or `/api/users/{user_id}/`)
*   **Method:** `PUT` or `PATCH`
*   **Authentication:** Required (JWT)
*   **Request Body (JSON):**
    \`\`\`json
    {
      "full_name": "Updated Name"
      // Email is not editable via this form, as per frontend
    }
    \`\`\`
*   **Expected Response (200 OK - JSON):**
    \`\`\`json
    {
      "id": "uuid-of-user",
      "email": "john.doe@example.com",
      "full_name": "Updated Name",
      "role": "user"
    }
    \`\`\`

### 2. Course Management (Admin & User Views)

**Frontend Components:** `app/admin/AdminDashboardClientPage.jsx`, `app/dashboard/DashboardClientPage.jsx`, `app/dashboard/progress/ClientProgressPage.jsx`

*   **Course Model:** Needs fields for `id`, `title`, `description`, `video_url`, `created_at`.
*   **UserCourseProgress Model:** Needs fields for `user` (FK), `course` (FK), `progress_percentage` (0-100), `completed_at`.

#### 2.1. Admin: Create New Course

*   **Endpoint:** `/api/admin/courses/`
*   **Method:** `POST`
*   **Authentication:** Required (Admin role)
*   **Request Body (JSON):**
    \`\`\`json
    {
      "title": "New NCLEX Course",
      "description": "A detailed description of the new course.",
      "video_url": "https://youtube.com/watch?v=new_video_id"
      // Or handle file upload separately if direct video upload is preferred over URL
    }
    \`\`\`
*   **Expected Response (201 Created - JSON):**
    \`\`\`json
    {
      "id": "new-course-uuid",
      "title": "New NCLEX Course",
      "description": "A detailed description of the new course.",
      "video_url": "https://youtube.com/watch?v=new_video_id",
      "created_at": "2023-10-27T10:00:00Z"
    }
    \`\`\`

#### 2.2. Admin: List All Courses

*   **Endpoint:** `/api/admin/courses/`
*   **Method:** `GET`
*   **Authentication:** Required (Admin role)
*   **Expected Response (200 OK - JSON Array):**
    \`\`\`json
    [
      {
        "id": "course-1-uuid",
        "title": "NCLEX-RN Fundamentals",
        "description": "Basic nursing concepts and principles.",
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "created_at": "2023-01-15T08:00:00Z"
      },
      // ... more courses
    ]
    \`\`\`

#### 2.3. Admin: Update Course

*   **Endpoint:** `/api/admin/courses/{course_id}/`
*   **Method:** `PUT` or `PATCH`
*   **Authentication:** Required (Admin role)
*   **Request Body (JSON):**
    \`\`\`json
    {
      "title": "Updated Course Title",
      "description": "Revised description.",
      "video_url": "https://youtube.com/watch?v=updated_video_id"
    }
    \`\`\`
*   **Expected Response (200 OK - JSON):**
    \`\`\`json
    {
      "id": "course-id",
      "title": "Updated Course Title",
      "description": "Revised description.",
      "video_url": "https://youtube.com/watch?v=updated_video_id",
      "created_at": "2023-01-15T08:00:00Z"
    }
    \`\`\`

#### 2.4. Admin: Delete Course

*   **Endpoint:** `/api/admin/courses/{course_id}/`
*   **Method:** `DELETE`
*   **Authentication:** Required (Admin role)
*   **Expected Response (204 No Content):** Empty response body.

#### 2.5. User: List All Available Courses

*   **Endpoint:** `/api/courses/`
*   **Method:** `GET`
*   **Authentication:** Optional (can show public courses, or all if authenticated)
*   **Expected Response (200 OK - JSON Array):**
    \`\`\`json
    [
      {
        "id": "course-1-uuid",
        "title": "NCLEX-RN Fundamentals",
        "description": "Basic nursing concepts and principles.",
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
      },
      // ... more courses
    ]
    \`\`\`

#### 2.6. User: Get My Course Progress

*   **Endpoint:** `/api/users/me/progress/`
*   **Method:** `GET`
*   **Authentication:** Required (JWT)
*   **Expected Response (200 OK - JSON Array):**
    \`\`\`json
    [
      {
        "user_id": "current-user-uuid",
        "course_id": "course-1-uuid",
        "progress_percentage": 100,
        "completed_at": "2023-09-01T14:30:00Z"
      },
      {
        "user_id": "current-user-uuid",
        "course_id": "course-2-uuid",
        "progress_percentage": 50,
        "completed_at": null
      }
      // ... more progress entries
    ]
    \`\`\`

#### 2.7. User: Update Course Progress (Mark Complete/Incomplete)

*   **Endpoint:** `/api/users/me/progress/{course_id}/`
*   **Method:** `PUT` or `PATCH`
*   **Authentication:** Required (JWT)
*   **Request Body (JSON):**
    \`\`\`json
    {
      "progress_percentage": 100 // Or 0 to mark incomplete
    }
    \`\`\`
*   **Expected Response (200 OK - JSON):**
    \`\`\`json
    {
      "user_id": "current-user-uuid",
      "course_id": "course-id",
      "progress_percentage": 100,
      "completed_at": "2023-10-27T15:00:00Z" // Or null if marked incomplete
    }
    \`\`\`

### 3. Messaging

**Frontend Components:** `components/messaging/chat-interface.jsx`, `components/messaging/conversation-list.jsx`

*   **Message Model:** Needs fields for `id`, `sender` (FK to User), `receiver` (FK to User), `content`, `created_at`.

#### 3.1. Get My Conversations (List of Users I've chatted with)

*   **Endpoint:** `/api/messages/conversations/`
*   **Method:** `GET`
*   **Authentication:** Required (JWT)
*   **Expected Response (200 OK - JSON Array):**
    \`\`\`json
    [
      {
        "user_id": "other-user-uuid-1",
        "full_name": "Dr. Sarah Chen",
        "email": "sarah.chen@example.com",
        "last_message_content": "Hello! I'd be happy to help.",
        "last_message_time": "2023-10-27T14:50:00Z"
      },
      {
        "user_id": "other-user-uuid-2",
        "full_name": "Jane Doe",
        "email": "jane.doe@example.com",
        "last_message_content": "Thanks for the help!",
        "last_message_time": "2023-10-26T18:00:00Z"
      }
    ]
    \`\`\`
*   **Notes:** This endpoint should return a list of users with whom the current user has active conversations, possibly including the last message for display.

#### 3.2. Get Messages for a Specific Conversation

*   **Endpoint:** `/api/messages/conversation/{other_user_id}/`
*   **Method:** `GET`
*   **Authentication:** Required (JWT)
*   **Expected Response (200 OK - JSON Array):**
    \`\`\`json
    [
      {
        "id": "msg-uuid-1",
        "sender_id": "current-user-uuid",
        "receiver_id": "other-user-uuid",
        "content": "Hi there! I have a question about pharmacology.",
        "created_at": "2023-10-27T14:40:00Z"
      },
      {
        "id": "msg-uuid-2",
        "sender_id": "other-user-uuid",
        "receiver_id": "current-user-uuid",
        "content": "Hello! I'd be happy to help. What specifically are you struggling with?",
        "created_at": "2023-10-27T14:50:00Z"
      }
      // ... more messages, ordered by created_at
    ]
    \`\`\`

#### 3.3. Send New Message

*   **Endpoint:** `/api/messages/send/`
*   **Method:** `POST`
*   **Authentication:** Required (JWT)
*   **Request Body (JSON):**
    \`\`\`json
    {
      "receiver_id": "target-user-uuid",
      "content": "My new message content."
    }
    \`\`\`
*   **Expected Response (201 Created - JSON):**
    \`\`\`json
    {
      "id": "new-msg-uuid",
      "sender_id": "current-user-uuid",
      "receiver_id": "target-user-uuid",
      "content": "My new message content.",
      "created_at": "2023-10-27T15:05:00Z"
    }
    \`\`\`
*   **Notes:** Consider implementing WebSockets (e.g., Django Channels) for real-time messaging if that's a desired feature for instant updates.

### 4. Payment Integration

**Frontend Components:** `components/payment-form.jsx`, `app/payment-status/PaymentStatusClientPage.jsx`

*   **Payment Model:** Needs fields for `user` (FK), `amount`, `currency`, `status` (e.g., 'pending', 'success', 'failed'), `transaction_id` (from gateway), `created_at`, `updated_at`.

#### 4.1. Initiate Payment

*   **Endpoint:** `/api/payments/initiate/`
*   **Method:** `POST`
*   **Authentication:** Required (JWT)
*   **Request Body (JSON):**
    \`\`\`json
    {
      "payment_method": "credit_card", // or "paystack", "flutterwave"
      "amount": 60, // Example amount, should be tied to course/plan
      "currency": "USD",
      "card_details": { // Only if processing directly, otherwise gateway handles this
        "cardNumber": "...",
        "expiryDate": "MM/YY",
        "cvv": "..."
      }
      // Add any other details required by your chosen payment gateway
    }
    \`\`\`
*   **Expected Response (200 OK - JSON):**
    \`\`\`json
    {
      "message": "Payment initiation successful.",
      "transaction_id": "gateway-transaction-id",
      "redirect_url": "https://gateway.com/checkout/..." // If gateway requires redirect
    }
    \`\`\`
*   **Notes:** This endpoint should interact with your chosen payment gateway's API (e.g., Paystack, Flutterwave). It should create a payment record in your database with a 'pending' status.

#### 4.2. Payment Webhook/Callback (from Payment Gateway)

*   **Endpoint:** `/api/payments/webhook/` (or similar, configured in your payment gateway)
*   **Method:** `POST`
*   **Authentication:** Implement webhook signature verification for security.
*   **Request Body (JSON):** Varies greatly by payment gateway.
*   **Expected Response (200 OK):** Acknowledge receipt of webhook.
*   **Notes:** This endpoint is called by the payment gateway to notify your backend of the payment status (success, failure, etc.). Your backend should update the payment record's status and trigger user enrollment in courses upon successful payment.

#### 4.3. Get Payment Status (for Frontend Polling/Display)

*   **Endpoint:** `/api/payments/status/{transaction_id}/`
*   **Method:** `GET`
*   **Authentication:** Required (JWT)
*   **Expected Response (200 OK - JSON):**
    \`\`\`json
    {
      "transaction_id": "gateway-transaction-id",
      "status": "success", // or "failed", "pending"
      "message": "Payment processed successfully.",
      "enrollment_status": "enrolled" // Or "pending", "failed"
    }
    \`\`\`
*   **Notes:** The frontend will query this endpoint to display the final payment and enrollment status to the user.

### 5. Admin: User Monitoring

**Frontend Components:** `app/admin/AdminDashboardClientPage.jsx`

#### 5.1. Admin: List All Users

*   **Endpoint:** `/api/admin/users/`
*   **Method:** `GET`
*   **Authentication:** Required (Admin role)
*   **Expected Response (200 OK - JSON Array):**
    \`\`\`json
    [
      {
        "id": "user-uuid-1",
        "full_name": "Mock Student",
        "email": "student@example.com",
        "role": "user",
        "created_at": "2023-01-01T10:00:00Z",
        "courses_completed_count": 2 // Optional: Aggregate data
      },
      {
        "id": "user-uuid-2",
        "full_name": "Dr. Sarah Chen",
        "email": "sarah.chen@example.com",
        "role": "user", // Or 'tutor' if you introduce that role
        "created_at": "2023-02-01T11:00:00Z",
        "courses_completed_count": 0
      }
      // ... more users
    ]
    \`\`\`
*   **Notes:** The `courses_completed_count` is an example of aggregated data that might be useful for the admin dashboard.

---

## File Uploads (for Course Videos)

The frontend currently allows uploading a video file or providing a URL. If you choose to handle direct file uploads:

*   **Backend Storage:** Decide where to store video files (e.g., local file system, S3, Google Cloud Storage).
*   **Endpoint:** The `POST /api/admin/courses/` endpoint (2.1) should be able to accept `multipart/form-data` if files are directly uploaded.
*   **Processing:** Handle file validation (size, type) and secure storage. Store the URL to the stored video in the `video_url` field of the Course model.

---

This document provides a comprehensive overview of the backend work required. Please refer to Django and Django REST Framework documentation for implementation details. Feel free to reach out if you need clarification on any specific endpoint or functionality.
