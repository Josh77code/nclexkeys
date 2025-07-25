# NCLEX Virtual School - Django Backend API

A comprehensive backend API for the NCLEX Virtual School platform, built with Django and Django REST Framework. This API powers a Next.js frontend and provides secure authentication, course management, messaging, payments, and administrative features.

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Environment Configuration](#environment-configuration)
- [API Documentation](#api-documentation)
- [Authentication](#authentication)
- [Testing](#testing)
- [Contributing](#contributing)
- [License](#license)

## Features

### 🔐 Authentication & Security
- **JWT Authentication**: Access and refresh token system
- **Email Verification**: Secure account activation
- **Password Management**: Reset functionality via email
- **Two-Factor Authentication**: TOTP-based 2FA
- **Security Features**: Login alerts, device detection, account lockout
- **Account Management**: Immediate or scheduled deletion

### 👤 User Management
- **Profile Management**: View and update user profiles
- **Session Tracking**: Device info and timestamp tracking
- **Account Control**: Deletion scheduling and cancellation

### 📚 Course Management
- **Admin Features**: Full CRUD operations for courses
- **Student Features**: Browse available courses and track progress
- **Progress Tracking**: Course completion monitoring
- **Media Support**: Video uploads and URL management

### 💬 Real-time Messaging
- **Chat System**: Direct user-to-user messaging
- **Conversation Management**: Active chat tracking
- **Message History**: Timestamped message records

### 💳 Payment Integration
- **Payment Processing**: Secure payment initiation
- **Webhook Support**: Automated callback processing
- **Enrollment Tracking**: Payment and course enrollment status

### 📧 Email System
- **Template Engine**: HTML email templates
- **Media Integration**: Cloudinary-hosted assets
- **Timezone Support**: Timezone-aware timestamps with pytz

## Project Structure

```
nclex_virtual_school/
├── auth/                    # Authentication & JWT management
├── users/                   # User profiles & session management
├── courses/                 # Course CRUD & progress tracking
├── messaging/               # User messaging system
├── payments/                # Payment gateway integration
├── admin/                   # Administrative dashboard
├── templates/emails/        # Email template collection
├── config/                  # Django settings & configuration
├── requirements.txt         # Python dependencies
├── manage.py               # Django management script
└── README.md               # This file
```

## Quick Start

### Prerequisites
- Python 3.8+
- PostgreSQL
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/war-riz/nclex_virtual_school.git
   cd nclex_virtual_school
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   
   # On macOS/Linux:
   source venv/bin/activate
   
   # On Windows:
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration (see Environment Configuration section)
   ```

5. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser (optional)**
   ```bash
   python manage.py createsuperuser
   ```

7. **Start the development server**
   ```bash
   python manage.py runserver
   ```

The API will be available at `http://localhost:8000/`

## Environment Configuration

Create a `.env` file in the project root with the following variables:

```env
# Django Settings
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgres://username:password@localhost:5432/database_name

# Frontend Configuration
FRONTEND_URL=http://localhost:3000

# Cloudinary Configuration
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret

# Email Configuration
DEFAULT_FROM_EMAIL=NCLEX Virtual School <noreply@nclexschool.com>
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password

# Payment Gateway (Optional)
PAYSTACK_SECRET_KEY=your-paystack-secret-key
FLUTTERWAVE_SECRET_KEY=your-flutterwave-secret-key
```

## API Documentation

### Authentication Endpoints
- `POST /api/auth/register/` - User registration
- `POST /api/auth/login/` - User login
- `POST /api/auth/logout/` - User logout
- `POST /api/auth/refresh/` - Refresh access token
- `POST /api/auth/verify-email/` - Email verification
- `POST /api/auth/password-reset/` - Password reset request
- `POST /api/auth/password-reset-confirm/` - Password reset confirmation

### User Management
- `GET /api/users/profile/` - Get user profile
- `PUT /api/users/profile/` - Update user profile
- `GET /api/users/sessions/` - List active sessions
- `DELETE /api/users/account/` - Delete account

### Course Management
- `GET /api/courses/` - List all courses
- `GET /api/courses/{id}/` - Get course details
- `POST /api/courses/` - Create course (admin)
- `PUT /api/courses/{id}/` - Update course (admin)
- `DELETE /api/courses/{id}/` - Delete course (admin)

### Messaging
- `GET /api/messaging/conversations/` - List conversations
- `POST /api/messaging/send/` - Send message
- `GET /api/messaging/messages/{conversation_id}/` - Get messages

### Payments
- `POST /api/payments/initiate/` - Initiate payment
- `POST /api/payments/webhook/` - Payment webhook
- `GET /api/payments/status/{transaction_id}/` - Payment status

## Authentication

The API uses JWT (JSON Web Tokens) for authentication. Here's how to authenticate requests:

### Frontend Integration Example

```javascript
// Login and store tokens
const login = async (email, password) => {
  try {
    const response = await fetch('/api/auth/login/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json();
    
    if (response.ok) {
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      return data;
    }
    
    throw new Error(data.message || 'Login failed');
  } catch (error) {
    console.error('Login error:', error);
    throw error;
  }
};

// Make authenticated requests
const makeAuthenticatedRequest = async (url, options = {}) => {
  const token = localStorage.getItem('access_token');
  
  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  });

  if (response.status === 401) {
    // Token expired, refresh it
    await refreshToken();
    return makeAuthenticatedRequest(url, options);
  }

  return response;
};
```

## Testing

Run the test suite:

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test auth
python manage.py test users
python manage.py test courses

# Run with coverage
pip install coverage
coverage run --source='.' manage.py test
coverage report
```

## Development

### Code Style
This project follows PEP 8 guidelines. Use `flake8` and `black` for code formatting:

```bash
pip install flake8 black
black .
flake8 .
```

### Database Management
```bash
# Create new migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Reset database (development only)
python manage.py flush
```

## Roadmap

### Upcoming Features
- [ ] WebSocket support for real-time messaging (Django Channels)
- [ ] User analytics dashboard for administrators
- [ ] Lesson-level progress tracking
- [ ] Push notifications (email and PWA)
- [ ] API rate limiting
- [ ] Comprehensive API documentation with Swagger/OpenAPI

### Performance Improvements
- [ ] Database query optimization
- [ ] Caching implementation (Redis)
- [ ] File upload optimization
- [ ] API response compression

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

Please ensure your code follows the project's coding standards and includes appropriate tests.

## Support

For questions or support, please contact:
- **Developer**: [war_riz](https://github.com/war-riz)
- **Issues**: [GitHub Issues](https://github.com/war-riz/nclex_virtual_school/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

**NCLEX Virtual School** - Empowering nursing students with comprehensive digital learning solutions.