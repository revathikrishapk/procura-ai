from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv


class SourcingError(RuntimeError):
    pass


PRICE_PATTERN = re.compile(
    r"(?P<currency>₹|INR|Rs\.?|USD|\$|EUR|€|GBP|£)\s*"
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<scale>lakh|lac|lakhs|lacs|crore|cr)?",
    re.IGNORECASE,
)
REVERSE_PRICE_PATTERN = re.compile(
    r"(?P<amount>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<scale>lakh|lac|lakhs|lacs|crore|cr)?\s*"
    r"(?P<currency>INR|USD|EUR|GBP)",
    re.IGNORECASE,
)

CURRENCY_CODES = {
    "₹": "INR",
    "rs": "INR",
    "rs.": "INR",
    "inr": "INR",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}


def _parse_price(text: str):
    match = PRICE_PATTERN.search(text) or REVERSE_PRICE_PATTERN.search(text)
    if not match:
        return None

    amount = float(match.group("amount").replace(",", ""))
    scale = (match.groupdict().get("scale") or "").lower()
    if scale in {"lakh", "lac", "lakhs", "lacs"}:
        amount *= 100_000
    elif scale in {"crore", "cr"}:
        amount *= 10_000_000

    currency = CURRENCY_CODES.get(match.group("currency").lower())
    if not currency or amount <= 0:
        return None
    return amount, currency, match.group(0)


def _parse_product_price(text: str, product_terms: set[str]):
    for match in PRICE_PATTERN.finditer(text):
        start = max(0, match.start() - 180)
        end = min(len(text), match.end() + 180)
        context = text[start:end].lower()
        if not product_terms or any(term in context for term in product_terms):
            price = _parse_price(match.group(0))
            if price:
                return price[0], price[1], text[start:end].strip()[:500]
    return None


def _supplier_name(title: str, url: str):
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").removeprefix("www.")
    if hostname:
        return hostname.split(".")[0].replace("-", " ").title()
    return title.strip() or "External Supplier"


def search_external_suppliers(
    product_name: str,
    budget: float,
    quantity: int = 1,
    currency: str = "INR",
):
    """Search and extract live web pages; only return offers with explicit prices."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise SourcingError("TAVILY_API_KEY is not configured in the project .env file.")

    try:
        search_response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": f"{product_name} supplier price {currency} buy",
                "max_results": 5,
                "search_depth": "advanced",
                "include_answer": False,
            },
            timeout=30,
        )
        search_response.raise_for_status()
        search_payload = search_response.json()
    except (requests.RequestException, ValueError) as error:
        raise SourcingError(f"Web search failed: {error}") from error

    if not isinstance(search_payload, dict):
        raise SourcingError("Web search returned an invalid response.")
    search_results = search_payload.get("results", [])
    if not isinstance(search_results, list):
        raise SourcingError("Web search returned an invalid results list.")
    search_results = [
        result for result in search_results if isinstance(result, dict)
    ]
    if not search_results:
        return []

    pages_to_extract = [
        result.get("url")
        for result in search_results
        if isinstance(result.get("url"), str)
        and result["url"]
        and urlparse(result["url"]).scheme in {"http", "https"}
    ][:5]

    page_content = {}
    if pages_to_extract:
        try:
            extract_response = requests.post(
                "https://api.tavily.com/extract",
                json={"api_key": api_key, "urls": pages_to_extract},
                timeout=45,
            )
            extract_response.raise_for_status()
            extraction = extract_response.json()
            if not isinstance(extraction, dict):
                raise SourcingError("Supplier page extraction returned an invalid response.")
            extracted_results = extraction.get("results", [])
            if not isinstance(extracted_results, list):
                raise SourcingError("Supplier page extraction returned an invalid results list.")
            page_content = {
                result.get("url"): result.get("raw_content", "")
                for result in extracted_results
                if isinstance(result, dict)
                and isinstance(result.get("url"), str)
                and result.get("url")
            }
        except (requests.RequestException, ValueError) as error:
            raise SourcingError(f"Supplier page extraction failed: {error}") from error

    offers = []
    seen_urls = set()
    product_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z0-9]+", product_name)
        if len(term) > 2
    }
    for result in search_results:
        url = result.get("url", "")
        if not isinstance(url, str) or not url or url in seen_urls:
            continue
        seen_urls.add(url)

        title = result.get("title", "")
        if not isinstance(title, str):
            title = ""
        snippet = result.get("content", "")
        if not isinstance(snippet, str):
            snippet = ""
        extracted_text = page_content.get(url, "")
        if not isinstance(extracted_text, str):
            extracted_text = ""
        evidence = extracted_text or snippet
        searchable_text = f"{title} {url} {snippet} {extracted_text}".lower()
        if product_terms and not any(term in searchable_text for term in product_terms):
            continue

        parsed_price = _parse_product_price(evidence, product_terms)
        if not parsed_price:
            continue

        unit_price, offer_currency, evidence_text = parsed_price
        if offer_currency != currency.upper():
            continue
        normalized_product = product_name.lower()
        if "h100" in normalized_product:
            minimum_price = 500_000 if offer_currency == "INR" else 5_000
            if unit_price < minimum_price:
                continue

        total_price = unit_price * quantity
        if total_price > budget:
            continue

        supplier_name = _supplier_name(title, url)
        offers.append({
            "supplier_name": supplier_name,
            "product_name": product_name,
            "unit_price": unit_price,
            "total_price": total_price,
            "currency": offer_currency,
            "lead_time_days": None,
            "source": url,
            "source_type": "external",
            "price_evidence": evidence_text[:500],
            "extraction_method": "page" if extracted_text else "search_snippet",
        })

    return sorted(offers, key=lambda offer: offer["total_price"])


def choose_best_offer(offers):
    if not offers:
        return None
    return min(
        offers,
        key=lambda offer: (
            offer["total_price"],
            offer.get("lead_time_days") or 9999,
        ),
    )
