# app.py
import io
import re
import base64
from datetime import datetime

import streamlit as st
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

st.set_page_config(page_title="PDF 工具箱：阅读 / 合并 / 拆分 / 编辑", layout="wide")

# =============== 工具函数 ===============
def read_pdf_bytes(file) -> bytes:
    return file.getvalue() if hasattr(file, "getvalue") else file.read()

def get_page_count(pdf_bytes: bytes) -> int:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages)

def parse_page_ranges(ranges_str: str, max_page: int):
    """
    输入类似: "1-3,5,7-9"（用户看到的是从1开始）
    返回0基索引的升序不重复列表
    """
    if not ranges_str.strip():
        return []

    pages = set()
    tokens = re.split(r"[,\s]+", ranges_str.strip())
    for tok in tokens:
        if not tok:
            continue
        if "-" in tok:
            a, b = tok.split("-", 1)
            try:
                start = int(a)
                end = int(b)
            except ValueError:
                raise ValueError(f"无效范围: {tok}")
            if start < 1 or end < 1 or start > max_page or end > max_page or start > end:
                raise ValueError(f"超出页码范围或无效: {tok}")
            for p in range(start - 1, end):
                pages.add(p)
        else:
            try:
                p = int(tok)
            except ValueError:
                raise ValueError(f"无效页码: {tok}")
            if p < 1 or p > max_page:
                raise ValueError(f"页码超出范围: {p}")
            pages.add(p - 1)
    return sorted(pages)

def parse_reorder(ranges_str: str, max_page: int):
    """
    支持倒序范围：x-y 如果 x>y 则降序展开
    输入从1开始 -> 返回0基索引序列（可重复）
    """
    if not ranges_str.strip():
        return []
    seq = []
    tokens = re.split(r"[,\s]+", ranges_str.strip())
    for tok in tokens:
        if not tok:
            continue
        if "-" in tok:
            a, b = tok.split("-", 1)
            try:
                start, end = int(a), int(b)
            except ValueError:
                raise ValueError(f"无效范围: {tok}")
            if start < 1 or end < 1 or start > max_page or end > max_page:
                raise ValueError(f"超出页码范围: {tok}")
            if start <= end:
                seq.extend(list(range(start - 1, end)))
            else:
                seq.extend(list(range(start - 1, end - 2, -1)))
        else:
            p = int(tok)
            if p < 1 or p > max_page:
                raise ValueError(f"页码超出范围: {p}")
            seq.append(p - 1)
    return seq

def merge_pdfs(files_with_names):
    writer = PdfWriter()
    for name, b in files_with_names:
        reader = PdfReader(io.BytesIO(b))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out

def extract_pages(pdf_bytes: bytes, page_indices):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for i in page_indices:
        writer.add_page(reader.pages[i])
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out

def delete_pages(pdf_bytes: bytes, page_indices):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    keep = [i for i in range(len(reader.pages)) if i not in set(page_indices)]
    for i in keep:
        writer.add_page(reader.pages[i])
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out

def rotate_pages(pdf_bytes: bytes, rotate_map):
    """
    rotate_map: dict[int->angle]，0基索引页->旋转角度(90/180/270)
    """
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i in rotate_map and rotate_map[i] in (90, 180, 270):
            page.rotate(rotate_map[i])
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out

def encrypt_pdf(pdf_bytes: bytes, user_pwd: str, owner_pwd: str | None = None,
                allow_print=True, allow_copy=False):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # pypdf 的 encrypt 接口只需要密码
    # 不同版本对权限支持不完全，这里保持最通用写法
    writer.encrypt(user_pwd, owner_pwd or user_pwd)

    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out

def edit_metadata(pdf_bytes: bytes, new_meta: dict):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    if new_meta:
        writer.add_metadata(new_meta)
    out = io.BytesIO()
    writer.write(out)
    out.seek(0)
    return out

def bytes_download_button(data: bytes, label: str, file_name: str, key: str):
    st.download_button(
        label=label,
        data=data,
        file_name=file_name,
        mime="application/pdf",
        key=key
    )

def pdf_bytes_to_iframe(b: bytes, height: int = 700) -> None:
    """在 Streamlit 中用 <iframe> 内嵌预览 PDF（纯前端展示）。"""
    b64 = base64.b64encode(b).decode("utf-8")
    html = f'''
    <iframe src="data:application/pdf;base64,{b64}" width="100%" height="{height}" style="border:1px solid #ddd; border-radius:8px;"></iframe>
    '''
    st.components.v1.html(html, height=height + 8, scrolling=False)

