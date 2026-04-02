#!/bin/bash
# LinkedIn Connection Scraper - VPS Deployment Script
# Run as root on a fresh Ubuntu VPS (Hostinger)

set -e

APP_USER="scraper"
APP_DIR="/opt/linkedin-scraper"
DOMAIN="${1:-}"  # Pass your domain as first argument, or leave empty for IP-only access

echo "=== Updating system ==="
apt update && apt upgrade -y

echo "=== Installing dependencies ==="
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# Playwright system dependencies
apt install -y libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 libwayland-client0

echo "=== Creating app user ==="
id -u $APP_USER &>/dev/null || useradd -r -m -s /bin/bash $APP_USER

echo "=== Setting up application ==="
mkdir -p $APP_DIR
cp -r . $APP_DIR/
chown -R $APP_USER:$APP_USER $APP_DIR

echo "=== Creating Python virtual environment ==="
su - $APP_USER -c "
    cd $APP_DIR
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    playwright install chromium
"

echo "=== Creating systemd service ==="
cat > /etc/systemd/system/linkedin-scraper.service << 'EOF'
[Unit]
Description=LinkedIn Connection Scraper (Streamlit)
After=network.target

[Service]
Type=simple
User=scraper
Group=scraper
WorkingDirectory=/opt/linkedin-scraper
Environment="PATH=/opt/linkedin-scraper/venv/bin:/usr/bin"
ExecStart=/opt/linkedin-scraper/venv/bin/streamlit run app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true \
    --browser.gatherUsageStats false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable linkedin-scraper
systemctl start linkedin-scraper

echo "=== Configuring Nginx ==="
if [ -n "$DOMAIN" ]; then
    cat > /etc/nginx/sites-available/linkedin-scraper << NGINXEOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
}
NGINXEOF
else
    cat > /etc/nginx/sites-available/linkedin-scraper << 'NGINXEOF'
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400;
    }
}
NGINXEOF
fi

ln -sf /etc/nginx/sites-available/linkedin-scraper /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

# SSL with Let's Encrypt (only if domain provided)
if [ -n "$DOMAIN" ]; then
    echo "=== Setting up SSL ==="
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsecure-key -m admin@$DOMAIN || \
        echo "SSL setup failed. You can run 'certbot --nginx -d $DOMAIN' manually later."
fi

echo ""
echo "=== Deployment complete! ==="
if [ -n "$DOMAIN" ]; then
    echo "App is live at: https://$DOMAIN"
else
    echo "App is live at: http://YOUR_VPS_IP"
fi
echo ""
echo "Useful commands:"
echo "  systemctl status linkedin-scraper   # check status"
echo "  systemctl restart linkedin-scraper  # restart app"
echo "  journalctl -u linkedin-scraper -f   # view logs"
