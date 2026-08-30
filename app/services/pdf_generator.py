import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

PO_OUTPUT_DIR = "generated_pos"

def create_purchase_order_pdf(po_number: str, spec: dict, comparison: dict) -> str:
    """Generates a professional PDF Purchase Order and returns the file path."""
    os.makedirs(PO_OUTPUT_DIR, exist_ok=True)
    file_path = os.path.join(PO_OUTPUT_DIR, f"{po_number}.pdf")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=22,
        leading=26,
        textColor=colors.HexColor('#1E293B')
    )
    bold_style = ParagraphStyle(
        'BoldText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14
    )

    story = []

    # 1. Document Header
    story.append(Paragraph("PURCHASE ORDER", title_style))
    story.append(Spacer(1, 10))

    header_data = [
        [
            Paragraph(f"<b>PO Number:</b> {po_number}<br/><b>Date:</b> 2026-08-19", styles['Normal']),
            Paragraph(f"<b>Vendor:</b> {comparison.get('recommended_vendor', 'N/A')}<br/><b>Terms:</b> {comparison.get('contract_terms', 'Net-30')}", styles['Normal'])
        ]
    ]
    header_table = Table(header_data, colWidths=[260, 270])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('PADDING', (0, 0), (-1, -1), 10),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 20))

    # 2. Line Items Table
    item_title = comparison.get('product_title', spec.get('item_name', 'Requested Item'))
    qty = spec.get('quantity', 1)
    unit_price = comparison.get('unit_price', 0.0)
    total_cost = comparison.get('total_cost', 0.0)

    items_data = [
        ["Line Item / Description", "Qty", "Unit Price", "Total Cost"],
        [item_title, str(qty), f"${unit_price:,.2f}", f"${total_cost:,.2f}"]
    ]

    items_table = Table(items_data, colWidths=[270, 60, 100, 100])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 20))

    # 3. Footer Approval & Sign-off
    story.append(Paragraph("<b>Approved by:</b> Procura AI Automated Engine", bold_style))
    story.append(Paragraph(f"<b>Source Verification:</b> {comparison.get('source', 'Internal System')}", styles['Normal']))

    doc.build(story)
    return file_path