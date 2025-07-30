#!/bin/bash
# commands/start_dev_environment.sh - Complete development setup script

echo "🚀 Starting NCLEX Virtual School Development Environment"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if Django server is running
if ! lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null ; then
    echo -e "${YELLOW}⚠️  Django server not running. Starting...${NC}"
    
    # Start Django server in background
    python manage.py runserver 8000 &
    DJANGO_PID=$!
    echo -e "${GREEN}✅ Django server started (PID: $DJANGO_PID)${NC}"
    
    # Wait for server to start
    sleep 3
else
    echo -e "${GREEN}✅ Django server already running${NC}"
fi

# Check if ngrok is installed
if ! command -v ngrok &> /dev/null; then
    echo -e "${RED}❌ ngrok is not installed${NC}"
    echo "Please install ngrok first:"
    echo "  - macOS: brew install ngrok/ngrok/ngrok"
    echo "  - Windows: choco install ngrok"
    echo "  - Linux: sudo snap install ngrok"
    exit 1
fi

# Check if ngrok is already running
if pgrep -f "ngrok" > /dev/null; then
    echo -e "${YELLOW}⚠️  ngrok is already running. Stopping existing instance...${NC}"
    pkill -f ngrok
    sleep 2
fi

# Start ngrok
echo -e "${BLUE}🌐 Starting ngrok tunnel...${NC}"
ngrok http 8000 --log=stdout > ngrok.log 2>&1 &
NGROK_PID=$!

# Wait for ngrok to start
echo -e "${YELLOW}⏳ Waiting for ngrok to initialize...${NC}"
sleep 5

# Get ngrok URL
NGROK_URL=""
for i in {1..10}; do
    NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for tunnel in data['tunnels']:
        if tunnel['proto'] == 'https':
            print(tunnel['public_url'])
            break
except:
    pass
" 2>/dev/null)
    
    if [ ! -z "$NGROK_URL" ]; then
        break
    fi
    echo -e "${YELLOW}⏳ Waiting for ngrok URL... (attempt $i/10)${NC}"
    sleep 2
done

if [ -z "$NGROK_URL" ]; then
    echo -e "${RED}❌ Failed to get ngrok URL${NC}"
    echo "Please check ngrok.log for errors"
    exit 1
fi

echo -e "${GREEN}✅ ngrok tunnel established${NC}"
echo -e "${BLUE}🌐 Public URL: $NGROK_URL${NC}"

# Update webhook URLs
echo -e "${BLUE}🔧 Updating webhook URLs...${NC}"
python manage.py update_webhook_urls --ngrok-url="$NGROK_URL"

# Test webhook endpoint
echo -e "${BLUE}🧪 Testing webhook endpoint...${NC}"
WEBHOOK_TEST=$(curl -s "$NGROK_URL/api/payments/webhooks/test/" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data.get('status') == 'success':
        print('SUCCESS')
    else:
        print('FAILED')
except:
    print('ERROR')
")

if [ "$WEBHOOK_TEST" = "SUCCESS" ]; then
    echo -e "${GREEN}✅ Webhook endpoint is working${NC}"
else
    echo -e "${RED}❌ Webhook endpoint test failed${NC}"
fi

# Display information
echo ""
echo "=================================================="
echo -e "${GREEN}🎉 Development Environment Ready!${NC}"
echo "=================================================="
echo -e "${BLUE}📍 Local Django:${NC} http://localhost:8000"
echo -e "${BLUE}🌐 Public URL:${NC} $NGROK_URL"
echo -e "${BLUE}🔍 ngrok Web UI:${NC} http://localhost:4040"
echo -e "${BLUE}📊 Webhook Status:${NC} $NGROK_URL/api/payments/webhooks/status/"
echo ""
echo -e "${YELLOW}📋 Paystack Configuration:${NC}"
echo -e "   Test Webhook URL: ${BLUE}$NGROK_URL/api/payments/webhooks/paystack/${NC}"
echo -e "   Test Callback URL: ${BLUE}$NGROK_URL/api/payments/callback/${NC}"
echo ""
echo -e "${YELLOW}⚡ Quick Commands:${NC}"
echo "   Test webhook: curl $NGROK_URL/api/payments/webhooks/test/"
echo "   View logs: tail -f ngrok.log"
echo "   Stop all: pkill -f 'ngrok|python manage.py runserver'"
echo ""
echo -e "${GREEN}🎯 Next Steps:${NC}"
echo "1. Copy the webhook URL above to your Paystack dashboard"
echo "2. Make a test payment to verify everything works"
echo "3. Monitor requests in ngrok web UI (http://localhost:4040)"

# Save URLs for reference
cat > .dev_urls.txt << EOF
# Development URLs - Generated $(date)
Django Local: http://localhost:8000
ngrok Public: $NGROK_URL
ngrok Web UI: http://localhost:4040

# Paystack Configuration
Test Webhook URL: $NGROK_URL/api/payments/webhooks/paystack/
Test Callback URL: $NGROK_URL/api/payments/callback/

# Useful Endpoints
Webhook Test: $NGROK_URL/api/payments/webhooks/test/
Webhook Status: $NGROK_URL/api/payments/webhooks/status/
Admin Panel: $NGROK_URL/admin/
EOF

echo -e "${GREEN}💾 URLs saved to .dev_urls.txt${NC}"

# Keep script running and show real-time ngrok logs
echo ""
echo -e "${YELLOW}📝 Showing ngrok logs (Ctrl+C to stop):${NC}"
echo "=================================================="
tail -f ngrok.log