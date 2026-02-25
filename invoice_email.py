import os
from datetime import datetime

# Email configuration - uses same setup as password_reset
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SMTP_FROM = os.getenv("SMTP_FROM", "ISIBI Support <noreply@isibi.com>")

# Try importing SendGrid
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    SENDGRID_AVAILABLE = True
except ImportError:
    SENDGRID_AVAILABLE = False


def send_invoice_email(
    email: str,
    amount: float,
    transaction_type: str,
    payment_method: str = "Credit Card",
    transaction_id: str = None,
    is_auto_recharge: bool = False
) -> dict:
    """
    Send invoice email for credit purchase or auto-recharge with PDF attachment
    
    Args:
        email: Customer email
        amount: Amount in dollars
        transaction_type: "purchase" or "auto_recharge"
        payment_method: Payment method used
        transaction_id: Transaction/payment ID
        is_auto_recharge: Whether this is an auto-recharge
    
    Returns:
        {"success": bool, "error": str (if failed)}
    """
    if not SENDGRID_AVAILABLE or not SENDGRID_API_KEY:
        print("⚠️ SendGrid not configured - invoice email skipped")
        return {"success": False, "error": "Email not configured"}
    
    try:
        # Generate invoice details
        invoice_date = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        invoice_number = transaction_id or f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Set subject and title based on type
        if is_auto_recharge:
            subject = f"Auto-Recharge Receipt - ${amount:.2f} Credits Added"
            title = "Auto-Recharge Receipt"
        else:
            subject = f"Invoice for ${amount:.2f} Credits Purchase"
            title = "Purchase Receipt"
        
        # Create HTML email
        html = get_invoice_html(
            amount=amount,
            invoice_date=invoice_date,
            invoice_number=invoice_number,
            payment_method=payment_method,
            is_auto_recharge=is_auto_recharge,
            title=title
        )
        
        # Generate PDF invoice
        from invoice_pdf import generate_invoice_pdf, generate_invoice_filename
        
        # Get customer name from email (first part before @)
        customer_name = email.split('@')[0].title()
        
        pdf_bytes = generate_invoice_pdf(
            customer_email=email,
            customer_name=customer_name,
            amount=amount,
            transaction_id=invoice_number,
            is_auto_recharge=is_auto_recharge
        )
        
        pdf_filename = generate_invoice_filename(invoice_number)
        
        # Encode PDF as base64 for SendGrid
        import base64
        pdf_base64 = base64.b64encode(pdf_bytes).decode()
        
        # Send via SendGrid with attachment
        message = Mail(
            from_email=SMTP_FROM,
            to_emails=email,
            subject=subject,
            html_content=html
        )
        
        # Attach PDF
        from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition
        
        attachment = Attachment(
            FileContent(pdf_base64),
            FileName(pdf_filename),
            FileType('application/pdf'),
            Disposition('attachment')
        )
        message.attachment = attachment
        
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        
        print(f"✅ Invoice email sent to {email} - ${amount:.2f} (PDF attached: {pdf_filename})")
        return {"success": True}
    
    except Exception as e:
        print(f"❌ Failed to send invoice email: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def get_invoice_html(
    amount: float,
    invoice_date: str,
    invoice_number: str,
    payment_method: str,
    is_auto_recharge: bool,
    title: str
) -> str:
    """Generate HTML invoice email"""
    
    auto_recharge_note = ""
    if is_auto_recharge:
        auto_recharge_note = """
        <div style="background: #FFF3CD; border-left: 4px solid #FFC107; padding: 15px; margin: 20px 0;">
            <p style="margin: 0; color: #856404;">
                <strong>⚡ Auto-Recharge:</strong> Your balance dropped below $2.00, so we automatically added credits using your saved payment method.
            </p>
        </div>
        """
    
    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; background: #f5f5f5; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 28px; }}
        .content {{ padding: 30px; }}
        .invoice-box {{ background: #f9f9f9; border: 1px solid #e0e0e0; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .invoice-row {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #e0e0e0; }}
        .invoice-row:last-child {{ border-bottom: none; }}
        .invoice-label {{ font-weight: 600; color: #666; }}
        .invoice-value {{ color: #333; }}
        .total-row {{ background: #4F46E5; color: white; padding: 15px; border-radius: 5px; margin-top: 20px; }}
        .total-row .invoice-row {{ border-bottom: none; }}
        .total-row .invoice-label, .total-row .invoice-value {{ color: white; font-size: 18px; font-weight: bold; }}
        .footer {{ background: #f9f9f9; padding: 20px; text-align: center; color: #666; font-size: 12px; }}
        .button {{ display: inline-block; padding: 12px 30px; background: #FFC107; color: #000; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; }}
        .divider {{ height: 1px; background: #e0e0e0; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>💳 {title}</h1>
            <p style="margin: 10px 0 0 0; opacity: 0.9;">ISIBI Voice AI Platform</p>
        </div>
        
        <div class="content">
            {auto_recharge_note}
            
            <p>Hello,</p>
            <p>Thank you for your payment! Here's your receipt for the credits added to your account.</p>
            
            <div class="invoice-box">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: #4F46E5;">Invoice #{invoice_number}</h3>
                    <p style="margin: 5px 0 0 0; color: #666;">{invoice_date}</p>
                </div>
                
                <div class="divider"></div>
                
                <div class="invoice-row">
                    <span class="invoice-label">Description</span>
                    <span class="invoice-value">ISIBI Voice AI Credits</span>
                </div>
                
                <div class="invoice-row">
                    <span class="invoice-label">Credits Added</span>
                    <span class="invoice-value">${amount:.2f}</span>
                </div>
                
                <div class="invoice-row">
                    <span class="invoice-label">Payment Method</span>
                    <span class="invoice-value">{payment_method}</span>
                </div>
                
                <div class="total-row">
                    <div class="invoice-row">
                        <span class="invoice-label">Total Paid</span>
                        <span class="invoice-value">${amount:.2f} USD</span>
                    </div>
                </div>
            </div>
            
            <p style="text-align: center;">
                <a href="https://isibi-control-hub.lovable.app/dashboard" class="button">View Dashboard</a>
            </p>
            
            <div style="background: #E8F5E9; border-left: 4px solid #4CAF50; padding: 15px; margin: 20px 0;">
                <p style="margin: 0; color: #2E7D32;">
                    <strong>✅ Credits Active:</strong> Your ${amount:.2f} in credits are now available in your account and ready to use!
                </p>
            </div>
            
            <p style="color: #666; font-size: 14px;">Questions about this charge? Reply to this email or contact our support team.</p>
        </div>
        
        <div class="footer">
            <p><strong>ISIBI Voice AI Platform</strong></p>
            <p>Invoice #{invoice_number}</p>
            <p style="margin-top: 15px;">This is an automated receipt. Please do not reply to this email.</p>
        </div>
    </div>
</body>
</html>
"""


def send_low_balance_warning(email: str, current_balance: float) -> dict:
    """
    Send warning email when balance is low
    
    Args:
        email: Customer email
        current_balance: Current balance
    
    Returns:
        {"success": bool, "error": str (if failed)}
    """
    if not SENDGRID_AVAILABLE or not SENDGRID_API_KEY:
        return {"success": False, "error": "Email not configured"}
    
    try:
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: #FF9800; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 5px 5px; }}
        .warning-box {{ background: #FFF3CD; border-left: 4px solid #FF9800; padding: 15px; margin: 20px 0; }}
        .button {{ display: inline-block; padding: 12px 30px; background: #FFC107; color: #000; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚠️ Low Balance Alert</h1>
        </div>
        <div class="content">
            <p>Hello,</p>
            <p>Your ISIBI Voice AI account balance is running low.</p>
            
            <div class="warning-box">
                <p style="margin: 0; font-size: 18px; font-weight: bold; color: #856404;">
                    Current Balance: ${current_balance:.2f}
                </p>
            </div>
            
            <p>To avoid service interruption, please add credits to your account.</p>
            
            <p style="text-align: center;">
                <a href="https://isibi-control-hub.lovable.app/dashboard" class="button">Add Credits Now</a>
            </p>
            
            <p><strong>💡 Tip:</strong> Enable auto-recharge to automatically add credits when your balance drops below $2.00.</p>
        </div>
    </div>
</body>
</html>
"""
        
        message = Mail(
            from_email=SMTP_FROM,
            to_emails=email,
            subject="⚠️ Low Balance Alert - Add Credits",
            html_content=html
        )
        
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        
        print(f"✅ Low balance warning sent to {email}")
        return {"success": True}
    
    except Exception as e:
        print(f"❌ Failed to send warning email: {e}")
        return {"success": False, "error": str(e)}