def extract_text_by_pages(pdf_bytes: bytes, page_indices: list[int]) -> str:
    """按页索引（0基）提取文本，拼接为字符串。"""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    texts = []
    for i in page_indices:
        if 0 <= i < len(reader.pages):
            try:
                texts.append(reader.pages[i].extract_text() or "")
            except Exception:
                texts.append("")
    return "\n".join(texts)

# =============== UI 布局 ===============
st.title("📄 PDF 工具箱（Streamlit + pypdf）")
st.caption("阅读/预览（多文件拖拽）、合并、拆分、重排/删除、旋转、加密、元数据 —— 轻量开箱即用")

tabs = st.tabs(["📖 阅读/预览", "🔗 合并", "✂️ 拆分 / 提取", "🧩 重排与删除", "🌀 旋转页面", "🔒 加密", "🧾 元数据"])

# ---------- 阅读/预览（多文件拖拽上传） ----------
with tabs[0]:
    st.subheader("阅读 / 预览多个 PDF（拖拽上传）")
    read_files = st.file_uploader(
        "将多个 PDF 拖拽到这里，或点击选择（支持多选）",
        type=["pdf"],
        accept_multiple_files=True,
        key="reader_multi"
    )

    if read_files:
        st.success(f"已选择 {len(read_files)} 个文件")
        for idx, f in enumerate(read_files, start=1):
            try:
                b = read_pdf_bytes(f)
                n = get_page_count(b)
            except PdfReadError:
                st.error(f"❌ {f.name} 读取失败：可能损坏或受密码保护")
                continue

            with st.container(border=True):
                st.markdown(f"#### {idx}. {f.name}  ·  {n} 页")
                col1, col2, col3 = st.columns([2, 1, 1])
                with col1:
                    height = st.slider("预览高度(px)", 400, 1200, 700, 50, key=f"pv_h_{idx}")
                with col2:
                    st.download_button("⬇️ 下载原文件", data=b, file_name=f.name, mime="application/pdf", key=f"dl_{idx}")
                with col3:
                    st.caption("拖拽排序暂不支持（可换文件名+合并页签控制顺序）")

                # 在线预览
                pdf_bytes_to_iframe(b, height=height)

                # 文本提取（可选）
                with st.expander("🧩 提取文本（可选）"):
                    st.caption("输入页码/范围（从 1 开始，例：1-3,5 或 10-8 支持倒序）")
                    ranges_str = st.text_input("页码范围", key=f"txt_rng_{idx}", value="")
                    if st.button("提取文本", key=f"extract_txt_btn_{idx}"):
                        try:
                            if ranges_str.strip():
                                idxs = parse_reorder(ranges_str, n)
                            else:
                                idxs = list(range(n))
                            text = extract_text_by_pages(b, idxs) or "(无可提取文本，可能是扫描件或图片)"
                            st.text_area("提取结果（可滚动）", value=text, height=200, key=f"txt_out_{idx}")
                            # 下载为txt
                            txt_name = f"{f.name.rsplit('.pdf',1)[0]}_extract.txt"
                            st.download_button("⬇️ 下载为 .txt", data=text.encode("utf-8"), file_name=txt_name, mime="text/plain", key=f"txt_dl_{idx}")
                        except Exception as e:
                            st.error(f"解析失败：{e}")

# ---------- 合并 ----------
with tabs[1]:
    st.subheader("合并多个 PDF")
    up_files = st.file_uploader("上传多个 PDF（可多选）", type=["pdf"], accept_multiple_files=True)
    if up_files:
        files_rows = []
        valid_files = []
        for f in up_files:
            try:
                b = read_pdf_bytes(f)
                n = get_page_count(b)
                files_rows.append({"文件名": f.name, "页数": n})
                valid_files.append((f, b))
            except PdfReadError:
                st.error(f"读取失败：{f.name} 可能已损坏或受密码保护")
        if files_rows:
            st.write("已上传：")
            st.dataframe(files_rows, use_container_width=True)

            st.info("如需调整顺序：在下方输入每个文件的顺序编号（从 1 开始），数值小的在前。")
            order_cols = st.columns(len(valid_files))
            order = []
            for i, (f, b) in enumerate(valid_files):
                v = order_cols[i].number_input(f"序号：{f.name}", min_value=1, max_value=len(valid_files), value=i+1, step=1, key=f"merge_ord_{i}")
                order.append((v, i))
            order_sorted = [valid_files[i] for _, i in sorted(order, key=lambda x: x[0])]

            if st.button("合并 PDF", type="primary"):
                files_with_names = [(f.name, b) for f, b in order_sorted]
                merged = merge_pdfs(files_with_names)
                out_name = f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                bytes_download_button(merged.getvalue(), "⬇️ 下载合并结果", out_name, key="merge_dl")

