import os
import base64
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.pdfgen import canvas
from io import BytesIO

# Company info
COMPANY_NAME = os.getenv("COMPANY_NAME", "ISIBI Voice AI")
COMPANY_EMAIL = os.getenv("COMPANY_EMAIL", "support@isibi.com")
COMPANY_PHONE = os.getenv("COMPANY_PHONE", "+1 (555) 123-4567")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "123 AI Street, Tech City, TC 12345")


def generate_invoice_pdf(
    customer_email: str,
    customer_name: str,
    amount: float,
    transaction_id: str,
    is_auto_recharge: bool = False
) -> bytes:
    """
    Generate a professional PDF invoice
    
    Returns:
        bytes: PDF file content
    """
    # Create PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#4F46E5'),
        spaceAfter=30,
    )
    
    # Invoice details
    invoice_date = datetime.now().strftime("%B %d, %Y")
    invoice_number = transaction_id or f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    invoice_type = "Auto-Recharge Receipt" if is_auto_recharge else "Invoice"
    
    # Header
    elements.append(Paragraph(COMPANY_NAME, title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Company info
    company_info = f"""
    <font size=10>
    {COMPANY_EMAIL}<br/>
    {COMPANY_PHONE}<br/>
    {COMPANY_ADDRESS}
    </font>
    """
    elements.append(Paragraph(company_info, styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))
    
    # Invoice title
    invoice_title = f"<font size=16 color='#4F46E5'><b>{invoice_type}</b></font>"
    elements.append(Paragraph(invoice_title, styles['Normal']))
    elements.append(Spacer(1, 0.2*inch))
    
    # Invoice details table
    invoice_data = [
        ['Invoice Number:', invoice_number],
        ['Invoice Date:', invoice_date],
        ['Bill To:', customer_name],
        ['Email:', customer_email],
    ]
    
    invoice_table = Table(invoice_data, colWidths=[2*inch, 4*inch])
    invoice_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(invoice_table)
    elements.append(Spacer(1, 0.4*inch))
    
    # Auto-recharge note
    if is_auto_recharge:
        auto_recharge_text = """
        <font size=10 color='#856404'>
        <b>⚡ Auto-Recharge:</b> Your balance dropped below $2.00, so we automatically 
        added credits using your saved payment method.
        </font>
        """
        elements.append(Paragraph(auto_recharge_text, styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))
    
    # Line items table
    line_items_data = [
        ['Description', 'Quantity', 'Unit Price', 'Amount'],
        ['ISIBI Voice AI Credits', '1', f'${amount:.2f}', f'${amount:.2f}'],
    ]
    
    line_items_table = Table(line_items_data, colWidths=[3*inch, 1*inch, 1.5*inch, 1.5*inch])
    line_items_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F46E5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(line_items_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Total section
    total_data = [
        ['Subtotal:', f'${amount:.2f}'],
        ['Tax:', '$0.00'],
        ['Total:', f'${amount:.2f}'],
    ]
    
    total_table = Table(total_data, colWidths=[5*inch, 2*inch])
    total_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('LINEABOVE', (0, 2), (-1, 2), 2, colors.HexColor('#4F46E5')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#E8F5E9')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(total_table)
    elements.append(Spacer(1, 0.4*inch))
    
    # Payment info
    payment_info = f"""
    <font size=10>
    <b>Payment Method:</b> Credit Card<br/>
    <b>Transaction ID:</b> {transaction_id}<br/>
    <b>Status:</b> <font color='green'>PAID</font>
    </font>
    """
    elements.append(Paragraph(payment_info, styles['Normal']))
    elements.append(Spacer(1, 0.4*inch))
    
    # Footer
    footer_text = """
    <font size=9 color='#666'>
    Thank you for your business!<br/>
    <br/>
    Your credits have been added to your account and are ready to use.<br/>
    <br/>
    If you have any questions about this invoice, please contact us at {email}
    </font>
    """.format(email=COMPANY_EMAIL)
    elements.append(Paragraph(footer_text, styles['Normal']))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes


def generate_invoice_filename(invoice_number: str) -> str:
    """Generate a clean filename for the invoice"""
    return f"Invoice_{invoice_number}.pdf"
