# Google Maps Scraper

Google Maps'ten işletme verilerini çeken Flask tabanlı web uygulaması.

## 🚀 Özellikler

- Google Maps'ten işletme bilgilerini çekme
- Telefon numarası analizi (Cep/Sabit ayrımı)
- WhatsApp link oluşturma
- Excel ve CSV export
- Responsive web arayüzü
- Production-ready (Gunicorn uyumlu)

## 📋 Gereksinimler

- Python 3.8+
- Chrome tarayıcı
- ChromeDriver

## 🛠️ Yerel Kurulum

```bash
# Repoyu klonla
git clone https://github.com/senmery/webscraping.git
cd webscraping

# Sanal ortam oluştur
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# veya
.\venv\Scripts\Activate   # Windows

# Bağımlılıkları yükle
pip install -r requirements.txt

# Uygulamayı çalıştır
cd webscraping
python web_app.py
```

Tarayıcıdan `http://localhost:5000` adresine gidin.

## 🌐 Sunucu Kurulumu (Ubuntu/Debian)

### 1. Sistem Paketleri
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install git python3 python3-venv python3-pip nginx chromium-chromedriver -y
```

### 2. Projeyi İndir
```bash
cd /var/www
git clone https://github.com/senmery/webscraping.git
cd webscraping
```

### 3. Python Ortamı
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Environment Dosyası
```bash
cp .env.example .env
nano .env
# FLASK_SECRET_KEY değerini güncelleyin
```

### 5. Gunicorn ile Test
```bash
cd webscraping
gunicorn --workers 3 --bind 0.0.0.0:8000 web_app:application
```

### 6. Systemd Servisi
```bash
sudo nano /etc/systemd/system/webscraping.service
```

İçeriği:
```ini
[Unit]
Description=Webscraping Flask App
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/webscraping/webscraping
Environment="PATH=/var/www/webscraping/venv/bin"
ExecStart=/var/www/webscraping/venv/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 web_app:application
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable webscraping
sudo systemctl start webscraping
sudo systemctl status webscraping
```

### 7. Nginx Yapılandırması
```bash
sudo nano /etc/nginx/sites-available/webscraping
```

İçeriği:
```nginx
server {
    listen 80;
    server_name SUNUCU_IP;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/webscraping /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 8. Firewall
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 📁 Proje Yapısı

```
webscraping/
├── .env.example          # Örnek environment dosyası
├── .gitignore
├── README.md
├── requirements.txt
└── webscraping/
    ├── web_app.py        # Ana Flask uygulaması
    ├── app.py            # Selenium scraper (opsiyonel)
    └── templates/
        └── index.html
```

## 🔧 API Endpoints

| Endpoint | Method | Açıklama |
|----------|--------|----------|
| `/` | GET | Ana sayfa (Web UI) |
| `/api` | GET | API durumu |
| `/search` | POST | Arama başlat |
| `/status` | GET | Scraping durumu |
| `/export/excel` | GET | Excel indir |
| `/export/csv` | GET | CSV indir |

## 📝 Lisans

MIT License

## 👤 Geliştirici

[@senmery](https://github.com/senmery)
