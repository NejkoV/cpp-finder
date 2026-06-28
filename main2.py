import asyncio
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from playwright.async_api import async_playwright

# =====================================================================
# KONFIGURACIJA
# =====================================================================
URL = "https://e-uprava.gov.si/si/javne-evidence/prosti-termini-zemljevid.html?lang=si"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
POSILJATELJ_EMAIL = "nejkodh@gmail.com"
GESLO_ZA_APLIKACIJO = "znaz megp qmjj omce"  # Google App Password
PREJEMNIK_EMAIL = "nejkodh@gmail.com"

# Koliko tednov v prihodnost želiva preiskati (25 tednov je cca. pol leta)
STEVILO_TEDNOV = 25  

IZBRANA_KATEGORIJA = "B"
IZBRANO_OBMOCJE = "Območje 2"
IZBRANA_LOKACIJA = "KRANJ Kolodvorska"
# =====================================================================


def poslji_email(vsebina_terminov):
    """Funkcija za pošiljanje obvestila na e-mail."""
    msg = MIMEMultipart()
    msg["From"] = POSILJATELJ_EMAIL
    msg["To"] = PREJEMNIK_EMAIL
    msg["Subject"] = "⚠️ OBVESTILO: Najdeni prosti termini za vožnjo (Kranj) ⚠️"

    telo = f"Živijo,\n\nna e-Upravi so se pojavili prosti termini v naslednjih {STEVILO_TEDNOV} tednih:\n\n"
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
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("[1/4] Odpiram spletno stran e-Uprave...")
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        
        print("[2/4] Nastavljam filtre (Kategorija, Območje, Kraj)...")
        await page.wait_for_selector("text=PREVERJANJE ZNANJA", timeout=15000)

        try:
            # 1. Izbira "Vožnja"
            print(" -> Klikam: Vožnja")
            await page.locator("label:has-text('Vožnja')").first.click(force=True)
            await page.wait_for_timeout(1500)

            # 2. Izbira kategorije
            print(f" -> Klikam: Kategorija {IZBRANA_KATEGORIJA}")
            kategorija_label = page.locator(f"//label[normalize-space(text())='{IZBRANA_KATEGORIJA}']").first
            await kategorija_label.click(force=True)
            await page.wait_for_timeout(1500)

            # 3. Izbira Območja
            print(" -> Izbiram Območje...")
            await page.locator("//div[contains(text(), 'Vsa območja')] | //span[contains(text(), 'Vsa območja')] | //input[@placeholder='Vsa območja']").first.click(force=True)
            await page.wait_for_timeout(1000)
            await page.keyboard.type(IZBRANO_OBMOCJE)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(1500)

            # 4. Izbira Kraja / Lokacije
            print(" -> Izbiram Lokacijo...")
            await page.locator("//div[contains(text(), 'Vse lokacije')] | //span[contains(text(), 'Vse lokacije')] | //input[@placeholder='Vse lokacije']").first.click(force=True)
            await page.wait_for_timeout(1000)
            await page.keyboard.type(IZBRANA_LOKACIJA)
            await page.wait_for_timeout(500)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)

        except Exception as e:
            print(f"[OPOZORILO] Težava pri vnosu filtrov: {e}")
        
        print(f"[3/4] Začenjam preklikavanje naslednjih {STEVILO_TEDNOV} tednov...")
        najdeni_termini = []

        for teden in range(STEVILO_TEDNOV):
            await page.wait_for_timeout(1500) # Čakamo, da se tabela osveži po kliku
            
            # Analiza vrstic za trenutno vidni teden
            vrstice = await page.locator("table tr, .table tr, div.row").all_inner_texts()
            
            for vrstica in vrstice:
                tekst_clean = vrstica.strip()
                if not tekst_clean or "Tip / Lokacija" in tekst_clean or "Prosta mesta" in tekst_clean:
                    continue
                
                # POPRAVEK: Namesto filtriranja po besedi "KRANJ", vzamemo vsako vrstico,
                # ki vsebuje številko (datum/uro) ali besedo "prost", saj so filtri že nastavljeni na Kranj!
                if any(char.isdigit() for char in tekst_clean) or "PROST" in tekst_clean.upper():
                    urejen_tekst = " | ".join([delcek.strip() for delcek in tekst_clean.split("\n") if delcek.strip()])
                    najdeni_termini.append(urejen_tekst)
            
            # Klik na gumb "NASLEDNJI TEDEN" za premik naprej
            try:
                gumb_naslednji = page.locator("text=NASLEDNJI TEDEN").first
                if not await gumb_naslednji.is_visible():
                    gumb_naslednji = page.locator("//div[contains(text(), 'NASLEDNJI TEDEN')] | //span[contains(text(), 'NASLEDNJI TEDEN')] | //a[contains(text(), 'NASLEDNJI TEDEN')]").first
                
                if await gumb_naslednji.is_visible():
                    print(f" -> Pregledan teden {teden + 1}/{STEVILO_TEDNOV}. Klikam 'NASLEDNJI TEDEN'...")
                    await gumb_naslednji.click(force=True)
                else:
                    print(f"[INFO] Gumb 'NASLEDNJI TEDEN' ni več viden. Konec seznama.")
                    break
            except Exception as e:
                print(f"[OPOZORILO] Ni mogoče klikniti gumba za naslednji teden: {e}")
                break

        # Kontrolni posnetek (shranil bo teden, kjer se je zanka ustavila)
        await page.screenshot(path="končni_pogled_terminov.png", full_page=True)
        print("[INFO] Kontrolni posnetek stanja shranjen v 'končni_pogled_terminov.png'")

        print("[4/4] Zaključujem analizo...")
        # Odstranimo morebitne duplikate
        najdeni_termini = list(set(najdeni_termini))

        if najdeni_termini:
            print(f"[USPEH] Skupno najdenih {len(najdeni_termini)} prostih terminov!")
            for t in najdeni_termini:
                print(f" -> {t}")
                
            vsebina_za_mail = "\n\n".join(najdeni_termini)
            poslji_email(vsebina_za_mail)
        else:
            print(f"[-] V celotnem obdobju {STEVILO_TEDNOV} tednov ni bilo najdenih prostih terminov.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(glavna_skripta())