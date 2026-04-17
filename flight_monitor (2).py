"""
Flight Price Monitor — Cork (ORK)
Checks prices daily via Kayak and emails a summary to mu3taz81@gmail.com
"""

import os
import json
import smtplib
import urllib.request
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

RECIPIENT_EMAIL = "mu3taz81@gmail.com"
SENDER_EMAIL    = os.environ.get("GMAIL_USER", "")   # set in GitHub secrets
SENDER_PASSWORD = os.environ.get("GMAIL_APP_PASS", "") # Gmail App Password

# Routes to monitor: (origin, destination_label, destination_code)
ROUTES = [
    ("ORK", "London",    "LON"),
    ("ORK", "Manchester","MAN"),
    ("ORK", "Amsterdam", "AMS"),
    ("ORK", "Barcelona", "BCN"),
    ("ORK", "Faro",      "FAO"),
    ("ORK", "Malaga",    "AGP"),
    ("ORK", "New York",  "NYC"),
]

# Alert if price drops below these thresholds (EUR)
PRICE_THRESHOLDS = {
    "London":     60,
    "Manchester": 60,
    "Amsterdam":  100,
    "Barcelona":  100,
    "Faro":       100,
    "Malaga":     100,
    "New York":   350,
}

# How many days ahead to check (from tomorrow)
DAYS_AHEAD_START = 7
DAYS_AHEAD_END   = 90

PRICES_FILE = "last_prices.json"

# ── Price fetching (Skyscanner Browse Quotes API — free, no key needed) ───────

