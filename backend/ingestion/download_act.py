"""
Download the Income Tax Act, 2025 from India Code (Ministry of Law).
Source: https://www.indiacode.nic.in/handle/123456789/1501
As specified in Section 4 of the assignment.
"""

import os
import requests
from bs4 import BeautifulSoup

ACT_PAGE_URL = "https://www.indiacode.nic.in/handle/123456789/1501"
SAVE_DIR = "data/raw"
SAVE_PATH = os.path.join(SAVE_DIR, "income_tax_act_2025.pdf")


def download_act():
    os.makedirs(SAVE_DIR, exist_ok=True)

    if os.path.exists(SAVE_PATH):
        print(f"File already exists: {SAVE_PATH}")
        return

    print(f"Fetching page: {ACT_PAGE_URL}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    try:
        response = requests.get(ACT_PAGE_URL, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR fetching page: {e}")
        print("Please manually download the PDF from:")
        print(ACT_PAGE_URL)
        print(f"Save it to: {SAVE_PATH}")
        return

    soup = BeautifulSoup(response.text, "lxml")

    # Look for PDF download links
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" in href.lower() or "bitstream" in href.lower():
            if not href.startswith("http"):
                href = "https://www.indiacode.nic.in" + href
            pdf_links.append(href)

    print(f"Found {len(pdf_links)} potential PDF links: {pdf_links}")

    if not pdf_links:
        print("\nCould not find PDF link automatically.")
        print("Please manually download the PDF from:")
        print(ACT_PAGE_URL)
        print(f"Save it as: {SAVE_PATH}")
        return

    for url in pdf_links:
        print(f"Trying to download: {url}")
        try:
            r = requests.get(url, headers=headers, timeout=60)
            r.raise_for_status()

            if len(r.content) < 10000:
                print(f"File too small ({len(r.content)} bytes), skipping")
                continue

            with open(SAVE_PATH, "wb") as f:
                f.write(r.content)

            print(f"SUCCESS: Saved to {SAVE_PATH} ({len(r.content)} bytes)")
            return

        except requests.RequestException as e:
            print(f"Failed: {e}")
            continue

    print("\nAutomatic download failed. Please manually download from:")
    print(ACT_PAGE_URL)
    print(f"Save it as: {SAVE_PATH}")


if __name__ == "__main__":
    download_act()
