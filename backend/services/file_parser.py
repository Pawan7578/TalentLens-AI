import io
import logging
from pdfminer.high_level import extract_text as pdf_extract
from docx import Document

logger = logging.getLogger(__name__)

# OCR imports (optional)
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.warning("pytesseract/PIL not available — OCR fallback disabled")


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF file. Falls back to OCR if text extraction yields < 50 chars."""
    try:
        text = pdf_extract(io.BytesIO(file_bytes))
        logger.info(f"PDF text extraction: {len(text)} chars")
        
        # Fallback to OCR if insufficient text
        if len(text.strip()) < 50:
            logger.info("PDF text < 50 chars, attempting OCR fallback")
            if OCR_AVAILABLE:
                return extract_text_from_pdf_ocr(file_bytes)
            else:
                logger.warning("OCR not available, returning empty extraction")
        
        return text
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        if OCR_AVAILABLE:
            logger.info("Attempting OCR fallback for PDF")
            try:
                return extract_text_from_pdf_ocr(file_bytes)
            except Exception as ocr_error:
                logger.error(f"OCR fallback failed: {ocr_error}")
                raise ValueError(f"Failed to parse PDF (extraction + OCR): {str(e)}")
        raise ValueError(f"Failed to parse PDF: {str(e)}")


def extract_text_from_pdf_ocr(file_bytes: bytes) -> str:
    """Extract text from PDF using OCR (pytesseract + Pillow)."""
    if not OCR_AVAILABLE:
        raise ValueError("OCR not available")
    
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(file_bytes)
        text_parts = []
        for i, image in enumerate(images):
            logger.info(f"OCR processing page {i+1}/{len(images)}")
            text = pytesseract.image_to_string(image)
            text_parts.append(text)
        result = "\n".join(text_parts)
        logger.info(f"OCR extraction: {len(result)} chars")
        return result
    except ImportError:
        raise ValueError("pdf2image not installed (required for PDF OCR)")
    except Exception as e:
        raise ValueError(f"OCR processing failed: {str(e)}")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract plain text from a DOCX file."""
    try:
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        logger.info(f"DOCX extraction: {len(text)} chars")
        return text
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        raise ValueError(f"Failed to parse DOCX: {str(e)}")


def extract_text(filename: str, file_bytes: bytes) -> str:
    """Route to the correct parser based on file extension."""
    lower = filename.lower()
    logger.info(f"Extracting text from {filename} ({len(file_bytes)} bytes)")
    
    if lower.endswith(".pdf"):
        return extract_text_from_pdf(file_bytes)
    elif lower.endswith(".docx"):
        return extract_text_from_docx(file_bytes)
    elif lower.endswith(".txt"):
        text = file_bytes.decode("utf-8", errors="ignore")
        logger.info(f"TXT extraction: {len(text)} chars")
        return text
    else:
        raise ValueError(f"Unsupported file type: {filename}")