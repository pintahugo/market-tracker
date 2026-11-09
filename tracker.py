#!/usr/bin/env python3
"""
Hugo Pinta - Markkinadata & Osakeseuranta
Seuraa valittuja osakkeita ja tulostaa reaaliaikaiset kurssit,
valuaatiokertoimet sekä sijoitussignaalit (aliarvostusanalyysi).
"""

import sys
import argparse
from datetime import datetime

# Määritellään Hugon seuraamat osakkeet (omistuksessa / aktiivisessa seurannassa)
DEFAULT_STOCKS = [
    {"symbol": "NESTE.HE", "name": "Neste Oyj", "exchange": "Helsinki (OMXH)"},
    {"symbol": "UPM.HE", "name": "UPM-Kymmene", "exchange": "Helsinki (OMXH)"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "exchange": "NASDAQ"},
    {"symbol": "IREN", "name": "Iren (Iris Energy)", "exchange": "NASDAQ"},
    {"symbol": "NDA-FI.HE", "name": "Nordea Bank Abp", "exchange": "Helsinki (OMXH)"},
    {"symbol": "HUH1V.HE", "name": "Huhtamäki Oyj", "exchange": "Helsinki (OMXH)"},
    {"symbol": "TELIA.ST", "name": "Telia Company", "exchange": "Nasdaq Stockholm"},
    {"symbol": "INTC", "name": "Intel Corporation", "exchange": "NASDAQ"},
]

