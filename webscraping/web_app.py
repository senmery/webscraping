import os
import re
import json
import time
import threading
from io import BytesIO, StringIO
import csv

from flask import Flask, jsonify, request, render_template_string, send_file, Response
from dotenv import load_dotenv

# Selenium Importları
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Excel Importları
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# .env yükle
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'google_maps_scraper_2026')

# --- GLOBAL DEĞİŞKENLER ---
# İşlem durumunu takip etmek için global sözlük
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
        # Başlık bekle
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1, div.fontHeadlineLarge"))
        )
        time.sleep(1) # Kısa bekleme
        
        # İsim
        try:
            name_elem = driver.find_element(By.TAG_NAME, "h1")
            result['isim'] = name_elem.text.strip()
        except:
            pass

        # Puan ve Değerlendirme
        try:
            puan_elem = driver.find_element(By.CSS_SELECTOR, "div.F7nice span[aria-hidden='true']")
            result['puan'] = puan_elem.text.strip()
        except:
            pass

        try:
            yorum_elem = driver.find_element(By.CSS_SELECTOR, "div.F7nice span[aria-label*='yorum']")
            text = yorum_elem.get_attribute("aria-label")
            result['degerlendirme_sayisi'] = re.search(r'([\d.,]+)', text).group(1) if text else ''
        except:
            pass

        # Adres (Buton aria-label üzerinden)
        try:
            addr_btn = driver.find_element(By.CSS_SELECTOR, "button[data-item-id='address']")
            result['adres'] = addr_btn.get_attribute("aria-label").replace("Adres:", "").strip()
        except:
            pass

        # Telefon
        try:
            phone_btn = driver.find_element(By.CSS_SELECTOR, "button[data-item-id^='phone']")
            raw_phone = phone_btn.get_attribute("aria-label").replace("Telefon:", "").strip()
            result['telefon'] = raw_phone
            result['telefon_bilgi'] = analyze_phone_number(raw_phone)
        except:
            pass

        # Website
        try:
            web_btn = driver.find_element(By.CSS_SELECTOR, "a[data-item-id='authority']")
            result['website'] = web_btn.get_attribute("href")
        except:
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
        # Chrome Ayarları
        chrome_options = Options()
        chrome_options.add_argument("--headless=new") # Arka planda çalışması için
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--lang=tr-TR")
        
        # Driver Manager ile başlatma
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
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
        except:
            pass
            
        scraping_status['message'] = 'Liste yükleniyor...'
        
        # Listeyi bekle ve scroll et
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed']"))
            )
        except:
            scraping_status['message'] = 'Sonuç bulunamadı.'
            scraping_status['is_running'] = False
            return

        scrollable_div = driver.find_element(By.CSS_SELECTOR, "div[role='feed']")
        place_links = []
        
        # Link toplama döngüsü
        while len(place_links) < max_results:
            # Mevcut linkleri al (a.hfpxzc Google Maps işletme linki sınıfıdır)
            elements = driver.find_elements(By.CSS_SELECTOR, "a.hfpxzc")
            for elem in elements:
                href = elem.get_attribute("href")
                if href and href not in place_links:
                    place_links.append(href)
            
            scraping_status['message'] = f"{len(place_links)} işletme bulundu..."
            
            # Scroll aşağı
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_div)
            time.sleep(2)
            
            # Eğer sayfa sonuna geldiyse veya yeterli sayıya ulaştıysa çık
            if "sonuna" in driver.page_source or len(place_links) >= max_results:
                break
        
        # Link sayısını limitle
        place_links = place_links[:max_results]
        
        # Detayları çekme döngüsü
        results = []
        total = len(place_links)
        
        for i, link in enumerate(place_links):
            if not scraping_status['is_running']: # Durdurma kontrolü
                break
                
            scraping_status['message'] = f"Veri çekiliyor: {i+1}/{total}"
            scraping_status['progress'] = 20 + int((i / total) * 80)
            
            driver.get(link)
            data = extract_detailed_data(driver, i+1, link)
            
            if data['isim']:
                results.append(data)
                scraping_status['results'] = results # Canlı güncelleme
                
        scraping_status['message'] = 'Tamamlandı!'
        scraping_status['progress'] = 100
        scraping_status['results'] = results
        scraping_status['total_found'] = len(results)

    except Exception as e:
        scraping_status['message'] = f"Hata oluştu: {str(e)}"
    finally:
        scraping_status['is_running'] = False
        if driver:
            driver.quit()

