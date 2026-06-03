"""
Download all CBDT Circulars from the official Income Tax India portal.
Source: https://www.incometaxindia.gov.in/communications/circular/
As specified in Section 4 of the assignment.
Coverage target: ALL circulars on the official portal.
"""

import os
import time
import requests
from bs4 import BeautifulSoup

CIRCULARS_PAGE_URL = "https://www.incometaxindia.gov.in/circulars"
SAVE_DIR = "data/raw/circulars"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def get_all_circular_links():
    """
    Scrape all PDF circular links from the official CBDT circulars page.
    The page may have pagination — we handle multiple pages.
    """
    all_links = []
    page_url = CIRCULARS_PAGE_URL

    while page_url:
        print(f"Fetching circular listing page: {page_url}")

        try:
            response = requests.get(page_url, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"Error fetching page: {e}")
            break

        soup = BeautifulSoup(response.text, "lxml")

        # Find all links that point to PDFs
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.lower().endswith(".pdf"):
                if not href.startswith("http"):
                    if href.startswith("/"):
                        href = "https://www.incometaxindia.gov.in" + href
                    else:
                        href = "https://www.incometaxindia.gov.in/" + href

                link_text = a.get_text(strip=True)
                all_links.append({
                    "url": href,
                    "name": link_text or href.split("/")[-1]
                })

        # Check for next page link
        next_page = None
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if "next" in text or "»" in text:
                next_href = a["href"]
                if not next_href.startswith("http"):
                    next_href = "https://www.incometaxindia.gov.in" + next_href
                if next_href != page_url:
                    next_page = next_href
                    break

        page_url = next_page

    # Deduplicate by URL
    seen = set()
    unique_links = []
    for link in all_links:
        if link["url"] not in seen:
            seen.add(link["url"])
            unique_links.append(link)

    return unique_links


def download_all_circulars():
    os.makedirs(SAVE_DIR, exist_ok=True)

    links = get_all_circular_links()
    print(f"\nFound {len(links)} unique circular PDFs")

    success = 0
    failed = 0

    for i, link in enumerate(links):
        filename = link["url"].split("/")[-1]
        if not filename.endswith(".pdf"):
            filename = filename + ".pdf"

        save_path = os.path.join(SAVE_DIR, filename)

        if os.path.exists(save_path):
            print(f"[{i+1}/{len(links)}] Already exists, skipping: {filename}")
            success += 1
            continue

        try:
            print(f"[{i+1}/{len(links)}] Downloading: {filename}")
            r = requests.get(link["url"], headers=HEADERS, timeout=30)
            r.raise_for_status()

            with open(save_path, "wb") as f:
                f.write(r.content)

            print(f"  Saved ({len(r.content)} bytes)")
            success += 1
            time.sleep(0.5)  # Polite delay between requests

        except requests.RequestException as e:
            print(f"  FAILED: {e}")
            failed += 1

    print(f"\nDone. Success: {success}, Failed: {failed}")
    print(f"Circulars saved to: {SAVE_DIR}")


if __name__ == "__main__":
    download_all_circulars()
