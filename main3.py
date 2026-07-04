import asyncio
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from playwright.async_api import async_playwright

# =====================================================================
# KONFIGURACIJA
# =====================================================================
URL = "https://e-uprava.gov.si/si/javne-evidence/prosti-termini-zemljevid.html?lang=si#eyJwYWdlIjpbMF0sImZpbHRlcnMiOnsidHlwZSI6WyIxIl0sImNhdCI6WyI2Il0sIml6cGl0bmlDZW50ZXIiOlsiMTgiXSwibG9rYWNpamEiOlsiMjIzIl0sIm9mZnNldCI6WyIwIl0sInNlbnRpbmVsX3R5cGUiOlsib2siXSwic2VudGluZWxfc3RhdHVzIjpbIm9rIl0sImlzX2FqYXgiOlsiMSJdfSwib2Zmc2V0UGFnZSI6bnVsbH0="

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
POSILJATELJ_EMAIL = "nejkodh@gmail.com"
GESLO_ZA_APLIKACIJO = "znaz megp qmjj omce"  # Google App Password
PREJEMNIK_EMAIL = "nejkodh@gmail.com"

MAX_DNI = 200

# POPRAVEK: Vsi parametri zbrani tukaj
IZBRANA_KATEGORIJA = "B"
IZBRANO_OBMOCJE = "Območje 2"
IZBRANA_LOKACIJA = "KRANJ Kolodvorska"
STEVILO_TEDNOV = 25
# =====================================================================


def poslji_email(vsebina_terminov):
    """Funkcija za pošiljanje obvestila na e-mail."""
    msg = MIMEMultipart()
    msg["From"] = POSILJATELJ_EMAIL
    msg["To"] = PREJEMNIK_EMAIL
    msg["Subject"] = "⚠️ OBVESTILO: Najdeni prosti termini za vožnjo (Kranj) ⚠️"

    telo = f"Živijo,\n\nna e-Upravi so se pojavili prosti termini v naslednjih {MAX_DNI} dneh:\n\n"
    telo += vsebina_terminov
    telo += f"\n\nPovezava do strani: {URL}"

    msg.attach(MIMEText(telo, "plain", "utf-8"))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(POSILJATELJ_EMAIL, GESLO_ZA_APLIKACIJO)
        server.sendmail(POSILJATELJ_EMAIL, PREJEMNIK_EMAIL, msg.as_string())
        server.quit()
        print("[ZAUPNO] E-mail je bil uspešno poslan!")
    except Exception as e:
        print(f"[NAPAKA] Težava pri pošiljanju e-maila: {e}")


