"""
Google Maps Scraper - Production Ready Flask App
Sunucu için optimize edilmiş web uygulaması
"""

import os
import re
import json
import time
import threading
from io import BytesIO, StringIO
import csv

from flask import Flask, jsonify, request, render_template_string, send_file, Response

# .env desteği (isteğe bağlı)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Selenium Importları
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Excel Importları
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

# Flask Uygulaması
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'google_maps_scraper_2026')
application = app  # WSGI sunucuları (Gunicorn) için alias

# --- GLOBAL DEĞİŞKENLER ---
scraping_status = {
    'is_running': False,
    'progress': 0,
    'message': 'Hazır',
    'results': [],
    'total_found': 0,
    'location': '',
    'profession': ''
}


# --- YARDIMCI FONKSİYONLAR ---

def get_chrome_driver():
    """
    Chrome WebDriver oluşturur.
    Sunucu (Linux) ve yerel (Windows) ortamlar için uyumludur.
    """
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--lang=tr-TR")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    
    # Linux sunucu için ChromeDriver yolu
    linux_chromedriver_path = '/usr/bin/chromedriver'
    
    if os.path.exists(linux_chromedriver_path):
        # Linux sunucu
        service = Service(linux_chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        # Windows veya webdriver-manager kullan
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception:
            # Sistem PATH'inden Chrome kullan
            driver = webdriver.Chrome(options=chrome_options)
    
    return driver


def analyze_phone_number(phone):
    """Telefon numarasını analiz eder ve WhatsApp linki oluşturur."""
    if not phone:
        return {'is_mobile': False, 'formatted': '', 'whatsapp_link': '', 'display': ''}
    
    cleaned = re.sub(r'[^\d]', '', phone)
    is_mobile = False
    whatsapp_number = ''
    
    # Türkiye numarası kontrolü
    if cleaned.startswith('90'):
        if len(cleaned) >= 12 and cleaned[2] == '5':
            is_mobile = True
            whatsapp_number = cleaned[:12]
    elif cleaned.startswith('05'):
        if len(cleaned) >= 11:
            is_mobile = True
            whatsapp_number = '9' + cleaned[:11]
    elif cleaned.startswith('5'):
        if len(cleaned) >= 10:
            is_mobile = True
            whatsapp_number = '90' + cleaned[:10]
    
    whatsapp_link = f"https://wa.me/{whatsapp_number}" if is_mobile and whatsapp_number else ''
    
    return {
        'is_mobile': is_mobile,
        'formatted': cleaned,
        'whatsapp_link': whatsapp_link,
        'display': phone
    }


def extract_detailed_data(driver, index, link):
    """Tekil işletme detaylarını çeker."""
    result = {
        'sira': index,
        'isim': '',
        'puan': '',
        'degerlendirme_sayisi': '',
        'kategori': '',
        'adres': '',
        'telefon': '',
        'telefon_bilgi': {},
        'website': '',
        'calisma_saatleri': {},
        'calisma_durumu': '',
        'plus_code': '',
        'link': link
    }
    
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1, div.fontHeadlineLarge"))
        )
        time.sleep(1)
        
        # İsim
        try:
            name_elem = driver.find_element(By.TAG_NAME, "h1")
            result['isim'] = name_elem.text.strip()
        except Exception:
            pass

        # Puan
        try:
            puan_elem = driver.find_element(By.CSS_SELECTOR, "div.F7nice span[aria-hidden='true']")
            result['puan'] = puan_elem.text.strip()
        except Exception:
            pass

        # Değerlendirme sayısı
        try:
            yorum_elem = driver.find_element(By.CSS_SELECTOR, "div.F7nice span[aria-label*='yorum']")
            text = yorum_elem.get_attribute("aria-label")
            match = re.search(r'([\d.,]+)', text) if text else None
            result['degerlendirme_sayisi'] = match.group(1) if match else ''
        except Exception:
            pass

        # Adres
        try:
            addr_btn = driver.find_element(By.CSS_SELECTOR, "button[data-item-id='address']")
            label = addr_btn.get_attribute("aria-label")
            result['adres'] = label.replace("Adres:", "").strip() if label else ''
        except Exception:
            pass

        # Telefon
        try:
            phone_btn = driver.find_element(By.CSS_SELECTOR, "button[data-item-id^='phone']")
            label = phone_btn.get_attribute("aria-label")
            raw_phone = label.replace("Telefon:", "").strip() if label else ''
            result['telefon'] = raw_phone
            result['telefon_bilgi'] = analyze_phone_number(raw_phone)
        except Exception:
            pass

        # Website
        try:
            web_btn = driver.find_element(By.CSS_SELECTOR, "a[data-item-id='authority']")
            result['website'] = web_btn.get_attribute("href")
        except Exception:
            pass

        return result

    except Exception as e:
        print(f"Veri çekme hatası (Index {index}): {e}")
        return result


