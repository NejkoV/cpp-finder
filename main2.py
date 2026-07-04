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
URL = "https://e-uprava.gov.si/si/javne-evidence/prosti-termini-zemljevid.html?lang=si#eyJwYWdlIjpbMF0sImZpbHRlcnMiOnsidHlwZSI6WyIxIl0sImNhdCI6WyI2Il0sIml6cGl0bmlDZW50ZXIiOlsiMTgiXSwibG9rYWNpamEiOlsiMjIzIl0sIm9mZnNldCI6WyIwIl0sInNlbnRpbmVsX3R5cGUiOlsib2siXSwic2VudGluZWxfc3RhdHVzIjpbIm9rIl0sImlzX2FqYXgiOlsiMSJdfSwib2Zmc2V0UGFnZSI6bnVsbH0="

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
        # headless=True pusti za produkcijo, če si na strežniku brez grafičnega vmesnika
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context(
            viewport={"width": 1400, "height": 1200},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("[1/4] Odpiram spletno stran e-Uprave...")
        # POPRAVEK: Uporabimo domcontentloaded, da se izognemo timeoutu zaradi neskončnih omrežnih zahtev v ozadju
        await page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        
        print("[2/4] Nastavljam filtre (Kategorija)...")
        # Čakamo, da se naloži celoten filter kontejner
        await page.wait_for_selector(".form-check, label", timeout=20000)
        await page.wait_for_timeout(2000)

        try:
            # 1. Izbira "Vožnja"
            print(" -> Klikam: Vožnja")
            # Uporabimo tekstovni selektor, ki ignorira natančno ujemanje velikih/malih črk in presledkov
            await page.locator("label", has_text="Vožnja").first.click(force=True)
            await page.wait_for_timeout(2000) # Malo več časa, da se kategorije dinamično prikažejo

            # 2. Izbira kategorije B
            print(f" -> Klikam: Kategorija {IZBRANA_KATEGORIJA}")
            
            # REŠITEV: Poiščemo labelo, ki vsebuje točno določeno kategorijo, 
            # vendar dovolimo poljuben tekst okoli nje (npr. presledke).
            kategorija_locator = page.locator(f"label:has-text('{IZBRANA_KATEGORIJA}')")
            
            # Če je locatorjev več, izberemo tistega, ki ima najbolj natančno ujemanje
            # ali pa uporabimo specifičen XPath/CSS e-uprave, če klasičen tekst odpove:
            if await kategorija_locator.count() > 0:
                # Najbolj varna pot na e-upravi je klik neposredno na tekst ali krogec poleg njega
                await page.locator(f"//label[contains(normalize-space(.), '{IZBRANA_KATEGORIJA}')]").first.click(force=True)
            else:
                # Rezervni načrt, če so kategorije znotraj spanov
                await page.locator(f"span:has-text('{IZBRANA_KATEGORIJA}')").first.click(force=True)

            await page.wait_for_timeout(2000)
            print(" -> Filtri uspešno nastavljeni prek vmesnika.")

        except Exception as e:
            print(f"[OPOZORILO] Težava pri vnosu filtrov: {e}")
        
        print(f"[3/4] Preklapljam skozi {STEVILO_TEDNOV} tednov in zbiram vsebino strani...")
        vsebina_tednov = []

        for teden in range(STEVILO_TEDNOV):
            try:
                trenutna_vsebina = await page.locator("#prostiTerminiRezultat, .table-responsive, table, table").first.inner_text()
            except Exception:
                trenutna_vsebina = ""

            if trenutna_vsebina:
                vsebina_tednov.append(trenutna_vsebina)

            # Klik na gumb "NASLEDNJI TEDEN" (poenostavljeno, brez takojšnje obdelave)
            try:
                gumb_naslednji = page.locator("text=NASLEDNJI TEDEN").first
                if not await gumb_naslednji.is_visible():
                    gumb_naslednji = page.locator("//button[contains(., 'NASLEDNJI TEDEN')] | //a[contains(., 'NASLEDNJI TEDEN')] | //span[contains(., 'NASLEDNJI TEDEN')]").first

                if await gumb_naslednji.is_visible():
                    print(f" -> Teden {teden + 1}/{STEVILO_TEDNOV} zabeležen. Klikam 'NASLEDNJI TEDEN'...")
                    await gumb_naslednji.click(force=True)
                    await page.wait_for_timeout(1200)
                else:
                    print(f"[INFO] Gumb 'NASLEDNJI TEDEN' ni več viden. Konec seznama.")
                    break
            except Exception as e:
                print(f"[OPOZORILO] Ni mogoče klikniti gumba za naslednji teden: {e}")
                break

        # Po koncu preklapljanja obdelamo združene vsebine enkrat
        print("[INFO] Obdelujem zbrane vsebine (enkrat na koncu)...")
        najdeni_termini = []
        zdruzeno = "\n".join(vsebina_tednov)

        for vrstica in zdruzeno.splitlines():
            tekst_clean = vrstica.strip()
            if not tekst_clean or "Tip / Lokacija" in tekst_clean or "Prosta mesta" in tekst_clean:
                continue
            if any(char.isdigit() for char in tekst_clean) and "KRANJ" in tekst_clean.upper():
                urejen_tekst = " | ".join([delcek.strip() for delcek in tekst_clean.split("\n") if delcek.strip()])
                najdeni_termini.append(urejen_tekst)

        # Shranjevanje kontrolne slike (brez full_page zapletov)
        try:
            await page.screenshot(path="končni_pogled_terminov.png", timeout=5000)
            print("[INFO] Kontrolni posnetek stanja shranjen v 'končni_pogled_terminov.png'")
        except Exception as e:
            print(f"[OPOZORILO] Ni bilo mogoče narediti posnetka zaslona: {e}")

        # Zaključek in pošiljanje obvestila
        print("[4/4] Zaključujem analizo...")
        najdeni_termini = list(set(najdeni_termini))

        if najdeni_termini:
            print(f"[USPEH] Skupno najdenih {len(najdeni_termini)} prostih terminov!")
            vsebina_za_mail = "\n\n".join(najdeni_termini)
            poslji_email(vsebina_za_mail)
        else:
            print(f"[-] V celotnem obdobju {STEVILO_TEDNOV} tednov ni bilo najdenih prostih terminov.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(glavna_skripta())