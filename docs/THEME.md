# Theme „Phoenix Contact“

Der HTML-Bericht nutzt standardmäßig das Theme `phoenix` (`pcpoc/theme_phoenix.css`). Mit `--theme neutral` entfällt es.

| Element | Quelle | Wert |
|---|---|---|
| Signalkette mit Logo im Kopf | `pcpoc/assets/signal-chain.svg`, Grafik von phoenixcontact.com | – |
| Petrol (Primärakzent, Forecast-Linie, KPI-Kanten) | aus der Signalkette | `#009BA3` (Text/Hover abgedunkelt `#007A81`) |
| Grün (Empfehlung, Hervorhebung) | aus der Signalkette | `#93C11C` (Linien abgedunkelt `#6A8C14`) |
| Dunkelgrau für Text und Navigation | Screenshot der Navigation | `#333333` |
| Navigation und Überschriften in fetten Versalien | Screenshot der Navigation | – |
| Token-Namen `--color-blue`, `--color-gray-800`, `--default-border` | HTML der Startseite | übernommen |
| Hausschrift | **nicht ermittelt**: Die Stylesheets der Website liefern bei automatisiertem Abruf 403 | Ersatz: Roboto, sonst Arial |

Um die Hausschrift nachzutragen, trägt man sie unter `--font` in `theme_phoenix.css` ein. Damit sie offline funktioniert, muss die Schrift auf den Rechnern installiert sein. Ein Einbetten der Schriftdatei ist nur nach Klärung der Lizenz sinnvoll.

Logo und Markenelemente stammen von Phoenix Contact. Sie werden ausschließlich im Bericht für Phoenix Contact verwendet.