def scrape_task(location, profession, max_results):
    """Arka planda çalışacak ana scraping fonksiyonu."""
    global scraping_status
    
    scraping_status['is_running'] = True
    scraping_status['progress'] = 0
    scraping_status['message'] = 'Tarayıcı hazırlanıyor...'
    scraping_status['results'] = []
    
    driver = None
    try:
        driver = get_chrome_driver()
        scraping_status['message'] = 'Google Maps açılıyor...'
        
        search_query = f"{location} {profession}"
        url = f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}"
        
        driver.get(url)
        scraping_status['progress'] = 10
        
        # Çerez onayı (varsa geç)
        try:
            WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Kabul')]"))
            ).click()
        except Exception:
            pass
            
        scraping_status['message'] = 'Liste yükleniyor...'
        
        # Listeyi bekle
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed']"))
            )
        except Exception:
            scraping_status['message'] = 'Sonuç bulunamadı.'
            scraping_status['is_running'] = False
            return

        scrollable_div = driver.find_element(By.CSS_SELECTOR, "div[role='feed']")
        place_links = []
        
        # Link toplama döngüsü
        scroll_attempts = 0
        max_scroll_attempts = 30
        
        while len(place_links) < max_results and scroll_attempts < max_scroll_attempts:
            elements = driver.find_elements(By.CSS_SELECTOR, "a.hfpxzc")
            for elem in elements:
                href = elem.get_attribute("href")
                if href and href not in place_links:
                    place_links.append(href)
            
            scraping_status['message'] = f"{len(place_links)} işletme bulundu..."
            
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_div)
            time.sleep(2)
            
            if "sonuna" in driver.page_source or len(place_links) >= max_results:
                break
            
            scroll_attempts += 1
        
        place_links = place_links[:max_results]
        
        # Detayları çekme döngüsü
        results = []
        total = len(place_links)
        
        for i, link in enumerate(place_links):
            if not scraping_status['is_running']:
                break
                
            scraping_status['message'] = f"Veri çekiliyor: {i+1}/{total}"
            scraping_status['progress'] = 20 + int((i / total) * 80)
            
            driver.get(link)
            data = extract_detailed_data(driver, i+1, link)
            
            if data['isim']:
                results.append(data)
                scraping_status['results'] = results.copy()
                
        scraping_status['message'] = 'Tamamlandı!'
        scraping_status['progress'] = 100
        scraping_status['results'] = results
        scraping_status['total_found'] = len(results)
        
        # Sonuçları JSON dosyasına kaydet
        save_results(results, location, profession)

    except Exception as e:
        scraping_status['message'] = f"Hata oluştu: {str(e)}"
    finally:
        scraping_status['is_running'] = False
        if driver:
            driver.quit()


