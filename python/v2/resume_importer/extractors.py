from __future__ import annotations

import re
import struct
from email import policy
from email.parser import BytesParser
from pathlib import Path

import olefile
import pythoncom
import pytesseract
import win32com.client
import xlrd
import fitz
from defusedxml import ElementTree
from docx import Document
from lxml import html
from openpyxl import load_workbook
from PIL import Image
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pypdf import PdfReader
from pyxlsb import open_workbook
from zipfile import ZipFile

from . import SUPPORTED_EXTENSIONS


class ExtractionError(RuntimeError):
    pass


class ResumeTextExtractor:
    def __init__(self) -> None:
        self._word = None
        self._excel = None
        self._powerpoint = None
        self._com_initialized = False
        self._word_documents_processed = 0
        self.last_audit: dict[str, object] = {"unit_count": 1, "units": []}

    def __enter__(self) -> "ResumeTextExtractor":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        if self._powerpoint is not None:
            try:
                self._powerpoint.Quit()
            except Exception:
                pass
            self._powerpoint = None
        if self._excel is not None:
            try:
                self._excel.Quit()
            except Exception:
                pass
            self._excel = None
        self._reset_word()
        if self._com_initialized:
            pythoncom.CoUninitialize()
            self._com_initialized = False

    def extract(self, path: Path) -> str:
        self.last_audit = {
            "unit_count": 1,
            "units": [{"name": path.name, "status": "success"}],
        }
        if path.stat().st_size == 0:
            raise ExtractionError("源文件为0字节空文件，无法读取。")

        handlers = {
            ".doc": self._extract_doc,
            ".docm": self._extract_openxml_word,
            ".docx": self._extract_docx,
            ".dotx": self._extract_openxml_word,
            ".xml": self._extract_xml,
            ".xls": self._extract_xls,
            ".xlsx": self._extract_xlsx,
            ".html": self._extract_html,
            ".htm": self._extract_html,
            ".mht": self._extract_mhtml,
            ".mhtml": self._extract_mhtml,
            ".pdf": self._extract_pdf,
            ".ppt": self._extract_legacy_powerpoint,
            ".pptx": self._extract_pptx,
            ".txt": self._extract_text,
            ".wps": self._extract_doc,
            ".xlsb": self._extract_xlsb,
            ".jpg": self._extract_image,
            ".jpeg": self._extract_image,
            ".png": self._extract_image,
            ".bmp": self._extract_image,
            ".eml": self._extract_eml,
        }

        suffix = path.suffix.lower()
        if suffix not in handlers:
            detected_suffix = self._detect_magic_suffix(path)
            if detected_suffix in handlers:
                suffix = detected_suffix
            else:
                raise ExtractionError(f"暂不支持格式：{path.suffix.lower() or '无扩展名'}")

        try:
            text = handlers[suffix](path)
        except ExtractionError as exc:
            self._mark_audit_failed(path, str(exc))
            raise
        except Exception as exc:
            self._mark_audit_failed(path, str(exc))
            raise ExtractionError(f"{path.name} 解析失败：{exc}") from exc

        text = self._normalize(text)
        if len(text) < 8:
            if suffix == ".pdf":
                raise ExtractionError("PDF没有可提取文字，可能是扫描件，需要OCR。")
            raise ExtractionError("文件中没有读取到足够的文字。")
        return text

    @staticmethod
    def _detect_magic_suffix(path: Path) -> str:
        try:
            data = path.read_bytes()[:16]
            if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
                return ".doc"
            if data.startswith(b"PK\x03\x04"):
                return ".docx"
            if data.startswith(b"%PDF"):
                return ".pdf"
            if b"html" in data.lower() or b"<!doctype" in data.lower() or b"<?xml" in data.lower():
                return ".html"
        except Exception:
            pass
        return ""

    def _mark_audit_failed(self, path: Path, message: str) -> None:
        existing_units = list(self.last_audit.get("units") or [])
        initial_placeholder = (
            len(existing_units) == 1
            and existing_units[0].get("name") == path.name
            and existing_units[0].get("status") == "success"
        )
        if existing_units and not initial_placeholder:
            self.last_audit = {
                "unit_count": len(existing_units),
                "units": existing_units,
                "overall_status": "failed",
                "error": message[:500],
            }
            return
        self.last_audit = {
            "unit_count": int(self.last_audit.get("unit_count", 1)),
            "units": [{
                "name": path.name,
                "status": "failed",
                "error": message[:500],
            }],
        }

    def _extract_docx(self, path: Path) -> str:
        try:
            document = Document(path)
        except Exception as primary_error:
            try:
                openxml_text = self._extract_openxml_word(path)
            except Exception as fallback_error:
                raise ExtractionError(
                    "DOCX正文及容错读取均失败："
                    f"标准读取={primary_error}；正文XML读取={fallback_error}"
                ) from fallback_error
            if len(self._normalize(openxml_text)) >= 8:
                return openxml_text
            raise ExtractionError(
                f"DOCX标准读取失败且正文XML没有足够文字：{primary_error}"
            ) from primary_error

        lines: list[str] = []

        def _walk_element(element_nodes):
            for child in element_nodes:
                tag = child.tag.split("}")[-1]
                if tag == "p":
                    p_text = "".join(
                        node.text or ""
                        for node in child.iter()
                        if node.tag.split("}")[-1] == "t"
                    ).strip()
                    if p_text:
                        lines.append(p_text)
                elif tag == "tbl":
                    seen_cells = set()
                    seen_cell_text = set()
                    for row in child.findall("{*}tr"):
                        row_cells = []
                        for cell in row.findall("{*}tc"):
                            marker = id(cell)
                            if marker in seen_cells:
                                continue
                            seen_cells.add(marker)
                            cell_text_parts = []
                            for sub in cell:
                                sub_tag = sub.tag.split("}")[-1]
                                if sub_tag == "p":
                                    t = "".join(
                                        node.text or ""
                                        for node in sub.iter()
                                        if node.tag.split("}")[-1] == "t"
                                    ).strip()
                                    if t:
                                        cell_text_parts.append(t)
                                elif sub_tag == "tbl":
                                    _walk_element([sub])
                            c_str = " ".join(cell_text_parts).strip()
                            if c_str:
                                if c_str in seen_cell_text:
                                    continue
                                seen_cell_text.add(c_str)
                                row_cells.append(c_str)
                        if row_cells:
                            lines.append(" | ".join(row_cells))

        _walk_element(document.element.body)
        text = "\n".join(lines)
        if len(self._normalize(text)) >= 8:
            return text
        openxml_text = self._extract_openxml_word(path)
        if len(self._normalize(openxml_text)) >= 8:
            return openxml_text
        ocr_parts: list[str] = []
        media_count = 0
        with ZipFile(path) as archive:
            media_names = [
                name
                for name in archive.namelist()
                if name.startswith("word/media/")
                and Path(name).suffix.lower()
                in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
            ]
            media_count = len(media_names)
            for name in media_names:
                try:
                    from io import BytesIO

                    with Image.open(BytesIO(archive.read(name))) as image:
                        ocr_parts.append(self._ocr_image(image))
                except Exception as exc:
                    raise ExtractionError(
                        f"Word内图片“{Path(name).name}”OCR失败：{exc}"
                    ) from exc
        result = "\n".join([text, *ocr_parts])
        if media_count and len(self._normalize(result)) < 8:
            raise ExtractionError(
                "Word仅包含图片且OCR未发现正文，疑似候选人照片附件。"
            )
        return result

    @staticmethod
    def _extract_openxml_word(path: Path) -> str:
        parts: list[str] = []
        with ZipFile(path) as archive:
            names = sorted(
                name
                for name in archive.namelist()
                if name == "word/document.xml"
                or re.fullmatch(
                    r"word/(?:header|footer)\d+\.xml|"
                    r"word/(?:footnotes|endnotes|comments)\.xml",
                    name,
                )
            )
            for name in names:
                root = ElementTree.fromstring(archive.read(name))
                text = "\n".join(
                    value.strip()
                    for value in root.itertext()
                    if value and value.strip()
                )
                if text:
                    parts.append(text)
        return "\n".join(parts)

    def _extract_doc(self, path: Path) -> str:
        native_error: Exception | None = None
        try:
            text = self._extract_doc_without_word(path)
            if len(self._normalize(text)) >= 8:
                return text
            if self._binary_doc_has_embedded_images(path):
                raise ExtractionError(
                    "旧版Word仅包含嵌入图片且没有正文，"
                    "疑似候选人照片附件。"
                )
        except Exception as exc:
            native_error = exc

        if isinstance(native_error, ExtractionError) and "照片附件" in str(
            native_error
        ):
            raise native_error

        first_error: Exception | None = None
        for attempt in range(2):
            try:
                text = self._extract_doc_once(path)
                if len(self._normalize(text)) >= 8:
                    return text
                if self._binary_doc_has_embedded_images(path):
                    raise ExtractionError(
                        "旧版Word仅包含嵌入图片且没有正文，"
                        "疑似候选人照片附件。"
                    )
                return text
            except Exception as exc:
                first_error = first_error or exc
                self._reset_word()
                if attempt == 0:
                    continue

        # 如果 COM 仍失败，尝试降级提取二进制中的文本
        # EN: If COM still fails, try falling back to extracting text from the binary
        # JA: COM がまだ失敗する場合は、バイナリからテキストを抽出する代替手段を試す
        fallback_text = self._extract_doc_fallback(path)
        if len(self._normalize(fallback_text)) >= 8:
            return fallback_text

        native_message = f"；离线读取失败：{native_error}" if native_error else ""
        raise ExtractionError(
            f"Word只读打开重试2次仍失败：{first_error}{native_message}"
        )

    def _extract_doc_fallback(self, path: Path) -> str:
        try:
            data = path.read_bytes()
            if data.startswith(b"{\\rtf") or b"{\\rtf" in data[:50]:
                return self._extract_rtf(data)
            if olefile.isOleFile(str(path)):
                with olefile.OleFileIO(str(path)) as compound:
                    raw_bytes = b""
                    if compound.exists("WordDocument"):
                        raw_bytes = compound.openstream("WordDocument").read()
                    else:
                        for stream in compound.listdir():
                            try:
                                raw_bytes += compound.openstream(stream).read()
                            except Exception:
                                pass
                    decoded = raw_bytes.decode('gb18030', errors='ignore')
                    matches = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9\s.,:;()（）\-–—/]{4,}', decoded)
                    text = "\n".join(m.strip() for m in matches if len(m.strip()) > 3)
                    if len(self._normalize(text)) >= 8:
                        return text
        except Exception:
            pass
        return ""

    @staticmethod
    def _extract_rtf(data: bytes) -> str:
        def replace_hex_block(match):
            hex_str = match.group(0).replace("\\'", "")
            try:
                raw_b = bytes.fromhex(hex_str)
                return raw_b.decode('gb18030', errors='ignore')
            except Exception:
                return ""

        raw_str = data.decode('latin1', errors='ignore')
        decoded_str = re.sub(r"(?:\\'[0-9a-fA-F]{2})+", replace_hex_block, raw_str)
        clean_text = re.sub(r"\\[a-zA-Z0-9]+(?:\-?\d+)?\s?", " ", decoded_str)
        clean_text = re.sub(r"[{}]", " ", clean_text)
        lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
        return "\n".join(lines)

    @staticmethod
    def _binary_doc_has_embedded_images(path: Path) -> bool:
        if not olefile.isOleFile(str(path)):
            return False
        signatures = (
            b"\xff\xd8\xff",
            b"\x89PNG\r\n\x1a\n",
            b"GIF8",
            b"\xd7\xcd\xc6\x9a",
        )
        try:
            with olefile.OleFileIO(str(path)) as compound:
                if not compound.exists("Data"):
                    return False
                data = compound.openstream("Data").read()
                return any(signature in data for signature in signatures)
        except Exception:
            return False

    def _extract_doc_without_word(self, path: Path) -> str:
        data = path.read_bytes()
        if data.startswith(b"{\\rtf") or b"{\\rtf" in data[:50]:
            return self._extract_rtf(data)
        if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            return self._extract_binary_doc(path)
        if data.startswith(b"PK\x03\x04"):
            return self._extract_openxml_word(path)

        if data.startswith(b"From:") or b"Content-Type: multipart/related" in data[:500] or b"MIME-Version:" in data[:500]:
            return self._extract_mhtml(path)

        text = self._decode_plain_bytes(data)
        if re.search(r"<(?:html|body|table|div|p)\b", text, re.I):
            return self._html_text(text)
        return text

    @staticmethod
    def _extract_binary_doc(path: Path) -> str:
        if not olefile.isOleFile(str(path)):
            raise ExtractionError("文件不是有效的OLE复合文档。")

        with olefile.OleFileIO(str(path)) as compound:
            if not compound.exists("WordDocument"):
                raise ExtractionError("OLE文档缺少WordDocument流。")
            word_data = compound.openstream("WordDocument").read()
            if len(word_data) < 0x1AA:
                raise ExtractionError("旧版Word文件头不完整。")

            n_fib = struct.unpack_from("<H", word_data, 0x02)[0]
            if n_fib < 0x00C1:
                raise ExtractionError("Word 97以前的二进制格式需由Word兼容读取。")

            flags = struct.unpack_from("<H", word_data, 0x0A)[0]
            if flags & 0x0100:
                raise ExtractionError("旧版Word文档已加密。")
            table_name = "1Table" if flags & 0x0200 else "0Table"
            if not compound.exists(table_name):
                raise ExtractionError(f"OLE文档缺少{table_name}流。")

            table_data = compound.openstream(table_name).read()
            fc_clx, lcb_clx = struct.unpack_from("<II", word_data, 0x1A2)
            return ResumeTextExtractor._decode_word_piece_table(
                word_data,
                table_data,
                fc_clx,
                lcb_clx,
            )

    @staticmethod
    def _decode_word_piece_table(
        word_data: bytes,
        table_data: bytes,
        fc_clx: int,
        lcb_clx: int,
    ) -> str:
        if lcb_clx <= 0 or fc_clx + lcb_clx > len(table_data):
            raise ExtractionError("Word文字索引CLX越界或为空。")

        clx = table_data[fc_clx:fc_clx + lcb_clx]
        position = 0
        plc_pcd: bytes | None = None
        while position < len(clx):
            clxt = clx[position]
            if clxt == 0x01:
                if position + 3 > len(clx):
                    raise ExtractionError("Word文字索引GrpPrl不完整。")
                cb_grpprl = struct.unpack_from("<H", clx, position + 1)[0]
                position += 3 + cb_grpprl
                continue
            if clxt == 0x02:
                if position + 5 > len(clx):
                    raise ExtractionError("Word文字索引Pcdt不完整。")
                plc_size = struct.unpack_from("<I", clx, position + 1)[0]
                start = position + 5
                end = start + plc_size
                if end > len(clx):
                    raise ExtractionError("Word文字片段表PlcPcd越界。")
                plc_pcd = clx[start:end]
                break
            raise ExtractionError(f"无法识别Word文字索引类型：0x{clxt:02x}")

        if plc_pcd is None or (len(plc_pcd) - 4) % 12 != 0:
            raise ExtractionError("Word文字片段表结构无效。")

        piece_count = (len(plc_pcd) - 4) // 12
        if piece_count <= 0:
            raise ExtractionError("Word文字片段表为空。")

        cp_count = piece_count + 1
        cp_bytes = cp_count * 4
        cps = struct.unpack_from(f"<{cp_count}I", plc_pcd, 0)
        parts: list[str] = []
        for index in range(piece_count):
            char_count = cps[index + 1] - cps[index]
            if char_count <= 0:
                continue

            pcd_offset = cp_bytes + index * 8
            fc_compressed = struct.unpack_from("<I", plc_pcd, pcd_offset + 2)[0]
            is_compressed = bool(fc_compressed & 0x40000000)
            file_offset = fc_compressed & 0x3FFFFFFF
            if is_compressed:
                file_offset //= 2
                byte_count = char_count
                encoding = "cp1252"
            else:
                byte_count = char_count * 2
                encoding = "utf-16-le"

            end = file_offset + byte_count
            if file_offset < 0 or end > len(word_data):
                raise ExtractionError(
                    f"Word文字片段{index + 1}越界："
                    f"{file_offset}-{end}/{len(word_data)}"
                )
            parts.append(
                word_data[file_offset:end].decode(encoding, errors="replace")
            )

        text = "".join(parts)
        text = (
            text.replace("\x0b", "\n")
            .replace("\x0c", "\n")
            .replace("\x0e", "\n")
            .replace("\x13", "")
            .replace("\x14", " ")
            .replace("\x15", "")
        )
        return text

    @staticmethod
    def _decode_plain_bytes(data: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-16", "gb18030", "shift_jis", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ExtractionError("文本编码无法识别。")

    def _extract_doc_once(self, path: Path) -> str:
        self._ensure_com()
        if self._word is None:
            self._word = win32com.client.DispatchEx("Word.Application")
            self._word.Visible = False
            self._word.DisplayAlerts = 0
            try:
                self._word.AutomationSecurity = 3
            except Exception:
                pass

        document = None
        text = ""
        try:
            document = self._word.Documents.Open(
                str(path.resolve()),
                ConfirmConversions=False,
                ReadOnly=True,
                AddToRecentFiles=False,
                Visible=False,
                OpenAndRepair=True,
            )
            text = str(document.Content.Text)
        finally:
            if document is not None:
                try:
                    document.Close(False)
                except Exception:
                    self._reset_word()
        self._word_documents_processed += 1
        if self._word_documents_processed >= 100:
            self._reset_word()
        return text

    def _reset_word(self) -> None:
        if self._word is not None:
            try:
                self._word.Quit()
            except Exception:
                pass
        self._word = None
        self._word_documents_processed = 0

    def _ensure_com(self) -> None:
        if not self._com_initialized:
            pythoncom.CoInitialize()
            self._com_initialized = True

    @staticmethod
    def _extract_xml(path: Path) -> str:
        root = ElementTree.parse(path).getroot()
        return "\n".join(part.strip() for part in root.itertext() if part.strip())

    def _extract_xlsx(self, path: Path) -> str:
        if olefile.isOleFile(str(path)):
            with olefile.OleFileIO(str(path)) as compound:
                if compound.exists("EncryptedPackage"):
                    raise ExtractionError(
                        "Excel文件已加密，未提供密码，无法读取。"
                    )
        workbook = load_workbook(path, read_only=True, data_only=True)
        lines: list[str] = []
        units: list[dict[str, str]] = []
        try:
            for sheet in workbook.worksheets:
                sheet_lines: list[str] = []
                nonempty_cells = 0
                if len(workbook.worksheets) > 1:
                    sheet_lines.append(f"工作表：{sheet.title}")
                try:
                    for row in sheet.iter_rows(values_only=True):
                        values = [
                            str(value).strip()
                            for value in row
                            if value not in (None, "")
                        ]
                        nonempty_cells += len(values)
                        if values:
                            sheet_lines.append("\t".join(values))
                except Exception as exc:
                    units.append(
                        {
                            "name": sheet.title,
                            "status": "failed",
                            "error": str(exc)[:500],
                        }
                    )
                    continue
                if nonempty_cells == 0 and len(getattr(sheet, "_images", [])) > 0:
                    units.append(
                        {
                            "name": sheet.title,
                            "status": "failed_image_only",
                            "error": "工作表只有图片，未发现单元格正文",
                        }
                    )
                    continue
                if nonempty_cells > 0:
                    lines.extend(sheet_lines)
                    units.append({"name": sheet.title, "status": "success"})
                else:
                    units.append({"name": sheet.title, "status": "empty"})
            self.last_audit = {"unit_count": len(units), "units": units}
        finally:
            workbook.close()
        return "\n".join(lines)

    def _extract_xls(self, path: Path) -> str:
        workbook = xlrd.open_workbook(path, on_demand=True)
        lines: list[str] = []
        units: list[dict[str, str]] = []
        try:
            for sheet_name in workbook.sheet_names():
                sheet = workbook.sheet_by_name(sheet_name)
                sheet_lines: list[str] = []
                nonempty_cells = 0
                if workbook.nsheets > 1:
                    sheet_lines.append(f"工作表：{sheet_name}")
                try:
                    for row_index in range(sheet.nrows):
                        values = [
                            str(sheet.cell_value(row_index, column)).strip()
                            for column in range(sheet.ncols)
                            if str(sheet.cell_value(row_index, column)).strip()
                        ]
                        nonempty_cells += len(values)
                        if values:
                            sheet_lines.append("\t".join(values))
                except Exception as exc:
                    units.append(
                        {
                            "name": sheet_name,
                            "status": "failed",
                            "error": str(exc)[:500],
                        }
                    )
                    continue
                if nonempty_cells > 0:
                    lines.extend(sheet_lines)
                    units.append({"name": sheet_name, "status": "success"})
                else:
                    units.append({"name": sheet_name, "status": "empty"})
            self.last_audit = {"unit_count": len(units), "units": units}
        finally:
            workbook.release_resources()
        if not lines and self._ole_has_embedded_images(path):
            raise ExtractionError(
                "Excel没有单元格正文且仅检测到嵌入图片，"
                "疑似候选人照片附件或扫描表。"
            )
        return "\n".join(lines)

    @staticmethod
    def _ole_has_embedded_images(path: Path) -> bool:
        if not olefile.isOleFile(str(path)):
            return False
        signatures = (
            b"\xff\xd8\xff",
            b"\x89PNG\r\n\x1a\n",
            b"GIF8",
            b"\xd7\xcd\xc6\x9a",
        )
        try:
            with olefile.OleFileIO(str(path)) as compound:
                for stream in compound.listdir():
                    try:
                        data = compound.openstream(stream).read()
                    except Exception:
                        continue
                    if any(signature in data for signature in signatures):
                        return True
        except Exception:
            return False
        return False

    @staticmethod
    def _extract_html(path: Path) -> str:
        data = path.read_bytes()
        return ResumeTextExtractor._html_text(data)

    @staticmethod
    def _extract_mhtml(path: Path) -> str:
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        parts: list[str] = []
        for part in message.walk():
            content_type = part.get_content_type()
            if content_type not in {"text/html", "text/plain"}:
                continue
            content = part.get_content()
            if not content:
                continue
            if content_type == "text/html":
                parts.append(ResumeTextExtractor._html_text(content))
            else:
                if isinstance(content, bytes):
                    charset = part.get_content_charset() or "utf-8"
                    content = content.decode(charset, errors="replace")
                parts.append(content)
        return "\n".join(parts)

    def _extract_eml(self, path: Path) -> str:
        data_bytes = path.read_bytes()
        message = BytesParser(policy=policy.default).parsebytes(data_bytes)
        parts: list[str] = []
        units: list[dict[str, str]] = []
        for index, part in enumerate(message.walk(), start=1):
            if part.is_multipart():
                continue
            content_type = part.get_content_type()
            filename = part.get_filename()
            disposition = part.get_content_disposition()
            label = filename or f"MIME-{index}:{content_type}"
            if content_type not in {"text/html", "text/plain", "application/xml", "text/xml"}:
                units.append({"name": label, "status": "ignored_non_text"})
                continue
            try:
                # 先尝试获取原始 payload 字节做容错解码
                # EN: First try getting the raw payload bytes for tolerant decoding
                # JA: まず元の payload のバイト列を取得し、寛容なデコードを試みる
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    content = self._decode_plain_bytes(payload)
                else:
                    content = str(part.get_content() or "")
                
                if content_type == "text/html":
                    value = self._html_text(content)
                elif content_type in {"application/xml", "text/xml"}:
                    value = re.sub(r"<[^>]+>", " ", str(content))
                else:
                    value = str(content)
                
                # 清洗 HTML 实体
                # EN: Clean HTML entities
                # JA: HTML エンティティをクレンジングする
                value = re.sub(r"&(?:nbsp|#160);", " ", value, flags=re.IGNORECASE)
                value = re.sub(r"&[a-z0-9]+;", " ", value, flags=re.IGNORECASE)
                if value.strip():
                    parts.append(value)
                units.append({"name": label, "status": "success"})
            except Exception as exc:
                units.append({"name": label, "status": "failed", "error": str(exc)})
        self.last_audit = {"unit_count": len(units), "units": units}
        return "\n".join(parts)

    @staticmethod
    def _decode_plain_bytes(data: bytes) -> str:
        for encoding in ("gb18030", "utf-8-sig", "shift_jis", "gbk", "cp1252", "utf-16"):
            try:
                return data.decode(encoding)
            except Exception:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _html_text(data: bytes | str) -> str:
        if isinstance(data, bytes):
            data = ResumeTextExtractor._decode_plain_bytes(data)
        data = re.sub(r"<\?xml[^>]*\?>", "", data, flags=re.IGNORECASE)
        document = html.document_fromstring(data)
        for element in document.xpath("//script|//style|//noscript|//template"):
            element.drop_tree()
        return document.text_content()

    def _extract_pdf(self, path: Path) -> str:
        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ExtractionError("PDF已加密，无法读取。") from exc
        parts: list[str] = []
        units: list[dict[str, str]] = []
        image_pages: list[int] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                try:
                    has_images = bool(page.images)
                except Exception:
                    has_images = False
                if has_images:
                    image_pages.append(index)
            parts.append(text)
            units.append(
                {"name": str(index), "status": "success", "text": text}
            )
        if not any(part.strip() for part in parts) and not image_pages:
            # pypdf does not expose every image-only PDF through page.images
            # (for example some scanner/photo exports).  When the whole file
            # has no text, render every page with MuPDF and let OCR decide.
            image_pages = list(range(1, len(parts) + 1))
        if image_pages:
            try:
                document = fitz.open(path)
                for page_number in image_pages:
                    page = document.load_page(page_number - 1)
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    image = Image.frombytes(
                        "RGB",
                        (pixmap.width, pixmap.height),
                        pixmap.samples,
                    )
                    parts[page_number - 1] = self._ocr_image(image)
                    units[page_number - 1]["status"] = "success_ocr"
                    units[page_number - 1]["text"] = parts[page_number - 1]
            except Exception as exc:
                raise ExtractionError(f"PDF图片页OCR失败：{exc}") from exc
        if image_pages and not any(part.strip() for part in parts):
            raise ExtractionError(
                "PDF只有图片且OCR未发现正文，疑似候选人照片附件。"
            )
        self.last_audit = {"unit_count": len(units), "units": units}
        return "\n".join(parts)

    @staticmethod
    def _ocr_image(image: Image.Image) -> str:
        tesseract_path = Path(
            r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        )
        tessdata_path = (
            Path(__file__).resolve().parents[2]
            / ".local-config"
            / "tessdata"
        )
        if not tesseract_path.is_file():
            raise ExtractionError("未找到Tesseract OCR引擎。")
        if not all(
            (tessdata_path / f"{language}.traineddata").is_file()
            for language in ("chi_sim", "jpn", "eng")
        ):
            raise ExtractionError("OCR中/日/英语言模型不完整。")
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_path)
        return pytesseract.image_to_string(
            image,
            lang="chi_sim+jpn+eng",
            config=f"--tessdata-dir {tessdata_path} --psm 6",
            timeout=90,
        )

    def _extract_xlsb(self, path: Path) -> str:
        lines: list[str] = []
        units: list[dict[str, str]] = []
        with open_workbook(str(path)) as workbook:
            sheet_names = list(workbook.sheets)
            with ZipFile(path) as archive:
                drawing_sheets = {
                    index
                    for index in range(1, len(sheet_names) + 1)
                    if (
                        f"xl/worksheets/_rels/sheet{index}.bin.rels"
                        in archive.namelist()
                        and b"/drawing" in archive.read(
                            f"xl/worksheets/_rels/sheet{index}.bin.rels"
                        )
                    )
                }
            for sheet_index, sheet_name in enumerate(sheet_names, start=1):
                sheet_lines: list[str] = []
                try:
                    with workbook.get_sheet(sheet_name) as worksheet:
                        for row in worksheet.rows():
                            values = [
                                str(cell.v).strip()
                                for cell in row
                                if cell.v not in (None, "")
                            ]
                            if values:
                                sheet_lines.append("\t".join(values))
                except Exception as exc:
                    units.append(
                        {
                            "name": sheet_name,
                            "status": "failed",
                            "error": str(exc)[:500],
                        }
                    )
                    continue
                if not sheet_lines and sheet_index in drawing_sheets:
                    units.append(
                        {
                            "name": sheet_name,
                            "status": "failed_image_only",
                            "error": "工作表可能只有图片，未发现单元格正文",
                        }
                    )
                    continue
                if sheet_lines:
                    if len(sheet_names) > 1:
                        lines.append(f"工作表：{sheet_name}")
                    lines.extend(sheet_lines)
                    units.append({"name": sheet_name, "status": "success"})
                else:
                    units.append({"name": sheet_name, "status": "empty"})
        self.last_audit = {"unit_count": len(units), "units": units}
        return "\n".join(lines)

    def _extract_xlsb_with_excel(self, path: Path) -> str:
        self._ensure_com()
        if self._excel is None:
            self._excel = win32com.client.DispatchEx("Excel.Application")
            self._excel.Visible = False
            self._excel.DisplayAlerts = False
            self._excel.EnableEvents = False
            try:
                self._excel.AutomationSecurity = 3
            except Exception:
                pass

        workbook = None
        lines: list[str] = []
        units: list[dict[str, str]] = []
        try:
            workbook = self._excel.Workbooks.Open(
                str(path.resolve()),
                UpdateLinks=0,
                ReadOnly=True,
                IgnoreReadOnlyRecommended=True,
                AddToMru=False,
            )
            for worksheet in workbook.Worksheets:
                sheet_name = str(worksheet.Name)
                try:
                    sheet_lines = self._excel_values_to_lines(worksheet.UsedRange.Value)
                    if not sheet_lines and int(worksheet.Shapes.Count) > 0:
                        raise ExtractionError(
                            f"Excel工作表“{sheet_name}”只有图片，无法识别文字。"
                        )
                    if sheet_lines:
                        if int(workbook.Worksheets.Count) > 1:
                            lines.append(f"工作表：{sheet_name}")
                        lines.extend(sheet_lines)
                    units.append({"name": sheet_name, "status": "success"})
                except ExtractionError:
                    raise
                except Exception as exc:
                    raise ExtractionError(
                        f"Excel工作表“{sheet_name}”读取失败：{exc}"
                    ) from exc
            self.last_audit = {"unit_count": len(units), "units": units}
            return "\n".join(lines)
        finally:
            if workbook is not None:
                workbook.Close(False)

    def _extract_pptx(self, path: Path) -> str:
        presentation = Presentation(path)
        lines: list[str] = []
        units: list[dict[str, str]] = []
        for slide_number, slide in enumerate(presentation.slides, start=1):
            slide_text: list[str] = []
            has_picture = False
            for shape in slide.shapes:
                slide_text.extend(self._pptx_shape_text(shape))
                if shape.shape_type in {
                    MSO_SHAPE_TYPE.PICTURE,
                    MSO_SHAPE_TYPE.LINKED_PICTURE,
                }:
                    has_picture = True
            if not slide_text and has_picture:
                raise ExtractionError(
                    f"PowerPoint第{slide_number}页只有图片，无法完整识别文字。"
                )
            if slide_text:
                lines.append(f"幻灯片：{slide_number}")
                lines.extend(slide_text)
            units.append({"name": str(slide_number), "status": "success"})
        self.last_audit = {"unit_count": len(units), "units": units}
        return "\n".join(lines)

    def _pptx_shape_text(self, shape: object) -> list[str]:
        parts: list[str] = []
        if getattr(shape, "has_text_frame", False):
            value = str(shape.text).strip()
            if value:
                parts.append(value)
        if getattr(shape, "has_table", False):
            for row in shape.table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append("\t".join(cells))
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for child in shape.shapes:
                parts.extend(self._pptx_shape_text(child))
        return parts

    def _extract_legacy_powerpoint(self, path: Path) -> str:
        self._ensure_com()
        if self._powerpoint is None:
            self._powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
            try:
                self._powerpoint.AutomationSecurity = 3
            except Exception:
                pass

        presentation = None
        lines: list[str] = []
        units: list[dict[str, str]] = []
        try:
            presentation = self._powerpoint.Presentations.Open(
                str(path.resolve()),
                ReadOnly=True,
                Untitled=False,
                WithWindow=False,
            )
            for slide in presentation.Slides:
                slide_number = int(slide.SlideIndex)
                try:
                    slide_text: list[str] = []
                    for shape in slide.Shapes:
                        slide_text.extend(self._powerpoint_shape_text(shape))
                    if not slide_text and int(slide.Shapes.Count) > 0:
                        raise ExtractionError(
                            f"PowerPoint第{slide_number}页只有图片或图形，"
                            "无法完整识别文字。"
                        )
                    if slide_text:
                        lines.append(f"幻灯片：{slide_number}")
                        lines.extend(slide_text)
                    units.append({"name": str(slide_number), "status": "success"})
                except ExtractionError:
                    raise
                except Exception as exc:
                    raise ExtractionError(
                        f"PowerPoint第{slide_number}页读取失败：{exc}"
                    ) from exc
            self.last_audit = {"unit_count": len(units), "units": units}
            return "\n".join(lines)
        finally:
            if presentation is not None:
                presentation.Close()

    @staticmethod
    def _excel_values_to_lines(values: object) -> list[str]:
        if values is None:
            return []
        if not isinstance(values, tuple):
            value = str(values).strip()
            return [value] if value else []
        rows = values if values and isinstance(values[0], tuple) else (values,)
        lines: list[str] = []
        for row in rows:
            cells = [str(value).strip() for value in row if value not in (None, "")]
            if cells:
                lines.append("\t".join(cells))
        return lines

    def _powerpoint_shape_text(self, shape: object) -> list[str]:
        parts: list[str] = []
        try:
            if bool(shape.HasTextFrame) and bool(shape.TextFrame.HasText):
                value = str(shape.TextFrame.TextRange.Text).strip()
                if value:
                    parts.append(value)
        except Exception:
            pass
        try:
            if bool(shape.HasTable):
                table = shape.Table
                for row in range(1, int(table.Rows.Count) + 1):
                    cells: list[str] = []
                    for column in range(1, int(table.Columns.Count) + 1):
                        value = str(
                            table.Cell(row, column).Shape.TextFrame.TextRange.Text
                        ).strip()
                        if value:
                            cells.append(value)
                    if cells:
                        parts.append("\t".join(cells))
        except Exception:
            pass
        try:
            if int(shape.Type) == 6:
                for index in range(1, int(shape.GroupItems.Count) + 1):
                    parts.extend(
                        self._powerpoint_shape_text(shape.GroupItems.Item(index))
                    )
        except Exception:
            pass
        return parts

    @staticmethod
    def _extract_text(path: Path) -> str:
        data = path.read_bytes()
        for encoding in ("utf-8-sig", "utf-16", "gb18030", "shift_jis", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise ExtractionError("文本编码无法识别。")

    @staticmethod
    def _extract_image(path: Path) -> str:
        with Image.open(path) as image:
            image.load()
            return ResumeTextExtractor._ocr_image(image)

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x07", "\n")
        text = re.sub(r"[\t \u3000]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