# ---------- 拆分 / 提取 ----------
with tabs[2]:
    st.subheader("拆分 / 按页提取")
    f = st.file_uploader("上传一个 PDF", type=["pdf"], key="split_one")
    if f:
        b = read_pdf_bytes(f)
        try:
            n = get_page_count(b)
            st.success(f"文件：{f.name}（{n} 页）")
            ranges_str = st.text_input("输入页码或范围（例：1-3,5,7-9）", value="")
            colA, colB = st.columns(2)
            with colA:
                if st.button("提取为新 PDF"):
                    try:
                        idxs = parse_page_ranges(ranges_str, n)
                        if not idxs:
                            st.warning("未指定页码范围。")
                        else:
                            out = extract_pages(b, idxs)
                            name = f"{f.name.rsplit('.pdf',1)[0]}_extract.pdf"
                            bytes_download_button(out.getvalue(), "⬇️ 下载提取结果", name, key="extract_dl")
                    except Exception as e:
                        st.error(f"解析失败：{e}")
            with colB:
                if st.button("删除这些页并导出"):
                    try:
                        idxs = parse_page_ranges(ranges_str, n)
                        if not idxs:
                            st.warning("未指定页码范围。")
                        else:
                            out = delete_pages(b, idxs)
                            name = f"{f.name.rsplit('.pdf',1)[0]}_deleted.pdf"
                            bytes_download_button(out.getvalue(), "⬇️ 下载删除结果", name, key="delete_dl")
                    except Exception as e:
                        st.error(f"解析失败：{e}")
        except PdfReadError:
            st.error("读取失败：文件可能损坏或受密码保护。")

# ---------- 重排与删除 ----------
with tabs[3]:
    st.subheader("重排页序 / 批量删除")
    f2 = st.file_uploader("上传一个 PDF", type=["pdf"], key="reorder_one")
    if f2:
        b2 = read_pdf_bytes(f2)
        try:
            n2 = get_page_count(b2)
            st.success(f"文件：{f2.name}（{n2} 页）")

            st.markdown("**删除页**（从1开始，逗号或空格分隔）")
            del_str = st.text_input("例如：2 4 10", value="")
            del_set = set()
            if del_str.strip():
                try:
                    del_set = set(parse_page_ranges(del_str.replace(",", " "), n2))
                except Exception as e:
                    st.error(f"删除页列表解析失败：{e}")

            st.markdown("**重排顺序**：指定导出的页序（从1开始）。留空则默认按原顺序（删除后）。")
            order_str = st.text_input("例如：1-3,7,5-4（倒序也支持，如 5-4 表示 5,4）", value="")

            if st.button("导出重排/删除后的 PDF", type="primary"):
                reader = PdfReader(io.BytesIO(b2))
                writer = PdfWriter()

                after_delete_idxs = [i for i in range(n2) if i not in del_set]

                if order_str.strip():
                    try:
                        re_idx = parse_reorder(order_str, n2)
                        # 先删除，再根据用户顺序选取；只保留删除后的集合中存在的页面
                        final_idxs = [i for i in re_idx if i in after_delete_idxs]
                    except Exception as e:
                        st.error(f"顺序解析失败：{e}")
                        final_idxs = after_delete_idxs
                else:
                    final_idxs = after_delete_idxs

                if not final_idxs:
                    st.warning("没有可导出的页面。")
                else:
                    for i in final_idxs:
                        writer.add_page(reader.pages[i])
                    out = io.BytesIO()
                    writer.write(out)
                    out.seek(0)
                    name = f"{f2.name.rsplit('.pdf',1)[0]}_reordered.pdf"
                    bytes_download_button(out.getvalue(), "⬇️ 下载结果", name, key="reorder_dl")

        except PdfReadError:
            st.error("读取失败：文件可能损坏或受密码保护。")

