# 💰 Smart Cash Flow OCR

Smart Cash Flow OCR is a tool designed to process bank transaction documents (PDF) using OCR technology (Typhoon OCR & Tesseract) and manage the data in a local SQLite database with a user-friendly Streamlit dashboard.

---

## 🌟 Features
- **OCR Processing**: Automatically extract transaction details from bank PDFs.
- **Database Management**: Store and manage historical data in SQLite.
- **Manual Entry**: Efficiently add or correct records manually with auto-formatting.
- **Reports**: Generate Bank Statements and Balance Summary reports in Excel.
- **Filters**: Advanced filtering by Account, Bank, Company, Currency, and Date.

---

## 🚀 Quick Setup | วิธีติดตั้งเบื้องต้น

### Prerequisites (English)
1. **Python 3.10+**: [Download here](https://www.python.org/downloads/)
2. **Tesseract OCR**: [Windows Installer](https://github.com/UB-Mannheim/tesseract/wiki)
3. **Poppler**: [Download Windows Release](https://github.com/oschwartz10612/poppler-windows/releases/)

### Installation Steps
1. **Configure**: Update `config.json` with the paths to Tesseract and Poppler.
2. **Setup**: Double-click `setup_env.bat` to create a virtual environment and install dependencies.
3. **Run**: Double-click `run_app.bat` to launch the application.

---

### สำหรับผู้ใช้ภาษาไทย (Thai Users)
หากต้องการคู่มือการติดตั้งและวิธีใช้งานแบบละเอียดเป็นภาษาไทย สามารถอ่านได้ที่:
👉 **[คู่มือการติดตั้ง (INSTALLATION_GUIDE.md)](INSTALLATION_GUIDE.md)**

---

## 🛠️ Tech Stack
- **Frontend/UI**: [Streamlit](https://streamlit.io/)
- **Data Handling**: [Pandas](https://pandas.pydata.org/)
- **Database**: [SQLite](https://www.sqlite.org/)
- **OCR Engine**: Typhoon OCR API / Pytesseract
- **PDF Processing**: pdf2image / PyMuPDF
