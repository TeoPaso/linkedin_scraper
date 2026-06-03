import re

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_func_pattern = r"def send_email_report\(matched_jobs: list, metrics: dict\):.*?msg\.attach\(MIMEText\(html_content, \"html\"\)\)"
match = re.search(old_func_pattern, content, flags=re.DOTALL)
if not match:
    print("Could not find send_email_report function.")
    exit(1)

old_func = match.group(0)

new_func = '''def send_email_report(matched_jobs: list, metrics: dict):
    """Invia un'email di recap se ci sono offerte interessanti."""
    if not config.get("email", {}).get("send_email", True):
        return

    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    recipient = os.environ.get("EMAIL_RECIPIENT")

    if not sender or not password or not recipient:
        print("[!] Credenziali email mancanti, salto invio email.")
        return

    today_str = datetime.now().strftime("%d/%m/%Y")

    total_matched = metrics.get("total_above_threshold", 0)
    total_found = metrics.get("total_found", 0)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = (
        f"LinkedIn Job Report — {today_str} — {total_matched} job matched/{total_found} trovati"
    )
    msg["From"] = sender
    msg["To"] = recipient

    html_content = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6; max-width: 800px; margin: auto;">
        <h2 style="color: #0a66c2; border-bottom: 2px solid #0a66c2; padding-bottom: 10px;">LinkedIn Job Report</h2>
        
        <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0a66c2;">
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px 0; width: 60%;"><strong>Totale offerte passate al setaccio (inclusi duplicati passati):</strong></td><td>{total_found}</td></tr>
                <tr><td style="padding: 4px 0;"><strong>Nuovi job effettivamente analizzati oggi (il tuo Target):</strong></td><td>{metrics.get("new_jobs_today", "N/A")}</td></tr>
                <tr><td style="padding: 4px 0;"><strong>Nuovi job promossi (Sopra la soglia Min Fit):</strong></td><td>{total_matched}</td></tr>
                <tr><td style="padding: 4px 0;"><strong>Iterazioni effettuate:</strong></td><td>{metrics.get("iterations", 0)}</td></tr>
                <tr><td style="padding: 4px 0;"><strong>Keyword migliore:</strong></td><td><code>{metrics.get("best_keyword", "N/A")}</code></td></tr>
                <tr><td style="padding: 4px 0;"><strong>Fit score medio:</strong></td><td>{round(metrics.get("avg_fit_score", 0), 1)}/100</td></tr>
            </table>
        </div>
        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
    """

    if not matched_jobs:
        html_content += "<p style='color: #666; font-style: italic;'>Nessuna nuova offerta ha superato la soglia minima per oggi.</p>"
    else:
        top_picks = [j for j in matched_jobs if j["score"] >= 80]
        other_valid = [j for j in matched_jobs if j["score"] < 80]

        def generate_job_html(item):
            job = item["job"]
            title = job.get("title", "Titolo Sconosciuto")
            company = job.get("companyName", "Azienda Sconosciuta")
            url = job.get("link", "#")
            score = item["score"]
            reasoning = item["reasoning"]

            if score >= 90:
                icon = "🏆"
                color = "#b8860b" # dark gold for text
                border_color = "#ffd700"
                bg_color = "#fffdf0"
            elif score >= 80:
                icon = "⭐"
                color = "#2e7d32"
                border_color = "#2e7d32"
                bg_color = "#f2fcf3"
            elif score >= 70:
                icon = "✓"
                color = "#f57c00"
                border_color = "#e0e0e0"
                bg_color = "#ffffff"
            else:
                icon = "❌"
                color = "#d32f2f"
                border_color = "#e0e0e0"
                bg_color = "#ffffff"

            return f"""
            <div style="margin-bottom: 25px; padding: 20px; border: 1px solid {border_color}; border-radius: 8px; background-color: {bg_color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <h3 style="margin-top: 0; margin-bottom: 8px; font-size: 18px;">
                    <span style="margin-right: 5px;">{icon}</span>
                    <a href="{url}" style="color: #0a66c2; text-decoration: none;">{title}</a> 
                    <span style="color: #666; font-weight: normal; font-size: 16px;">presso {company}</span>
                    <span style="float: right; font-size: 14px; font-weight: 600; color: {color};">Score: {score}/100</span>
                </h3>
                <div style="padding-top: 8px;">
                    <span style="color: #555; font-size: 14px; line-height: 1.5;">{reasoning}</span>
                </div>
            </div>
            """

        if top_picks:
            html_content += "<h3>🏆 Top Picks (Fascia A & Golden)</h3><div style='margin-top: 20px;'>"
            for item in top_picks:
                html_content += generate_job_html(item)
            html_content += "</div>"
        
        if other_valid:
            html_content += "<hr style='border: 0; border-top: 1px dashed #ccc; margin: 30px 0;'>"
            html_content += "<h3>✓ Altre Posizioni Valide (Fascia B)</h3><div style='margin-top: 20px;'>"
            for item in other_valid:
                html_content += generate_job_html(item)
            html_content += "</div>"

    dashboard_url = os.environ.get("DASHBOARD_URL", "https://teopaso.github.io/linkedin_scraper/")

    html_content += f"""
        <p style="font-size: 14px; color: #888; text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eaeaea;">
            Report completo disponibile nella <a href="{dashboard_url}" style="color: #0a66c2; text-decoration: none; font-weight: bold;">Dashboard</a>.
        </p>
    """

    html_content += """
    </body>
    </html>
    """

    msg.attach(MIMEText(html_content, "html"))'''

content = content.replace(old_func, new_func)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("SUCCESS")