async def glavna_skripta():
    async with async_playwright() as p:
        # headless=True za delo v ozadju
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("[1/4] Odpiram spletno stran e-Uprave...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        
        print("[2/4] Nastavljam filtre natančno po elementih...")
        await page.wait_for_selector("text=PREVERJANJE ZNANJA", timeout=15000)

        try:
            # 1. Izbira "Vožnja"
            print(" -> Klikam: Vožnja")
            await page.locator("label:has-text('Vožnja')").first.click(force=True)
            await page.wait_for_timeout(2000)

            # 2. Izbira kategorije (POPRAVEK: Klik neposredno na checkbox preko pripadajočega labela z uporabo force=True)
            print(f" -> Klikam: Kategorija {IZBRANA_KATEGORIJA}")
            
            # Najdemo label, ki ima natančno besedilo "B", in kliknemo nanj z možnostjo force=True
            kategorija_label = page.locator(f"//label[normalize-space(text())='{IZBRANA_KATEGORIJA}']").first
            await kategorija_label.click(force=True)
            await page.wait_for_timeout(2000)

            # 3. Izbira Območja
            print(" -> Izbiram Območje...")
            # Kliknemo na polje "Vsa območja"
            await page.locator("//div[contains(text(), 'Vsa območja')] | //span[contains(text(), 'Vsa območja')] | //input[@placeholder='Vsa območja']").first.click(force=True)
            await page.wait_for_timeout(1000)
            
            await page.keyboard.type(IZBRANO_OBMOCJE)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

            # 4. Izbira Kraja / Lokacije
            print(" -> Izbiram Lokacijo...")
            await page.locator("//div[contains(text(), 'Vse lokacije')] | //span[contains(text(), 'Vse lokacije')] | //input[@placeholder='Vse lokacije']").first.click(force=True)
            await page.wait_for_timeout(1000)
            
            await page.keyboard.type(IZBRANA_LOKACIJA)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Enter")

        except Exception as e:
            print(f"[OPOZORILO] Težava pri vnosu filtrov: {e}")

        print(f"[3/4] Preklapljam skozi {STEVILO_TEDNOV} tednov in zbiram vsebino strani...")
        vsebina_tednov = []

        for teden in range(STEVILO_TEDNOV):
            # 1. Počakamo, da se tabela naloži / stabilizira
            try:
                tabela_locator = page.locator("#prostiTerminiRezultat table, .table-responsive table").first
                await tabela_locator.wait_for(state="visible", timeout=5000)
                
                # Preberemo tekst celotne tabele
                trenutna_vsebina = await tabela_locator.inner_text()
            except Exception:
                trenutna_vsebina = ""

            if trenutna_vsebina and trenutna_vsebina.strip():
                vsebina_tednov.append(trenutna_vsebina)

            # 2. Klik na gumb "NASLEDNJI TEDEN"
            try:
                # E-uprava uporablja puščice, ki imajo pogosto title, class 'next' ali pa specifičen onclick atribut.
                # Spodnji selektor poskusi najti gumb preko različnih pogostih e-uprava struktur:
                gumb_naslednji = page.locator(
                    "a.next, "
                    "button.next, "
                    "[title*='Naslednji'], "
                    "[title*='naslednji'], "
                    "//a[contains(text(), 'Naslednji')] | //button[contains(text(), 'Naslednji')]"
                ).first

                if await gumb_naslednji.is_visible():
                    print(f" -> Teden {teden + 1}/{STEVILO_TEDNOV} zabeležen. Klikam naslednji teden...")
                    
                    # Da zagotovimo, da bomo po kliku zaznali spremembo, si lahko shranimo trenutno stanje
                    star_tekst = trenutna_vsebina
                    
                    await gumb_naslednji.click(force=True)
                    
                    # Namesto fiksnega timeouta počakamo, da se vsebina tabele spremeni (postane drugačna od stare)
                    # Če se ne spremeni, počakamo maksimalno 3 sekunde
                    try:
                        await page.wait_for_function(
                            "old => document.querySelector('#prostiTerminiRezultat').innerText !== old",
                            arg=star_tekst,
                            timeout=3000
                        )
                    except Exception:
                        # Če se vsebina ni spremenila, je stran morda počasna, zato dodamo krajši fiksen premor
                        await page.wait_for_timeout(1000)
                else:
                    print(f"[INFO] Gumb za naslednji teden ni viden ali ne obstaja. Konec seznama.")
                    break
            except Exception as e:
                print(f"[OPOZORILO] Ni mogoče klikniti gumba za naslednji teden: {e}")
                break

        # Po koncu preklapljanja obdelamo združene vsebine enkrat
        print("[INFO] Obdelujem zbrane vsebine (enkrat na koncu)...")
        najdeni_termini = []

        for blok_tedna in vsebina_tednov:
            # Vsak teden razbijemo na vrstice
            for vrstica in blok_tedna.splitlines():
                tekst_clean = vrstica.strip()
                
                # Preskočimo prazne vrstice in glave tabel
                if not tekst_clean or any(x in tekst_clean for x in ["Tip / Lokacija", "Prosta mesta", "Ni prostih terminov"]):
                    continue
                
                # Preverimo, če vrstica vsebuje KRANJ (iščemo neglede na velike/male črke) in vsaj eno številko (datum/ura)
                if "KRANJ" in tekst_clean.upper() and any(char.isdigit() for char in tekst_clean):
                    # Očistimo morebitne odvečne bele znake znotraj vrstice
                    urejen_tekst = " ".join(tekst_clean.split())
                    najdeni_termini.append(urejen_tekst)

        # Odstranimo podvojene vrstice
        najdeni_termini = list(set(najdeni_termini))

        # Shranjevanje kontrolne slike
        try:
            await page.screenshot(path="končni_pogled_terminov.png", timeout=5000)
            print("[INFO] Kontrolni posnetek stanja shranjen v 'končni_pogled_terminov.png'")
        except Exception as e:
            print(f"[OPOZORILO] Ni bilo mogoče narediti posnetka zaslona: {e}")

        # Zaključek in pošiljanje obvestila
        print("[4/4] Zaključujem analizo...")

        if najdeni_termini:
            print(f"[USPEH] Skupno najdenih {len(najdeni_termini)} prostih terminov za Kranj!")
            vsebina_za_mail = "\n".join(najdeni_termini)
            poslji_email(vsebina_za_mail)
        else:
            print(f"[-] V celotnem obdobju {STEVILO_TEDNOV} tednov ni bilo najdenih prostih terminov za Kranj.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(glavna_skripta())