# --- FLASK ROUTE'LARI ---

# Basit bir HTML arayüzü (template dosyası oluşturmanıza gerek kalmasın diye)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Google Maps Scraper</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
</head>
<body class="bg-light">
    <div class="container mt-5">
        <div class="card shadow">
            <div class="card-header bg-primary text-white">
                <h3>🗺️ Google Maps Scraper 2026</h3>
            </div>
            <div class="card-body">
                <form id="searchForm">
                    <div class="row">
                        <div class="col-md-5">
                            <input type="text" class="form-control" name="location" placeholder="Konum (Örn: Kadıköy)" required>
                        </div>
                        <div class="col-md-5">
                            <input type="text" class="form-control" name="profession" placeholder="Meslek (Örn: Diş Hekimi)" required>
                        </div>
                        <div class="col-md-2">
                            <input type="number" class="form-control" name="max_results" value="10" min="1" max="100">
                        </div>
                    </div>
                    <button type="submit" class="btn btn-success mt-3 w-100">Scraping Başlat</button>
                </form>

                <div id="statusArea" class="mt-4" style="display:none;">
                    <h5>Durum: <span id="statusText">Bekleniyor...</span></h5>
                    <div class="progress">
                        <div id="progressBar" class="progress-bar progress-bar-striped progress-bar-animated" style="width: 0%"></div>
                    </div>
                    <div class="mt-3">
                        <a href="/export/excel" id="dlExcel" class="btn btn-primary disabled">Excel İndir</a>
                        <a href="/export/csv" id="dlCsv" class="btn btn-secondary disabled">CSV İndir</a>
                    </div>
                    <div class="mt-3 alert alert-info">
                        Bulunan İşletme Sayısı: <span id="foundCount">0</span>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        $(document).ready(function(){
            $('#searchForm').on('submit', function(e){
                e.preventDefault();
                $.post('/search', $(this).serialize(), function(data){
                    $('#statusArea').show();
                    checkStatus();
                }).fail(function(xhr){
                    alert(xhr.responseJSON.error);
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

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/search', methods=['POST'])
def search():
    global scraping_status
    
    if scraping_status['is_running']:
        return jsonify({'error': 'Şu anda zaten bir işlem devam ediyor.'}), 400
    
    location = request.form.get('location')
    profession = request.form.get('profession')
    max_results = int(request.form.get('max_results', 20))
    
    scraping_status['location'] = location
    scraping_status['profession'] = profession
    
    # Arka planda thread başlat
    thread = threading.Thread(target=scrape_task, args=(location, profession, max_results))
    thread.daemon = True
    thread.start()
    
    return jsonify({'success': True, 'message': 'İşlem başlatıldı'})

@app.route('/status')
def status():
    return jsonify(scraping_status)

@app.route('/export/<fmt>')
def export_data(fmt):
    global scraping_status
    results = scraping_status.get('results', [])
    
    if not results:
        return "İndirilecek veri yok", 404
        
    filename_base = f"sonuclar_{scraping_status['location']}_{scraping_status['profession']}"
    
    if fmt == 'excel':
        # Excel Oluşturma
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sonuclar"
        
        headers = ['Sıra', 'İşletme Adı', 'Puan', 'Yorum Sayısı', 'Adres', 'Telefon', 'Tip', 'WhatsApp', 'Website']
        ws.append(headers)
        
        # Stil tanımları
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        
        # Başlık stili uygula
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
                tel_bilgi.get('whatsapp_link'),
                item.get('website')
            ]
            ws.append(row)
            
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        return send_file(output, download_name=f"{filename_base}.xlsx", as_attachment=True)
        
    elif fmt == 'csv':
        # CSV Oluşturma
        output = StringIO()
        writer = csv.writer(output, delimiter=';') # Excel için noktalı virgül daha iyidir
        writer.writerow(['Sıra', 'İşletme Adı', 'Puan', 'Yorum Sayısı', 'Adres', 'Telefon', 'WhatsApp', 'Website'])
        
        for item in results:
             writer.writerow([
                item.get('sira'),
                item.get('isim'),
                item.get('puan'),
                item.get('degerlendirme_sayisi'),
                item.get('adres'),
                item.get('telefon'),
                item.get('telefon_bilgi', {}).get('whatsapp_link', ''),
                item.get('website')
            ])
            
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename_base}.csv"}
        )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)