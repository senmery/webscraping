
# Selenium ve ChromeDriver ayarları (Ubuntu uyumlu)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import json
import csv

def scrape_google_maps(url):
    """
    Google Maps'ten berber verilerini çeker.
    Ubuntu sunucuda Chrome ve ChromeDriver'ın sistemde kurulu olduğu varsayılır.
    Headless mod ve stabil çalışma için ek argümanlar eklenmiştir.
    """
    # Chrome ayarları
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--lang=tr-TR")
    # Headless ve sunucu uyumlu argümanlar
    chrome_options.add_argument('--headless=new')  # Headless mod (Selenium 4+)
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')

    # ChromeDriver'ın sistemde kurulu olduğu yol
    chrome_service = Service('/usr/local/bin/chromedriver')

    # Webdriver başlatılır
    driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

    try:
        print("Google Maps açılıyor...")
        driver.get(url)

        # Sayfanın yüklenmesini bekle
        time.sleep(5)

        # Çerez popup'ını kabul et (varsa)
        try:
            accept_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(., 'Kabul')]"))
            )
            accept_button.click()
            time.sleep(2)
        except Exception:
            print("Çerez popup'ı bulunamadı veya zaten kabul edilmiş.")

        # Sonuçların yüklenmesini bekle
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='feed']"))
        )
        
        # Scroll yaparak tüm sonuçları yükle
        print("Sonuçlar yükleniyor...")
        scrollable_div = driver.find_element(By.CSS_SELECTOR, "div[role='feed']")
        
        last_height = 0
        scroll_count = 0
        max_scrolls = 20  # Maksimum scroll sayısı
        
        while scroll_count < max_scrolls:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_div)
            time.sleep(2)
            
            new_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_div)
            if new_height == last_height:
                # Listenin sonuna ulaşıldı mı kontrol et
                try:
                    end_message = driver.find_element(By.XPATH, "//*[contains(text(), 'listenin sonuna ulaştınız')]")
                    print("Listenin sonuna ulaşıldı.")
                    break
                except:
                    pass
            
            last_height = new_height
            scroll_count += 1
            print(f"Scroll: {scroll_count}")
        
        # Tüm işletmeleri bul
        time.sleep(2)
        places = driver.find_elements(By.CSS_SELECTOR, "div.Nv2PK")
        
        print(f"\n{len(places)} berber bulundu!\n")
        
        results = []
        
        for i, place in enumerate(places, 1):
            try:
                # İşletme adı
                name = ""
                try:
                    name_element = place.find_element(By.CSS_SELECTOR, "div.qBF1Pd")
                    name = name_element.text
                except:
                    pass
                
                # Puan
                rating = ""
                try:
                    rating_element = place.find_element(By.CSS_SELECTOR, "span.MW4etd")
                    rating = rating_element.text
                except:
                    pass
                
                # Değerlendirme sayısı
                reviews = ""
                try:
                    reviews_element = place.find_element(By.CSS_SELECTOR, "span.UY7F9")
                    reviews = reviews_element.text.replace("(", "").replace(")", "")
                except:
                    pass
                
                # Kategori/Tür
                category = ""
                try:
                    category_elements = place.find_elements(By.CSS_SELECTOR, "div.W4Efsd span")
                    for elem in category_elements:
                        text = elem.text
                        if text and "·" not in text and not text.startswith("("):
                            category = text
                            break
                except:
                    pass
                
                # Adres
                address = ""
                try:
                    address_elements = place.find_elements(By.CSS_SELECTOR, "div.W4Efsd")
                    for elem in address_elements:
                        text = elem.text
                        if "Maltepe" in text or "İstanbul" in text or any(char.isdigit() for char in text):
                            address = text.split("·")[-1].strip() if "·" in text else text
                            break
                except:
                    pass
                
                # Çalışma saatleri
                hours = ""
                try:
                    hours_element = place.find_element(By.CSS_SELECTOR, "span.ZDu9vd span")
                    hours = hours_element.text
                except:
                    pass
                
                # Link
                link = ""
                try:
                    link_element = place.find_element(By.CSS_SELECTOR, "a.hfpxzc")
                    link = link_element.get_attribute("href")
                except:
                    pass
                
                if name:  # Sadece ismi olan kayıtları ekle
                    result = {
                        "sira": i,
                        "isim": name,
                        "puan": rating,
                        "degerlendirme_sayisi": reviews,
                        "kategori": category,
                        "adres": address,
                        "calisma_saati": hours,
                        "link": link
                    }
                    results.append(result)
                    print(f"{i}. {name} - Puan: {rating} ({reviews} değerlendirme)")
                    
            except Exception as e:
                print(f"Hata (kayıt {i}): {str(e)}")
                continue
        
        return results
        
    except Exception as e:
        print(f"Genel hata: {str(e)}")
        return []
        
    finally:
        driver.quit()

def save_to_json(data, filename="berberler.json"):
    """Verileri JSON dosyasına kaydet"""
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nVeriler {filename} dosyasına kaydedildi.")

def save_to_csv(data, filename="berberler.csv"):
    """Verileri CSV dosyasına kaydet"""
    if not data:
        print("Kaydedilecek veri yok!")
        return
    
    keys = data[0].keys()
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)
    print(f"Veriler {filename} dosyasına kaydedildi.")

if __name__ == "__main__":
    # Google Maps URL
    url = "https://www.google.com/maps/search/Maltepe+berberler/@40.9440895,29.1142176,13z/data=!3m1!4b1?entry=ttu&g_ep=EgoyMDI2MDEwNC4wIKXMDSoASAFQAw%3D%3D"
    
    print("=" * 60)
    print("MALTEPE BERBERLER - GOOGLE MAPS VERİ ÇEKME")
    print("=" * 60)
    
    # Verileri çek
    data = scrape_google_maps(url)
    
    if data:
        print(f"\n{'=' * 60}")
        print(f"TOPLAM {len(data)} BERBER BULUNDU")
        print("=" * 60)
        
        # JSON ve CSV olarak kaydet
        save_to_json(data)
        save_to_csv(data)
    else:
        print("Veri çekilemedi!")
