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
URL = "https://e-uprava.gov.si/si/javne-evidence/prosti-termini-zemljevid.html?lang=si"

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
        
        # POPRAVEK: Popolnoma izpustiva koledar in pustiva, da JS sam osveži tabelo spodaj
        print("[3/4] Čakam, da e-Uprava osveži tabelo pod zemljevidom...")
        await page.wait_for_timeout(6000)

        # Kontrolni posnetek - zdaj ko filtri delajo, morava tukaj videti termine!
        await page.screenshot(path="končni_pogled_terminov.png", full_page=True)
        print("[INFO] Kontrolni posnetek stanja shranjen v 'končni_pogled_terminov.png'")

        print("[4/4] Analiziram tabelo z rezultati...")
        
        najdeni_termini = []
        
        # Ker so rezultati v klasični tabeli (kot na tvoji uspešni sliki),
        # zajamemo vse vrstice 'tr' ali celice 'td' na strani
        vrstice = await page.locator("table tr, .table tr, div.row").all_inner_texts()
        
        print(f"[INFO] Najdeno {len(vrstice)} potencialnih vrstic na strani.")

        for vrstica in vrstice:
            tekst_clean = vrstica.strip()
            
            # Preskočimo prazne vrstice in glavo tabele
            if not tekst_clean or "Tip / Lokacija" in tekst_clean or "Prosta mesta" in tekst_clean:
                continue
                
            # Če vrstica vsebuje Kranj ali Območje 2, jo vzamemo, saj koledar že sam omeji izpis
            if "KRANJ" in tekst_clean.upper() or "OBMOČJE 2" in tekst_clean.upper():
                # Očistimo morebitne prelomnice vrstic za lepši izpis v mailu
                urejen_tekst = " | ".join([delcek.strip() for delcek in tekst_clean.split("\n") if delcek.strip()])
                najdeni_termini.append(urejen_tekst)

        # Odstranimo duplikate
        najdeni_termini = list(set(najdeni_termini))

        if najdeni_termini:
            print(f"[USPEH] Najdenih je {len(najdeni_termini)} terminov v tabeli!")
            # Izpišemo jih v terminal, da jih takoj vidiš
            for t in najdeni_termini:
                print(f" -> {t}")
                
            vsebina_za_mail = "\n\n".join(najdeni_termini)
            poslji_email(vsebina_za_mail)
        else:
            print(f"[-] V tabeli ni bilo najdenih prostih terminov.")
            print("[NASVET] Poglej sliko 'končni_pogled_terminov.png' - če je tabela spodaj vidna, a je prazna, terminov preprosto ni.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(glavna_skripta())