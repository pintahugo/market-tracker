# Hugo Pinta — Markkinadata & Osakeseurantatyökalu 📊

Tämä on Pythonilla ja `uv`-työkalulla toteutettu rahoitus- ja osakeseurantatyökalu, joka hakee reaaliaikaiset markkinakurssit ja keskeiset valuaatiokertoimet.

## Seurattavat osakkeet
1. **Neste Oyj** (`NESTE.HE` - Helsinki)
2. **UPM-Kymmene Oyj** (`UPM.HE` - Helsinki)
3. **NVIDIA Corporation** (`NVDA` - NASDAQ)
4. **Iren / Iris Energy** (`IREN` - NASDAQ)
5. **Nordea Bank Abp** (`NDA-FI.HE` - Helsinki)
6. **Huhtamäki Oyj** (`HUH1V.HE` - Helsinki)

## Käynnistys
Aja projektin kansiossa:
```bash
uv run tracker.py
```

### Lisätoiminnot:
- **Syväanalyysi tietystä osakkeesta:**
  ```bash
  uv run tracker.py --detail NVDA
  uv run tracker.py --detail NESTE.HE
  ```
- **Tallenna markkinakatsaus tiedostoon (Markdown):**
  ```bash
  uv run tracker.py --export
  ```
- **Lisää tilapäisesti uusi osake seurantaan:**
  ```bash
  uv run tracker.py --add AAPL
  ```
