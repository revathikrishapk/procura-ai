import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

def send_po_email(to_email: str, po_number: str, pdf_path: str, vendor_name: str) -> bool:
    """Sends the generated Purchase Order PDF as an email attachment via SMTP."""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    # Fallback dry-run mode if SMTP credentials are not set in environment
    if not smtp_user or not smtp_password:
        print(f"[MOCK EMAIL] Simulating email delivery for {po_number} to {to_email}")
        return True

    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = to_email
    msg['Subject'] = f"New Purchase Order: {po_number} - Procura AI"

    body = f"""Dear {vendor_name} Sales Team,

Please find attached Purchase Order {po_number} for immediate processing.

Best regards,
Automated Procurement Engine
Procura AI
"""
    msg.attach(MIMEText(body, 'plain'))

    # Attach PDF Document
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
            pdf_attachment.add_header('Content-Disposition', 'attachment', filename=f"{po_number}.pdf")
            msg.attach(pdf_attachment)

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send email: {e}")
        return False