# Mahdollisuusuniversumi — osakkeet joita screenataan ostomahdollisuuksien varalta.
# Ilmoitus tulee vain jos signaali on riittävän vahva (OSTA NYT).
OPPORTUNITY_STOCKS = [
    {"symbol": "TSM", "name": "Taiwan Semiconductor", "exchange": "NYSE"},
    {"symbol": "ASML", "name": "ASML Holding", "exchange": "NASDAQ"},
    {"symbol": "MSFT", "name": "Microsoft", "exchange": "NASDAQ"},
    {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ"},
    {"symbol": "NOKIA.HE", "name": "Nokia Oyj", "exchange": "Helsinki (OMXH)"},
    {"symbol": "FORTUM.HE", "name": "Fortum Oyj", "exchange": "Helsinki (OMXH)"},
    {"symbol": "SAMPO.HE", "name": "Sampo Oyj", "exchange": "Helsinki (OMXH)"},
    {"symbol": "AMD", "name": "AMD", "exchange": "NASDAQ"},
    {"symbol": "BRKB", "name": "Berkshire Hathaway", "exchange": "NYSE"},
]

def format_currency(val, currency="EUR"):
    if val is None:
        return "N/A"
    curr_symbol = "€" if currency in ["EUR", "eur"] else ("$" if currency in ["USD", "usd"] else currency)
    return f"{val:.2f} {curr_symbol}"

def format_market_cap(val, currency="EUR"):
    if val is None:
        return "N/A"
    curr_symbol = "€" if currency in ["EUR", "eur"] else ("$" if currency in ["USD", "usd"] else currency)
    if val >= 1e12:
        return f"{val / 1e12:.2f} T {curr_symbol}"
    elif val >= 1e9:
        return f"{val / 1e9:.2f} Mrd {curr_symbol}"
    elif val >= 1e6:
        return f"{val / 1e6:.1f} M {curr_symbol}"
    return f"{val:,.0f} {curr_symbol}"

def format_pe(val):
    if val is None or val <= 0:
        return "N/A"
    return f"{val:.1f}"

def format_dividend(val):
    if val is None:
        return "N/A"
    # yfinance voi antaa osingon joko desimaalina (0.045) tai prosenttina (4.5)
    pct = val * 100 if val < 0.3 else val
    return f"{pct:.2f} %"

def map_recommendation(rec_key):
    """
    Kääntää analyytikoiden konsensus-suosituksen suomeksi:
    OSTA / LISÄÄ / PIDÄ / VÄHENNÄ / MYY
    """
    if not rec_key:
        return ("N/A", "dim")
    
    key = str(rec_key).lower().replace("_", "").replace(" ", "")
    
    if "strongbuy" in key:
        return ("OSTA (Vahva)", "bold green")
    elif "buy" in key:
        return ("OSTA", "bold green")
    elif "outperform" in key or "overweight" in key:
        return ("LISÄÄ", "green")
    elif "hold" in key or "neutral" in key:
        return ("PIDÄ", "yellow")
    elif "underperform" in key or "underweight" in key:
        return ("VÄHENNÄ", "bright_red")
    elif "sell" in key:
        return ("MYY", "bold red")
    
    return (str(rec_key).upper(), "white")

def compute_signal(item):
    """
    Laskee sijoitussignaalin (OSTA NYT / SEURAA / ODOTA) useista tekijöistä:
    - Analyytikkojen konsensus-suositus
    - Nousuvara tavoitehintaan
    - Sijainti 52 viikon vaihteluvälillä (lähellä pohjia = kiinnostava)
    - Forward P/E vs TTM P/E (odotettu tuloskasvutrendi)

    Palauttaa: (signaali_teksti, selitys_lista, pisteet)
    """
    score = 0
    reasons = []

    # 1. Analyytikkokonsensus
    rec = str(item.get("recommendation") or "").lower().replace("_", "").replace(" ", "")
    if "strongbuy" in rec or "buy" in rec:
        score += 2
        reasons.append("✅ Analyytikot suosittavat ostamaan")
    elif "outperform" in rec or "overweight" in rec:
        score += 1
        reasons.append("✅ Analyytikot: ylituotto-odotus")
    elif "hold" in rec or "neutral" in rec:
        reasons.append("➡️  Analyytikot: pidä")
    elif "underperform" in rec or "underweight" in rec or "sell" in rec:
        score -= 1
        reasons.append("⚠️  Analyytikot suosittavat myymään")

    # 2. Nousuvara tavoitehintaan
    target = item.get("target_price")
    price = item.get("price")
    if target and price and price > 0:
        upside = ((target - price) / price) * 100
        if upside >= 20:
            score += 2
            reasons.append(f"✅ Suuri nousuvara tavoitehintaan: +{upside:.0f}%")
        elif upside >= 10:
            score += 1
            reasons.append(f"✅ Kohtalainen nousuvara: +{upside:.0f}%")
        elif upside < -5:
            score -= 1
            reasons.append(f"⚠️  Hinta ylittää tavoitehinnan ({upside:.0f}%)")

    # 3. Sijainti 52 viikon vaihteluvälillä
    low52 = item.get("fifty_two_low")
    high52 = item.get("fifty_two_high")
    if low52 and high52 and price and high52 > low52:
        position = (price - low52) / (high52 - low52)  # 0 = pohja, 1 = huippu
        if position <= 0.25:
            score += 2
            reasons.append(f"✅ Hinta lähellä 52vk pohjia ({position*100:.0f}% vaihteluvälillä)")
        elif position <= 0.40:
            score += 1
            reasons.append(f"✅ Hinta selvästi alle vuosihuipun ({position*100:.0f}% vaihteluvälillä)")
        elif position >= 0.85:
            score -= 1
            reasons.append(f"⚠️  Hinta lähellä 52vk huippuja ({position*100:.0f}% vaihteluvälillä)")

    # 4. Forward P/E vs TTM P/E (odotettu tuloskasvutrendi)
    pe = item.get("trailing_pe")
    fwd_pe = item.get("forward_pe")
    if pe and fwd_pe and pe > 0 and fwd_pe > 0:
        if fwd_pe < pe * 0.80:
            score += 1
            reasons.append(f"✅ Tuloskasvu odotettu: Fwd P/E ({fwd_pe:.1f}) < TTM P/E ({pe:.1f})")
        elif fwd_pe > pe * 1.20:
            score -= 1
            reasons.append(f"⚠️  Tuloslasku odotettu: Fwd P/E ({fwd_pe:.1f}) > TTM P/E ({pe:.1f})")

    # 5. Absoluuttinen P/E — erityisen matala = kiinnostava
    if pe and 0 < pe < 12:
        score += 1
        reasons.append(f"✅ Matala P/E ({pe:.1f}) — mahdollinen aliarvostus")
    elif pe and pe > 50:
        reasons.append(f"ℹ️  Korkea P/E ({pe:.1f}) — kasvuosake tai kallis")

    # Kokonaissignaali — myös myyntisignaalit
    if score >= 4:
        signal = "🟢 OSTA NYT"
        signal_color = "bold green"
    elif score >= 2:
        signal = "🟡 SEURAA"
        signal_color = "yellow"
    elif score >= 0:
        signal = "⚪ NEUTRAALI"
        signal_color = "white"
    elif score == -1:
        signal = "🔴 ODOTA"
        signal_color = "bold red"
    elif score == -2:
        signal = "⚠️ HARKITSE MYYNTIÄ"
        signal_color = "bold red"
    else:
        signal = "🚨 MYYNTISUOSITUS"
        signal_color = "bold red"

    return signal, signal_color, score, reasons


def screen_opportunities(opportunity_stocks=None, min_score=3):
    """
    Screenaa OPPORTUNITY_STOCKS-listalta osakkeet, joilla on vahva ostomahdollisuus.
    Hakee datan ja palauttaa vain ne joiden signaalipistemäärä >= min_score.
    """
    if opportunity_stocks is None:
        opportunity_stocks = OPPORTUNITY_STOCKS

    print("Screenataan ostomahdollisuuksia mahdollisuusuniversumista...")
    hits = []
    for stock in opportunity_stocks:
        try:
            data = fetch_stock_data(stock["symbol"])
            signal, signal_color, score, reasons = compute_signal(data)
            if score >= min_score:
                hits.append((data, stock, signal, score, reasons))
        except Exception:
            pass
    return hits


def format_target_price(target, current_price, currency="EUR"):
    if target is None or current_price is None or current_price <= 0:
        return "N/A"
    curr_symbol = "€" if currency in ["EUR", "eur"] else ("$" if currency in ["USD", "usd"] else currency)
    upside = ((target - current_price) / current_price) * 100
    color = "green" if upside >= 0 else "red"
    return f"{target:.2f} {curr_symbol} ([{color}]{upside:+.1f}%[/{color}])"

def fetch_stock_data(symbol):
    import yfinance as yf
    ticker = yf.Ticker(symbol)
    
    # Haetaan tiedot
    info = {}
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    # Hinta ja muutos
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")
    currency = info.get("currency", "EUR")

    # Jos info ei antanut hintaa, haetaan tuoreimmasta historiasta
    if price is None:
        try:
            hist = ticker.history(period="2d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
                if len(hist) > 1:
                    prev_close = float(hist["Close"].iloc[-2])
        except Exception:
            pass

    # Lasketaan päivän muutos
    change = None
    change_pct = None
    if price is not None and prev_close is not None and prev_close > 0:
        change = price - prev_close
        change_pct = (change / prev_close) * 100

    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "currency": currency,
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "market_cap": info.get("marketCap"),
        "dividend_yield": info.get("dividendYield"),
        "fifty_two_low": info.get("fiftyTwoWeekLow"),
        "fifty_two_high": info.get("fiftyTwoWeekHigh"),
        "target_price": info.get("targetMeanPrice"),
        "recommendation": info.get("recommendationKey"),
    }

def print_rich_table(stock_items):
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text

    console = Console()

    # Otsikkopaneeli
    now_str = datetime.now().strftime("%d.%m.%Y klo %H:%M")
    header_text = Text()
    header_text.append("📊 HUGO PINTA — MARKKINADATA & VALUAATIO-TERMINAALI\n", style="bold cyan")
    header_text.append(f"Päivitetty: {now_str} • Seurannassa: {len(stock_items)} keskeistä osaketta", style="dim")
    console.print(Panel(header_text, border_style="cyan"))

    # Taulukko
    table = Table(title="Osakekurssit, suositukset ja keskeiset kertoimet", border_style="bright_black", header_style="bold bright_white")

    table.add_column("Symboli", style="bold white", no_wrap=True)
    table.add_column("Yhtiö", style="cyan")
    table.add_column("Markkina", style="dim")
    table.add_column("Hinta", justify="right", style="bold white")
    table.add_column("Päivän muutos", justify="right")
    table.add_column("Signaali", justify="center")
    table.add_column("Suositus", justify="center")
    table.add_column("Tavoitehinta", justify="right")
    table.add_column("P/E (TTM)", justify="right")
    table.add_column("Fwd P/E", justify="right")
    table.add_column("Markkina-arvo", justify="right")
    table.add_column("Osinko %", justify="right")
    table.add_column("52 vk vaihtelu", justify="center", style="dim")

    for item, static in stock_items:
        sym = static.get("symbol", item["symbol"])
        name = static.get("name", item["name"])
        ex = static.get("exchange", "")
        curr = item.get("currency", "EUR")

        price_str = format_currency(item.get("price"), curr)

        # Muutosväritys
        chg_pct = item.get("change_pct")
        chg_val = item.get("change")
        if chg_pct is not None:
            sign = "+" if chg_pct >= 0 else ""
            color = "green" if chg_pct >= 0 else "red"
            chg_str = f"[{color}]{sign}{chg_pct:.2f}% ({sign}{chg_val:.2f})[/{color}]"
        else:
            chg_str = "N/A"

        # Sijoitussignaali
        signal, signal_color, score, _ = compute_signal(item)
        signal_str = f"[{signal_color}]{signal}[/{signal_color}]"

        # Suositus (Osta/Myy/Lisää/Vähennä/Pidä)
        rec_text, rec_color = map_recommendation(item.get("recommendation"))
        rec_str = f"[{rec_color}]{rec_text}[/{rec_color}]"

        # Tavoitehinta ja nousuvara
        target_str = format_target_price(item.get("target_price"), item.get("price"), curr)

        pe_str = format_pe(item.get("trailing_pe"))
        fwd_pe_str = format_pe(item.get("forward_pe"))
        mcap_str = format_market_cap(item.get("market_cap"), curr)
        div_str = format_dividend(item.get("dividend_yield"))

        low52 = item.get("fifty_two_low")
        high52 = item.get("fifty_two_high")
        if low52 and high52:
            range52 = f"{low52:.1f} - {high52:.1f}"
        else:
            range52 = "N/A"

        table.add_row(sym, name, ex, price_str, chg_str, signal_str, rec_str, target_str, pe_str, fwd_pe_str, mcap_str, div_str, range52)

    console.print(table)
    console.print()


def print_signals_view(stock_items):
    """Tulostaa yksityiskohtaisen sijoitussignaalianalyysin kaikille osakkeille."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    console = Console()
    now_str = datetime.now().strftime("%d.%m.%Y klo %H:%M")

    console.print()
    console.print(Panel(
        f"[bold yellow]💡 SIJOITUSSIGNAALIANALYYSI[/bold yellow]\n[dim]Päivitetty: {now_str} — Aliarvostus & ostohetki-indikaattorit[/dim]",
        border_style="yellow"
    ))

    # Järjestetään pisteiden mukaan (paras ensin)
    scored = []
    for item, static in stock_items:
        signal, signal_color, score, reasons = compute_signal(item)
        scored.append((score, signal, signal_color, reasons, item, static))
    scored.sort(key=lambda x: x[0], reverse=True)

    for score, signal, signal_color, reasons, item, static in scored:
        sym = static.get("symbol", item["symbol"])
        name = static.get("name", item["name"])
        curr = item.get("currency", "EUR")
        price_str = format_currency(item.get("price"), curr)

        reasons_text = "\n".join(f"  {r}" for r in reasons) if reasons else "  ℹ️  Ei riittävästi dataa analyysiin"

        console.print(Panel(
            f"[bold white]{name} ({sym})[/bold white]  •  Hinta: [bold]{price_str}[/bold]  •  Pisteet: [bold]{score:+d}[/bold]\n\n{reasons_text}",
            title=f"[{signal_color}]{signal}[/{signal_color}]",
            border_style=signal_color if "green" in signal_color else ("yellow" if "yellow" in signal_color else "dim"),
        ))

    console.print("[dim]Huom: Signaali on kvantitatiivinen indikaattori, ei sijoitusneuvonta. Tee aina oma analyysi.[/dim]\n")

def print_detail_view(symbol):
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    console.print(f"[bold cyan]Haetaan syväanalyysia osakkeelle: {symbol}...[/bold cyan]")
    data = fetch_stock_data(symbol)

    curr = data.get("currency", "EUR")
    chg_pct = data.get("change_pct")
    color = "green" if (chg_pct and chg_pct >= 0) else "red"
    sign = "+" if (chg_pct and chg_pct >= 0) else ""

    rec_text, rec_color = map_recommendation(data.get("recommendation"))
    target_str = format_target_price(data.get("target_price"), data.get("price"), curr)

    panel_content = f"""
[bold white]{data['name']} ({symbol})[/bold white]
Hinta: [bold]{format_currency(data['price'], curr)}[/bold]  Muutos: [{color}]{sign}{chg_pct:.2f}%[/{color}]
Markkina-arvo: {format_market_cap(data['market_cap'], curr)}

[bold cyan]Konsensus-suositus & Tavoitehinta:[/bold cyan]
• Suositus: [{rec_color}]{rec_text}[/{rec_color}]
• Analyytikkojen tavoitehinta: {target_str}

[bold cyan]Arvostuskertoimet:[/bold cyan]
• P/E (toteutunut TTM): {format_pe(data['trailing_pe'])}
• Forward P/E (ennustettu): {format_pe(data['forward_pe'])}
• Osinkotuotto: {format_dividend(data['dividend_yield'])}
• 52 viikon vaihteluväli: {format_currency(data['fifty_two_low'], curr)} - {format_currency(data['fifty_two_high'], curr)}
"""
    console.print(Panel(panel_content.strip(), title=f"Yhtiöanalyysi: {symbol}", border_style="cyan"))

def export_markdown_report(stock_items, filename="markkinakatsaus.md"):
    now_str = datetime.now().strftime("%d.%m.%Y klo %H:%M")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Hugo Pinta — Markkinakatsaus\n\n")
        f.write(f"*Päivitetty: {now_str}*\n\n")
        f.write("| Symboli | Yhtiö | Markkina | Hinta | Päivän muutos | Suositus | Tavoitehinta (Upside) | P/E (TTM) | Fwd P/E | Markkina-arvo | Osinko % |\n")
        f.write("| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n")
        for item, static in stock_items:
            sym = static.get("symbol", item["symbol"])
            name = static.get("name", item["name"])
            ex = static.get("exchange", "")
            curr = item.get("currency", "EUR")
            price_str = format_currency(item.get("price"), curr)
            chg = item.get("change_pct")
            chg_str = f"{chg:+.2f} %" if chg is not None else "N/A"
            rec_text, _ = map_recommendation(item.get("recommendation"))
            target_str = format_target_price(item.get("target_price"), item.get("price"), curr)
            # Poistetaan rikkaat väritagipätkät markdownista
            clean_target = target_str.replace("[green]", "").replace("[/green]", "").replace("[red]", "").replace("[/red]", "")
            pe_str = format_pe(item.get("trailing_pe"))
            fwd_pe_str = format_pe(item.get("forward_pe"))
            mcap_str = format_market_cap(item.get("market_cap"), curr)
            div_str = format_dividend(item.get("dividend_yield"))
            f.write(f"| **{sym}** | {name} | {ex} | {price_str} | {chg_str} | **{rec_text}** | {clean_target} | {pe_str} | {fwd_pe_str} | {mcap_str} | {div_str} |\n")
        f.write(f"\n*Raportti generoitu automaattisesti Pythonilla (`uv run tracker.py`).*\n")
    print(f"✅ Markkinakatsaus tallennettu tiedostoon: {filename}")

def fetch_stock_news(symbol, max_items=2):
    """Hakee viimeisimmät uutisotsikoita yfinancesta tietylle osakkeelle."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        news = ticker.news or []
        headlines = []
        for article in news[:max_items]:
            content = article.get("content", {})
            title = content.get("title") or article.get("title", "")
            if title:
                headlines.append(title)
        return headlines
    except Exception:
        return []


def _send_ntfy(title, body, topic="hugo-pinta-markets", tags="chart_with_upwards_trend,bar_chart", priority="high"):
    """Sisäinen apufunktio ntfy-viestin lähettämiseen."""
    import urllib.request
    url = f"https://ntfy.sh/{topic}"
    req = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "Title": title.encode("utf-8"),
            "Priority": priority,
            "Tags": tags,
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print(f"📲 Ilmoitus lähetetty puhelimeen (ntfy: {topic})!")
            else:
                print(f"⚠️  ntfy vastasi tilakoodilla {resp.status}")
    except Exception as e:
        print(f"⚠️  Virhe ilmoituksen lähetyksessä: {e}")


def send_morning_notification(stock_items, topic="hugo-pinta-markets"):
    """
    🌅 AAMULÄHETYS (klo 08:55) — Pörssi aukeaa 5 minuutin päästä!
    Näyttää eilisen sulkukurssit, sijoitussignaalit, myyntivaroitukset ja uudet ostokohteet.
    """
    now_str = datetime.now().strftime("%d.%m.%Y")
    lines = []
    lines.append(f"Pörssi aukeaa klo 09:00 — {now_str}")
    lines.append("")

    # Osakkeet + signaali
    for item, static in stock_items:
        name = static.get("name", item["name"]).split(" ")[0]
        curr = item.get("currency", "EUR")
        price_str = format_currency(item.get("price"), curr)
        signal, _, score, _ = compute_signal(item)
        if score >= 4:
            sig_icon = "🟢"
        elif score >= 2:
            sig_icon = "🟡"
        elif score <= -2:
            sig_icon = "🚨"
        else:
            sig_icon = "⚪"
        rec_text, _ = map_recommendation(item.get("recommendation"))
        lines.append(f"{sig_icon} {name}: {price_str} [{rec_text}]")

    # Myyntivaroitukset omistuksista
    sell_warnings = []
    for item, static in stock_items:
        signal, _, score, reasons = compute_signal(item)
        if score <= -2:
            name_short = static.get("name", item["name"]).split(" ")[0]
            sell_warnings.append(f"  🚨 {name_short}: {signal}")
    if sell_warnings:
        lines.append("")
        lines.append("⚠️ Myyntivaroitukset:")
        lines.extend(sell_warnings)

    # Parhaat ostokohteet omista osakkeista
    buy_list = []
    for item, static in stock_items:
        signal, _, score, _ = compute_signal(item)
        if score >= 2:
            name_short = static.get("name", item["name"]).split(" ")[0]
            buy_list.append(f"  • {name_short}: {signal}")

    # Uudet ostomahdollisuudet mahdollisuusuniversumista
    opportunities = screen_opportunities(min_score=3)
    opp_lines = []
    for data, stock, signal, score, reasons in opportunities:
        name_short = stock.get("name", data["name"]).split(" ")[0]
        curr = data.get("currency", "EUR")
        price_str = format_currency(data.get("price"), curr)
        target = data.get("target_price")
        price = data.get("price")
        upside_str = ""
        if target and price and price > 0:
            upside = ((target - price) / price) * 100
            upside_str = f" ↗ +{upside:.0f}%"
        opp_lines.append(f"  🎯 {name_short}: {price_str}{upside_str} [{signal}]")

    if buy_list or opp_lines:
        lines.append("")
        lines.append("💡 Tänään seuraa:")
        lines.extend(buy_list)
        if opp_lines:
            lines.append("")
            lines.append("🆕 Uudet ostomahdollisuudet:")
            lines.extend(opp_lines)
    else:
        lines.append("")
        lines.append("💡 Ei erityisiä signaaleita tänään")

    _send_ntfy(
        title=f"🌅 Pörssiaamun katsaus • {now_str}",
        body="\n".join(lines),
        topic=topic,
        tags="sunrise,chart_with_upwards_trend",
        priority="high"
    )


def send_evening_notification(stock_items, topic="hugo-pinta-markets"):
    """
    🌆 ILTAKATSAUS (klo 17:35) — Päivän yhteenveto.
    Voittajat & häviäjät, uutisselitykset, myyntivaroitukset ja uudet ostokohteet.
    """
    now_str = datetime.now().strftime("%d.%m.%Y")
    lines = []

    # Lajitellaan päivän muutoksen mukaan
    sorted_items = sorted(stock_items, key=lambda x: x[0].get("change_pct") or 0, reverse=True)
    winners = [(i, s) for i, s in sorted_items if (i.get("change_pct") or 0) >= 0.5]
    losers  = [(i, s) for i, s in sorted_items if (i.get("change_pct") or 0) <= -0.5]
    flat    = [(i, s) for i, s in sorted_items if abs(i.get("change_pct") or 0) < 0.5]

    if winners:
        lines.append("📈 Päivän nousijat:")
        for item, static in winners:
            name = static.get("name", item["name"]).split(" ")[0]
            curr = item.get("currency", "EUR")
            chg = item.get("change_pct", 0)
            price_str = format_currency(item.get("price"), curr)
            lines.append(f"  🟢 {name}: {price_str} ({chg:+.1f}%)")

    if losers:
        lines.append("")
        lines.append("📉 Päivän laskijat:")
        for item, static in losers:
            name = static.get("name", item["name"]).split(" ")[0]
            curr = item.get("currency", "EUR")
            chg = item.get("change_pct", 0)
            price_str = format_currency(item.get("price"), curr)
            lines.append(f"  🔴 {name}: {price_str} ({chg:+.1f}%)")

    if flat:
        lines.append("")
        lines.append("➡️  Tasainen päivä:")
        flat_names = [static.get("name", item["name"]).split(" ")[0] for item, static in flat]
        lines.append(f"  {', '.join(flat_names)}")

    # Uutisotsikoita isommille liikkeille (>1.5% muutos)
    significant = [(i, s) for i, s in stock_items if abs(i.get("change_pct") or 0) >= 1.5]
    if significant:
        news_lines = []
        for item, static in significant[:3]:
            sym = static.get("symbol", item["symbol"])
            name = static.get("name", item["name"]).split(" ")[0]
            headlines = fetch_stock_news(sym, max_items=1)
            if headlines:
                news_lines.append(f"  📰 {name}: {headlines[0][:80]}")
        if news_lines:
            lines.append("")
            lines.append("🗞️  Päivän uutiset:")
            lines.extend(news_lines)

    # Myyntivaroitukset omistuksista
    sell_warnings = []
    for item, static in stock_items:
        signal, _, score, reasons = compute_signal(item)
        if score <= -2:
            name_short = static.get("name", item["name"]).split(" ")[0]
            # Lyhyin selitys myyntisignaalin syystä
            top_reason = next((r for r in reasons if "⚠️" in r), "")
            sell_warnings.append(f"  🚨 {name_short}: {signal}")
            if top_reason:
                sell_warnings.append(f"     {top_reason.strip()}")

    if sell_warnings:
        lines.append("")
        lines.append("⚠️ MYYNTIVAROITUKSET (omistuksistasi):")
        lines.extend(sell_warnings)

    # Sijoitussignaalit omistuksista
    buy_signals = []
    for item, static in stock_items:
        signal, _, score, _ = compute_signal(item)
        if score >= 2:
            name_short = static.get("name", item["name"]).split(" ")[0]
            rec_text, _ = map_recommendation(item.get("recommendation"))
            buy_signals.append(f"  {signal} {name_short} [{rec_text}]")

    if buy_signals:
        lines.append("")
        lines.append("💡 Sijoitussignaalit (omat):")
        lines.extend(buy_signals)

    # Uudet ostomahdollisuudet mahdollisuusuniversumista
    opportunities = screen_opportunities(min_score=3)
    if opportunities:
        lines.append("")
        lines.append("🎯 Uudet ostomahdollisuudet:")
        for data, stock, signal, score, reasons in opportunities:
            name_short = stock.get("name", data["name"]).split(" ")[0]
            curr = data.get("currency", "EUR")
            price_str = format_currency(data.get("price"), curr)
            target = data.get("target_price")
            price = data.get("price")
            upside_str = ""
            if target and price and price > 0:
                upside = ((target - price) / price) * 100
                upside_str = f" ↗ +{upside:.0f}%"
            lines.append(f"  🟢 {name_short}: {price_str}{upside_str} [{signal}]")

    _send_ntfy(
        title=f"🌆 Päivän pörssikatsaus • {now_str}",
        body="\n".join(lines),
        topic=topic,
        tags="bar_chart,bell",
        priority="default"
    )


def send_ntfy_notification(stock_items, topic="hugo-pinta-markets"):
    """Perus push-ilmoitus (yhteensopivuus vanhaan --notify flagiin)."""
    now_str = datetime.now().strftime("%d.%m. klo %H:%M")
    lines = []

    for item, static in stock_items:
        name = static.get("name", item["name"]).split(" ")[0]
        curr = item.get("currency", "EUR")
        price_str = format_currency(item.get("price"), curr)
        chg = item.get("change_pct")
        icon = ("🟢" if chg >= 0 else "🔴") if chg is not None else "⚪️"
        chg_str = f"{chg:+.1f}%" if chg is not None else ""
        rec_text, _ = map_recommendation(item.get("recommendation"))
        target = item.get("target_price")
        price = item.get("price")
        target_info = ""
        if target and price and price > 0:
            upside = ((target - price) / price) * 100
            target_info = f" ↗ {target:.1f} ({upside:+.0f}%)"
        lines.append(f"{icon} {name}: {price_str} ({chg_str}) [{rec_text}]{target_info}")

    buy_signals = []
    for item, static in stock_items:
        signal, _, score, _ = compute_signal(item)
        if score >= 2:
            name_short = static.get("name", item["name"]).split(" ")[0]
            buy_signals.append(f"💡 {name_short}: {signal}")
    if buy_signals:
        lines.append("")
        lines.append("— Sijoitussignaalit —")
        lines.extend(buy_signals)

    _send_ntfy(
        title=f"Pörssikatsaus • {now_str}",
        body="\n".join(lines),
        topic=topic
    )

def main():
    parser = argparse.ArgumentParser(description="Hugo Pinta Markkinadata & Osakeseuranta")
    parser.add_argument("--detail", "-d", type=str, help="Näytä syväanalyysi tietylle osakesymbolille (esim. NVDA tai NESTE.HE)")
    parser.add_argument("--export", "-e", action="store_true", help="Vie markkinakatsaus Markdown-tiedostoon (markkinakatsaus.md)")
    parser.add_argument("--notify", "-n", action="store_true", help="Lähetä perus push-ilmoitus puhelimeen (ntfy.sh)")
    parser.add_argument("--morning", action="store_true", help="🌅 Lähetä aamulähetys — pörssi aukeaa 5min päästä")
    parser.add_argument("--evening", action="store_true", help="🌆 Lähetä iltakatsaus — päivän yhteenveto, voittajat & häviäjät, uutiset")
    parser.add_argument("--add", "-a", type=str, help="Lisää uusi symboli tilapäisesti mukaan seurantaan")
    parser.add_argument("--signals", "-s", action="store_true", help="Näytä yksityiskohtainen sijoitussignaalianalyysi (aliarvostus & ostohetki)")
    args = parser.parse_args()

    # Tarkistetaan asennetut paketit
    try:
        import yfinance
        import rich
    except ImportError:
        print("⚠️  Puuttuvia paketteja. Aja komento `uv add yfinance rich` tai suorita ohjelma komennolla:")
        print("   uv run tracker.py")
        sys.exit(1)

    if args.detail:
        print_detail_view(args.detail)
        return

    stocks_to_track = list(DEFAULT_STOCKS)
    if args.add:
        stocks_to_track.append({"symbol": args.add, "name": args.add, "exchange": "Custom"})

    print("Haetaan tuoreimmat kurssit ja kertoimet markkinoilta...")
    results = []
    for stock in stocks_to_track:
        data = fetch_stock_data(stock["symbol"])
        results.append((data, stock))

    print_rich_table(results)

    if args.signals:
        print_signals_view(results)

    if args.morning:
        send_morning_notification(results)
    elif args.evening:
        send_evening_notification(results)
    elif args.notify:
        send_ntfy_notification(results)

    if args.export:
        export_markdown_report(results)

if __name__ == "__main__":
    main()