def save_results(results, location, profession):
    """Sonuçları JSON dosyasına kaydet."""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        filename = f"sonuclar_{location}_{profession}.json".replace(' ', '_').lower()
        filepath = os.path.join(base_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        # Genel sonuçlar dosyası
        general_filepath = os.path.join(base_dir, 'son_arama.json')
        with open(general_filepath, 'w', encoding='utf-8') as f:
            json.dump({
                'lokasyon': location,
                'meslek': profession,
                'sonuc_sayisi': len(results),
                'sonuclar': results
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Sonuçlar kaydedilirken hata: {e}")


# --- HTML TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Google Maps Scraper</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
</head>
<body class="bg-light">
    <div class="container mt-5">
        <div class="card shadow">
            <div class="card-header bg-primary text-white">
                <h3>🗺️ Google Maps Scraper</h3>
            </div>
            <div class="card-body">
                <form id="searchForm">
                    <div class="row g-3">
                        <div class="col-md-5">
                            <input type="text" class="form-control" name="location" placeholder="Konum (Örn: Kadıköy)" required>
                        </div>
                        <div class="col-md-5">
                            <input type="text" class="form-control" name="profession" placeholder="Meslek (Örn: Berber)" required>
                        </div>
                        <div class="col-md-2">
                            <input type="number" class="form-control" name="max_results" value="10" min="1" max="100">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success mt-3 w-100">🚀 Scraping Başlat</button>
                </form>

                <div id="statusArea" class="mt-4" style="display:none;">
                    <h5>Durum: <span id="statusText">Bekleniyor...</span></h5>
                    <div class="progress">
                        <div id="progressBar" class="progress-bar progress-bar-striped progress-bar-animated" style="width: 0%"></div>
                    </div>
                    <div class="mt-3">
                        <a href="/export/excel" id="dlExcel" class="btn btn-primary disabled">📊 Excel İndir</a>
                        <a href="/export/csv" id="dlCsv" class="btn btn-secondary disabled">📄 CSV İndir</a>
                    </div>
                    <div class="mt-3 alert alert-info">
                        Bulunan İşletme Sayısı: <strong><span id="foundCount">0</span></strong>
                    </div>
                </div>
            </div>
            <div class="card-footer text-muted text-center">
                Google Maps Scraper &copy; 2026
            </div>
        </div>
    </div>

    <script>
        $(document).ready(function(){
            $('#searchForm').on('submit', function(e){
                e.preventDefault();
                $('#dlExcel').addClass('disabled');
                $('#dlCsv').addClass('disabled');
                $.post('/search', $(this).serialize(), function(data){
                    $('#statusArea').show();
                    checkStatus();
                }).fail(function(xhr){
                    alert(xhr.responseJSON ? xhr.responseJSON.error : 'Bir hata oluştu');
                });
            });

            function checkStatus(){
                $.get('/status', function(data){
                    $('#statusText').text(data.message);
                    $('#progressBar').css('width', data.progress + '%');
                    $('#foundCount').text(data.total_found);
                    
                    if(data.is_running){
                        setTimeout(checkStatus, 2000);
                    } else if(data.progress == 100) {
                        $('#dlExcel').removeClass('disabled');
                        $('#dlCsv').removeClass('disabled');
                    }
                });
            }
        });
    </script>
</body>
</html>
"""


# --- FLASK ROUTE'LARI ---

@app.route('/')
def home():
    """Ana sayfa."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api')
def api_home():
    """API durumu."""
    return jsonify({
        "status": "ok",
        "message": "Google Maps Scraper API çalışıyor 👑",
        "endpoints": ["/", "/search", "/status", "/export/excel", "/export/csv"]
    })


@app.route('/search', methods=['POST'])
def search():
    """Arama başlat."""
    global scraping_status
    
    if scraping_status['is_running']:
        return jsonify({'error': 'Şu anda zaten bir işlem devam ediyor.'}), 400
    
    location = request.form.get('location', '').strip()
    profession = request.form.get('profession', '').strip()
    max_results = int(request.form.get('max_results', 20))
    
    if not location or not profession:
        return jsonify({'error': 'Lokasyon ve meslek alanları zorunludur!'}), 400
    
    scraping_status['location'] = location
    scraping_status['profession'] = profession
    
    thread = threading.Thread(target=scrape_task, args=(location, profession, max_results))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'İşlem başlatıldı'})


@app.route('/status')
def status():
    """Scraping durumunu döndür."""
    return jsonify(scraping_status)


@app.route('/export/<fmt>')
def export_data(fmt):
    """Excel veya CSV olarak dışa aktar."""
    global scraping_status
    results = scraping_status.get('results', [])
    
    if not results:
        return jsonify({"error": "İndirilecek veri yok"}), 404
        
    location = scraping_status.get('location', 'bilinmiyor')
    profession = scraping_status.get('profession', 'bilinmiyor')
    filename_base = f"sonuclar_{location}_{profession}".replace(' ', '_')
    
    if fmt == 'excel':
        if not EXCEL_AVAILABLE:
            return jsonify({"error": "openpyxl kütüphanesi yüklü değil. CSV olarak indirin."}), 400
            
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sonuclar"
        
        headers = ['Sıra', 'İşletme Adı', 'Puan', 'Yorum Sayısı', 'Adres', 'Telefon', 'Tip', 'WhatsApp', 'Website', 'Link']
        ws.append(headers)
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            
        for item in results:
            tel_bilgi = item.get('telefon_bilgi', {})
            row = [
                item.get('sira'),
                item.get('isim'),
                item.get('puan'),
                item.get('degerlendirme_sayisi'),
                item.get('adres'),
                item.get('telefon'),
                'Cep' if tel_bilgi.get('is_mobile') else 'Sabit',
                tel_bilgi.get('whatsapp_link', ''),
                item.get('website', ''),
                item.get('link', '')
            ]
            ws.append(row)
        
        # Sütun genişlikleri
        column_widths = [6, 35, 8, 12, 40, 18, 8, 30, 35, 50]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[chr(64 + i)].width = width
            
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        return send_file(
            output, 
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            download_name=f"{filename_base}.xlsx", 
            as_attachment=True
        )
        
    elif fmt == 'csv':
        output = StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['Sıra', 'İşletme Adı', 'Puan', 'Yorum Sayısı', 'Adres', 'Telefon', 'Tip', 'WhatsApp', 'Website', 'Link'])
        
        for item in results:
            tel_bilgi = item.get('telefon_bilgi', {})
            writer.writerow([
                item.get('sira'),
                item.get('isim'),
                item.get('puan'),
                item.get('degerlendirme_sayisi'),
                item.get('adres'),
                item.get('telefon'),
                'Cep' if tel_bilgi.get('is_mobile') else 'Sabit',
                tel_bilgi.get('whatsapp_link', ''),
                item.get('website', ''),
                item.get('link', '')
            ])
            
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename_base}.csv"}
        )
    
    return jsonify({"error": "Geçersiz format"}), 400


# --- UYGULAMA BAŞLATMA ---
if __name__ == '__main__':
    # Production için debug=False
    debug_mode = os.getenv('FLASK_ENV', 'production') != 'production'
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=debug_mode, threaded=True)
