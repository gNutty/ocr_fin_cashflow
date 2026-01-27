# Project Context: Smart Cash Flow (Streamlit Version)

## Goal
สร้างเครื่องมือ Web App ภายใน (Internal Tool) ด้วย Streamlit เพื่อแปลงไฟล์ PDF Bank Statement เป็น Excel โดยเน้นความง่าย ไม่ต้องติดตั้งโปรแกรมซับซ้อน

## User Interface (Streamlit Logic)
- **Input:** ช่องสำหรับระบุ Path ของ Folder ที่เก็บไฟล์ PDF หรือช่อง Drag & Drop ไฟล์
- **OCR Toggle:** ปุ่มเลือก Engine ระหว่าง "Typhoon (API)" และ "Tesseract (Local)"
- **Data Preview:** แสดงตาราง (st.dataframe) ที่ดึงข้อมูลมาได้ 6 Columns และอนุญาตให้แก้ไขค่าได้ (Editable)
- **Action:** ปุ่ม "Process & Export" เพื่อรวมข้อมูลและเซฟเป็นไฟล์ Excel ฐานข้อมูล

## Data Logic (7 Columns)
1. A/C No: ค้นหาจาก Keyword "A/C NO:"
2. Document Date: ดึงวันที่ด้านบนสุด แปลงเป็น dd/MM/yyyy
3. Reference No: ค้นหาจาก "Our Ref" หรือคำที่เกี่ยวข้อง
4. Total Value: ดึงค่า "Total Debited/Credited" หรือตัวเลขสุดท้ายของหน้า
5. Bank Name: Lookup จาก `AC_Master.xlsx` (Key: A/C No)
6. Company Name: Lookup จาก `AC_Master.xlsx` (Key: A/C No)
7. Transaction: "DEBIT" หากพบ DEBIT ADVICE หรือ "CREDIT" หากพบ CREDIT ADVICE