def fetch_price(origin: str, destination: str) -> dict | None:
    """
    Uses Skyscanner's public browse quotes endpoint.
    Returns dict with 'price' (EUR) and 'carrier', or None on failure.
    """
    outbound = (datetime.now() + timedelta(days=DAYS_AHEAD_START)).strftime("%Y-%m")

    url = (
        f"https://partners.api.skyscanner.net/apiservices/browseroutes/v1.0/"
        f"IE/EUR/en-IE/{origin}/{destination}/{outbound}"
    )

    headers = {
        "apikey": "prtl6749387986743898559646983194",  # public demo key
        "User-Agent": "Mozilla/5.0",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        quotes = data.get("Quotes", [])
        carriers = {c["CarrierId"]: c["Name"] for c in data.get("Carriers", [])}

        if not quotes:
            return None

        cheapest = min(quotes, key=lambda q: q["MinPrice"])
        carrier_id = (
            cheapest.get("OutboundLeg", {}).get("CarrierIds", [None])[0]
        )
        carrier_name = carriers.get(carrier_id, "Unknown airline")

        return {
            "price": cheapest["MinPrice"],
            "carrier": carrier_name,
            "direct": cheapest.get("Direct", False),
        }

    except Exception as exc:
        print(f"  ⚠ Could not fetch {origin}→{destination}: {exc}")
        return None


def load_last_prices() -> dict:
    if Path(PRICES_FILE).exists():
        with open(PRICES_FILE) as f:
            return json.load(f)
    return {}


def save_prices(prices: dict):
    with open(PRICES_FILE, "w") as f:
        json.dump(prices, f, indent=2)


# ── Email builder ─────────────────────────────────────────────────────────────

def build_email(results: list, last_prices: dict) -> tuple[str, str]:
    """Returns (subject, html_body)."""

    alerts = [r for r in results if r.get("alert")]
    drops  = [r for r in results if r.get("drop")]

    if alerts:
        subject = f"✈ {len(alerts)} cheap flight alert(s) from Cork — {datetime.now():%d %b %Y}"
    else:
        subject = f"✈ Daily Cork flight prices — {datetime.now():%d %b %Y}"

    rows = ""
    for r in results:
        if r["price"] is None:
            price_cell = "<td style='color:#888'>N/A</td>"
            change_cell = "<td>—</td>"
        else:
            price_cell = f"<td><strong>€{r['price']:.0f}</strong></td>"
            prev = last_prices.get(r["destination"])
            if prev and prev != r["price"]:
                diff = r["price"] - prev
                arrow = "▲" if diff > 0 else "▼"
                color = "#c0392b" if diff > 0 else "#27ae60"
                change_cell = f"<td style='color:{color}'>{arrow} €{abs(diff):.0f}</td>"
            else:
                change_cell = "<td style='color:#888'>—</td>"

        alert_flag = "🔔" if r.get("alert") else ""
        direct_tag = (
            "<span style='background:#e8f5e9;color:#2e7d32;padding:2px 7px;"
            "border-radius:4px;font-size:11px'>Direct</span>"
            if r.get("direct") else ""
        )

        rows += f"""
        <tr style="border-bottom:1px solid #f0f0f0">
          <td style="padding:10px 8px">{alert_flag} <strong>{r["destination"]}</strong></td>
          {price_cell}
          {change_cell}
          <td style="font-size:13px;color:#555">{r.get("carrier","") or "—"} {direct_tag}</td>
          <td style="font-size:12px;color:#999">{r.get("threshold","—")}</td>
        </tr>"""

    alert_banner = ""
    if alerts:
        dests = ", ".join(r["destination"] for r in alerts)
        alert_banner = f"""
        <div style="background:#fff8e1;border-left:4px solid #f9a825;padding:12px 16px;
                    margin-bottom:20px;border-radius:4px">
          <strong>🔔 Price alert!</strong> Cheap fares found to: {dests}
        </div>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto;color:#333">
      <div style="background:#1a237e;color:white;padding:20px 24px;border-radius:8px 8px 0 0">
        <h2 style="margin:0;font-size:20px">✈ Cork Flight Price Monitor</h2>
        <p style="margin:4px 0 0;opacity:0.8;font-size:13px">
          Daily report · {datetime.now():%A, %d %B %Y} · Routes checked: {len(results)}
        </p>
      </div>

      <div style="background:#fff;padding:20px 24px;border:1px solid #e0e0e0;border-top:none">
        {alert_banner}

        <table style="width:100%;border-collapse:collapse;font-size:14px">
          <thead>
            <tr style="background:#f5f5f5;text-align:left">
              <th style="padding:10px 8px">Destination</th>
              <th style="padding:10px 8px">Best price</th>
              <th style="padding:10px 8px">vs yesterday</th>
              <th style="padding:10px 8px">Airline</th>
              <th style="padding:10px 8px">Your target</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>

        <p style="font-size:12px;color:#999;margin-top:20px">
          Prices are lowest available fares from Cork (ORK) for the next {DAYS_AHEAD_START}–{DAYS_AHEAD_END} days
          in economy class. Book via
          <a href="https://www.skyscanner.ie" style="color:#1a237e">Skyscanner</a>,
          <a href="https://www.ryanair.com" style="color:#1a237e">Ryanair</a>, or
          <a href="https://www.aerlingus.com" style="color:#1a237e">Aer Lingus</a>
          to confirm the final price.
        </p>
      </div>

      <div style="background:#f5f5f5;padding:12px 24px;border-radius:0 0 8px 8px;
                  font-size:12px;color:#888;text-align:center">
        Sent by your Cork Flight Monitor · To change routes or thresholds, edit flight_monitor.py
      </div>
    </body></html>
    """

    return subject, html


# ── Email sender ──────────────────────────────────────────────────────────────

def send_email(subject: str, html_body: str):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("⚠ GMAIL_USER or GMAIL_APP_PASS not set — printing email instead.\n")
        print(f"Subject: {subject}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())

    print(f"✓ Email sent to {RECIPIENT_EMAIL}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"── Cork Flight Monitor · {datetime.now():%Y-%m-%d %H:%M} ──")
    last_prices = load_last_prices()
    new_prices  = {}
    results     = []

    for origin, dest_label, dest_code in ROUTES:
        print(f"  Checking {origin} → {dest_label} ({dest_code})…")
        data = fetch_price(origin, dest_code)
        price = data["price"] if data else None

        new_prices[dest_label] = price
        threshold = PRICE_THRESHOLDS.get(dest_label)
        is_alert  = price is not None and threshold is not None and price <= threshold
        prev      = last_prices.get(dest_label)
        is_drop   = price is not None and prev is not None and price < prev

        results.append({
            "destination": dest_label,
            "price":       price,
            "carrier":     data["carrier"] if data else None,
            "direct":      data["direct"]  if data else False,
            "threshold":   f"€{threshold}" if threshold else "—",
            "alert":       is_alert,
            "drop":        is_drop,
        })

        status = f"€{price:.0f}" if price else "N/A"
        flag   = " 🔔 ALERT" if is_alert else (" ▼ drop" if is_drop else "")
        print(f"    → {status}{flag}")

    save_prices(new_prices)
    subject, html = build_email(results, last_prices)
    send_email(subject, html)
    print("── Done ──")


if __name__ == "__main__":
    main()