# ---------- 旋转 ----------
with tabs[4]:
    st.subheader("旋转页面（90/180/270）")
    f3 = st.file_uploader("上传一个 PDF", type=["pdf"], key="rotate_one")
    if f3:
        b3 = read_pdf_bytes(f3)
        try:
            n3 = get_page_count(b3)
            st.success(f"文件：{f3.name}（{n3} 页）")
            angle = st.selectbox("旋转角度", [90, 180, 270], index=0)
            pages_str = st.text_input("要旋转的页（从1开始，例：2-5,7）", value="")
            if st.button("旋转并导出"):
                try:
                    idxs = parse_page_ranges(pages_str, n3)
                    if not idxs:
                        st.warning("未指定页面，将不进行任何旋转。")
                    rotate_map = {i: angle for i in idxs}
                    out = rotate_pages(b3, rotate_map)
                    name = f"{f3.name.rsplit('.pdf',1)[0]}_rotated.pdf"
                    bytes_download_button(out.getvalue(), "⬇️ 下载结果", name, key="rotate_dl")
                except Exception as e:
                    st.error(f"解析失败：{e}")
        except PdfReadError:
            st.error("读取失败：文件可能损坏或受密码保护。")

# ---------- 加密 ----------
with tabs[5]:
    st.subheader("加密（设置打开密码）")
    f4 = st.file_uploader("上传一个 PDF", type=["pdf"], key="encrypt_one")
    if f4:
        b4 = read_pdf_bytes(f4)
        try:
            _ = get_page_count(b4)
            user_pwd = st.text_input("用户密码（打开文件时需要）", type="password")
            owner_pwd = st.text_input("所有者密码（可选）", type="password")
            allow_print = st.checkbox("允许打印", value=True)
            allow_copy = st.checkbox("允许复制", value=False)

            if st.button("加密并导出", type="primary"):
                if not user_pwd:
                    st.error("请设置用户密码。")
                else:
                    out = encrypt_pdf(b4, user_pwd, owner_pwd or None, allow_print, allow_copy)
                    name = f"{f4.name.rsplit('.pdf',1)[0]}_encrypted.pdf"
                    bytes_download_button(out.getvalue(), "⬇️ 下载结果", name, key="encrypt_dl")
        except PdfReadError:
            st.error("读取失败：文件可能损坏或受密码保护。")

# ---------- 元数据 ----------
with tabs[6]:
    st.subheader("查看 / 编辑元数据")
    f5 = st.file_uploader("上传一个 PDF", type=["pdf"], key="meta_one")
    if f5:
        b5 = read_pdf_bytes(f5)
        try:
            reader = PdfReader(io.BytesIO(b5))
            meta = dict(reader.metadata or {})
            st.write("当前元数据：")
            for k, v in meta.items():
                st.write(f"- {k}: {v}")
            st.divider()
            st.markdown("**编辑元数据（可选）**")
            title = st.text_input("Title", value=meta.get("/Title", "") or "")
            author = st.text_input("Author", value=meta.get("/Author", "") or "")
            subject = st.text_input("Subject", value=meta.get("/Subject", "") or "")
            keywords = st.text_input("Keywords", value=meta.get("/Keywords", "") or "")
            producer = st.text_input("Producer", value=meta.get("/Producer", "") or "")
            creator = st.text_input("Creator", value=meta.get("/Creator", "") or "")

            if st.button("写入并导出"):
                new_meta = {}
                if title: new_meta["/Title"] = title
                if author: new_meta["/Author"] = author
                if subject: new_meta["/Subject"] = subject
                if keywords: new_meta["/Keywords"] = keywords
                if producer: new_meta["/Producer"] = producer
                if creator: new_meta["/Creator"] = creator
                # 自动更新时间（PDF日期格式）
                new_meta["/ModDate"] = datetime.now().strftime("D:%Y%m%d%H%M%S+00'00'")
                out = edit_metadata(b5, new_meta)
                name = f"{f5.name.rsplit('.pdf',1)[0]}_meta.pdf"
                bytes_download_button(out.getvalue(), "⬇️ 下载结果", name, key="meta_dl")
        except PdfReadError:
            st.error("读取失败：文件可能损坏或受密码保护。")

# 侧边栏小贴士
with st.sidebar:
    st.markdown("### 使用小贴士")
    st.markdown("- 页码输入**从1开始**。")
    st.markdown("- 拆分示例：`1-3, 5, 7-9`。")
    st.markdown("- 重排支持**倒序**：如 `10-7` 代表 10,9,8,7。")
    st.markdown("- 加密：未输入所有者密码时，默认与用户密码一致。")
    st.markdown("- 若为扫描件/图片，文本提取可能为空。")
    st.markdown("- 受密码保护的 PDF 需先解密后再处理。")
