"""
Resume PDF Generator — compiles tailored resumes into professional PDF documents.

Uses pdflatex (LaTeX) when available for the best typographic quality,
and falls back to fpdf (pure Python) when LaTeX is not installed.

Inspired by job_agent.py's _generate_pdf method.
"""

import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils import safe_filename
from config import get_settings

# Output directory for generated PDFs
GENERATED_DIR = Path(__file__).parent.parent / "generated" / "resumes"

# Optional career-ops bridge for professional Playwright-based PDFs
try:
    from .career_ops_bridge import CareerOpsBridge
except ImportError:
    CareerOpsBridge = None  # type: ignore


def _find_pdflatex() -> str | None:
    """Find the pdflatex executable on the system."""
    pdflatex_path = shutil.which("pdflatex")
    if pdflatex_path:
        return pdflatex_path
    # Windows: check common MiKTeX install paths
    common_paths = [
        r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe",
        r"C:\Program Files (x86)\MiKTeX\miktex\bin\pdflatex.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdflatex.exe"),
    ]
    for path in common_paths:
        if os.path.isfile(path):
            return path
    return None


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = {
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
        "^": r"\^{}", "\\": r"\textbackslash{}",
    }
    for char, escaped in replacements.items():
        text = text.replace(char, escaped)
    return text


# ─── LaTeX Template ─────────────────────────────────────────────────────────

LATEX_RESUME_TEMPLATE = r"""
\documentclass[11pt]{article}

% ── Packages ────────────────────────────────────────────────────────────────
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{titlesec}
\usepackage{parskip}

% ── Page Layout ─────────────────────────────────────────────────────────────
\geometry{
    margin=0.6in,
    top=0.5in,
    bottom=0.5in,
}

% ── Colors ──────────────────────────────────────────────────────────────────
\definecolor{primary}{HTML}{1a365d}
\definecolor{accent}{HTML}{2b6cb0}
\definecolor{muted}{HTML}{718096}

% ── Section Formatting ──────────────────────────────────────────────────────
\titleformat{\section}
    {\Large\bfseries\color{primary}}
    {}{0em}{}[\vspace{-0.3em}\rule{\textwidth}{0.5pt}]
\titlespacing{\section}{0em}{0.8em}{0.4em}

% ── List Formatting ─────────────────────────────────────────────────────────
\setlist[itemize]{
    leftmargin=1.2em,
    itemsep=0.1em,
    parsep=0em,
    topsep=0.2em,
}

% ── Hyperlinks ──────────────────────────────────────────────────────────────
\hypersetup{
    colorlinks=true,
    urlcolor=accent,
    linkcolor=primary,
}

% ── Custom Commands ─────────────────────────────────────────────────────────
\newcommand{\name}[1]{{\Huge\bfseries\color{primary}#1}}
\newcommand{\contact}[1]{{\small\color{muted}#1}}
\newcommand{\role}[1]{{\bfseries\color{accent}#1}}

\begin{document}
\begin{center}
    \name{NAME_PLACEHOLDER} \\[0.3em]
    \contact{CONTACT_PLACEHOLDER}
\end{center}

% ── Professional Summary ────────────────────────────────────────────────────
\section*{Professional Summary}
SUMMARY_PLACEHOLDER

% ── Skills ──────────────────────────────────────────────────────────────────
\section*{Skills}
SKILLS_PLACEHOLDER

% ── Experience ──────────────────────────────────────────────────────────────
\section*{Experience}
EXPERIENCE_PLACEHOLDER

% ── Education ───────────────────────────────────────────────────────────────
\section*{Education}
EDUCATION_PLACEHOLDER

% ── Projects ────────────────────────────────────────────────────────────────
\section*{Projects}
PROJECTS_PLACEHOLDER

\end{document}
"""


def _build_latex(resume_data: dict[str, Any]) -> str:
    """Build a LaTeX document from parsed resume data."""
    name = _escape_latex(resume_data.get("full_name", "Your Name"))
    email = _escape_latex(resume_data.get("email", ""))
    phone = _escape_latex(resume_data.get("phone", ""))
    linkedin = _escape_latex(resume_data.get("linkedin_url", ""))
    github = _escape_latex(resume_data.get("github_url", ""))

    # Contact line
    contact_parts = [p for p in [email, phone] if p]
    contact = " $|$ ".join(contact_parts) if contact_parts else ""
    links = []
    if linkedin:
        links.append(f"\\href{{{linkedin}}}{{{linkedin.replace('https://', '').replace('http://', '')}}}")
    if github:
        links.append(f"\\href{{{github}}}{{{github.replace('https://', '').replace('http://', '')}}}")
    if links:
        if contact:
            contact += " \\\\ "
        contact += " $|$ ".join(links)

    # Summary
    summary = _escape_latex(resume_data.get("summary", ""))
    if not summary:
        summary = _escape_latex(resume_data.get("headline", ""))

    # Skills
    skills = resume_data.get("skills", [])
    if skills:
        # Group skills into bullet points
        skill_text = " $\\bullet$ ".join(skills[:20])
        if len(skills) > 20:
            skill_text += " $\\bullet$ \\textit{and more}"
        skills_block = "\\begin{center}" + skill_text + "\\end{center}"
    else:
        skills_block = ""

    # Experience
    experience = resume_data.get("experience", [])
    exp_blocks = []
    for exp in experience:
        role = _escape_latex(exp.get("role", ""))
        company = _escape_latex(exp.get("company", ""))
        date_range = _escape_latex(exp.get("date_range", ""))
        bullets = exp.get("bullets", [])

        block = f"\\noindent\\role{{{role}}}"
        if company:
            block += f" \\hfill \\textit{{{company}}}"
        if date_range:
            block += f" \\\\ \\small\\color{{muted}}{{{date_range}}}"
        block += "\n\n"
        if bullets:
            block += "\\begin{itemize}[nosep]\n"
            for bullet in bullets[:6]:
                escaped = _escape_latex(bullet)
                block += f"    \\item {escaped}\n"
            block += "\\end{itemize}"
        exp_blocks.append(block)
    exp_text = "\n\n".join(exp_blocks) if exp_blocks else ""

    # Education
    education = resume_data.get("education", [])
    edu_blocks = []
    for edu in education:
        title = _escape_latex(edu.get("title", ""))
        details = edu.get("details", [])
        stripped_details = [d for d in details if d.strip()]
        if stripped_details:
            detail_text = " \\hfill ".join(_escape_latex(d) for d in stripped_details[:3])
            edu_blocks.append(f"\\noindent{title} \\\\ \\small\\color{{muted}}{{{detail_text}}}")
        else:
            edu_blocks.append(f"\\noindent{title}")
    edu_text = "\n\n".join(edu_blocks) if edu_blocks else ""

    # Projects
    projects = resume_data.get("projects", [])
    proj_blocks = []
    for proj in projects:
        name = _escape_latex(proj.get("name", ""))
        desc = _escape_latex(proj.get("description", ""))
        if name and desc:
            proj_blocks.append(f"\\noindent\\role{{{name}}} --- {desc}")
        elif name:
            proj_blocks.append(f"\\noindent\\role{{{name}}}")
    proj_text = "\n\n".join(proj_blocks) if proj_blocks else ""

    # Fill template
    latex = LATEX_RESUME_TEMPLATE
    latex = latex.replace("NAME_PLACEHOLDER", name)
    latex = latex.replace("CONTACT_PLACEHOLDER", contact)
    latex = latex.replace("SUMMARY_PLACEHOLDER", summary or "\\textit{No summary available}")
    latex = latex.replace("SKILLS_PLACEHOLDER", skills_block or "\\textit{No skills listed}")
    latex = latex.replace("EXPERIENCE_PLACEHOLDER", exp_text or "\\textit{No experience listed}")
    latex = latex.replace("EDUCATION_PLACEHOLDER", edu_text or "\\textit{No education listed}")
    latex = latex.replace("PROJECTS_PLACEHOLDER", proj_text or "\\textit{No projects listed}")

    return latex


# ─── Helper: sanitize text for fpdf ────────────────────────────────────────

_SANITIZE_MAP = {
    "\u2014": "-- ",    # em dash
    "\u2013": "-",      # en dash
    "\u2018": "'",     # left single quote
    "\u2019": "'",     # right single quote
    "\u201c": '"',     # left double quote
    "\u201d": '"',     # right double quote
    "\u2026": "...",   # ellipsis
    "\u2022": "-",     # bullet
    "\u25cf": "-",     # black circle
    "\u00a0": " ",     # non-breaking space
    "\u00b7": "*",     # middle dot
    "\u2192": "->",    # right arrow
    "\u2190": "<-",    # left arrow
    "\u00a9": "(c)",   # copyright
    "\u00ae": "(R)",   # registered
    "\u2122": "TM",    # trademark
    "\uf0b7": "",      # thin bullet
    "\u2713": "[x]",   # check mark
    "\u2714": "[x]",   # heavy check mark
    "\u2716": "[X]",   # heavy multiplication
}


def _sanitize_fpdf_text(text: str) -> str:
    """Replace Unicode characters with ASCII equivalents safe for fpdf's built-in fonts."""
    for char, replacement in _SANITIZE_MAP.items():
        text = text.replace(char, replacement)
    # Strip any remaining non-ASCII characters outside latin-1
    safe = text.encode("latin-1", errors="replace").decode("latin-1")
    return safe


# ─── fpdf Fallback ──────────────────────────────────────────────────────────

def _build_fpdf_pdf_structured(pdf: Any, resume_data: dict[str, Any]) -> None:
    """Render structured resume fields into an fpdf document."""
    primary = (26, 54, 93)
    accent = (43, 108, 192)
    muted = (113, 128, 150)

    def _section(title: str):
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*primary)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*primary)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)

    def _body(text: str):
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.multi_cell(0, 5, _sanitize_fpdf_text(text))
        pdf.ln(1)

    # Summary
    summary = resume_data.get("summary", "") or resume_data.get("headline", "")
    if summary:
        _section("Professional Summary")
        _body(summary)

    # Skills
    skills = resume_data.get("skills", [])
    if skills:
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(*primary)
        pdf.cell(0, 8, "Skills", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*primary)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*accent)
        skill_text = ", ".join(_sanitize_fpdf_text(s) for s in skills[:25])
        if len(skills) > 25:
            skill_text += " and more"
        pdf.multi_cell(0, 5, skill_text)
        pdf.ln(2)

    # Experience
    experience = resume_data.get("experience", [])
    if experience:
        _section("Experience")
        for exp in experience:
            role = _sanitize_fpdf_text(exp.get("role", ""))
            company = _sanitize_fpdf_text(exp.get("company", ""))
            date_range = _sanitize_fpdf_text(exp.get("date_range", ""))

            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*accent)
            line = role
            if company:
                line += f" -- {company}"
            pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")

            if date_range:
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(*muted)
                pdf.cell(0, 4, date_range, new_x="LMARGIN", new_y="NEXT")

            bullets = exp.get("bullets", [])
            if bullets:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(30, 30, 30)
                pdf.l_margin += 4
                for bullet in bullets[:5]:
                    pdf.cell(0, 4.5, f"  -  {_sanitize_fpdf_text(bullet[:90])}", new_x="LMARGIN", new_y="NEXT")
                pdf.l_margin -= 4
            pdf.ln(2)

    # Education
    education = resume_data.get("education", [])
    if education:
        _section("Education")
        for edu in education:
            title = _sanitize_fpdf_text(edu.get("title", ""))
            details = edu.get("details", [])
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*accent)
            pdf.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")
            if details:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(*muted)
                pdf.cell(0, 4, " | ".join(_sanitize_fpdf_text(d) for d in details[:3]), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

    # Projects
    projects = resume_data.get("projects", [])
    if projects:
        _section("Projects")
        for proj in projects:
            pname = _sanitize_fpdf_text(proj.get("name", ""))
            desc = _sanitize_fpdf_text(proj.get("description", ""))
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*accent)
            pdf.cell(0, 5, pname, new_x="LMARGIN", new_y="NEXT")
            if desc:
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(0, 4.5, desc[:200])
            pdf.ln(1)


def _build_fpdf_pdf_from_md(pdf: Any, resume_data: dict[str, Any], raw_md: str) -> None:
    """Render optimized markdown resume content into an fpdf document.

    Parses markdown line by line and renders with professional formatting:
    - ## headings → colored section headers with divider line
    - * / - bullets → nicely indented with bullet character
    - **bold** → bold font weight
    - Regular text → clean paragraph rendering
    """
    primary = (26, 54, 93)
    accent = (43, 108, 192)
    muted = (113, 128, 150)
    body_color = (40, 40, 40)

    def _md_section(title: str):
        """Render a section heading with colored divider line."""
        # Section title
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*primary)
        pdf.cell(0, 8, _sanitize_fpdf_text(title.upper()), new_x="LMARGIN", new_y="NEXT")
        # Divider line
        pdf.set_draw_color(*accent)
        pdf.set_line_width(0.4)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 40, pdf.get_y())
        pdf.ln(3)

    def _md_text(text: str, size: int = 10, bold: bool = False):
        """Render a paragraph of text."""
        style = "B" if bold else ""
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*body_color)
        pdf.multi_cell(0, 5.5, _sanitize_fpdf_text(text))
        pdf.ln(0.5)

    def _md_bullet(text: str):
        """Render a bullet point with proper indentation."""
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*body_color)
        original_margin = pdf.l_margin
        pdf.l_margin += 3  # Indent bullet from left margin
        # Use simple ASCII hyphen for bullet (Unicode bullets get mangled by latin-1 encoding)
        pdf.cell(5, 4.5, " - ", new_x="LMARGIN", new_y="TOP")
        pdf.multi_cell(0, 4.5, _sanitize_fpdf_text(text[:400]))
        pdf.l_margin = original_margin
        pdf.ln(0.5)

    def _render_bold_line(line: str):
        """Render a line with **bold** markers handled gracefully.
        Removes ** markers and renders the whole line as bold.
        """
        clean = line.replace("**", "").strip()
        _md_text(clean, 10, bold=True)

    # Parse markdown line by line
    lines = raw_md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        # Section headings (## or ###)
        if line.startswith("#"):
            section_name = line.lstrip("#").strip()
            if section_name:
                _md_section(section_name)
            i += 1
            continue

        # Horizontal rule (--- or ***)
        if line in ("---", "***", "___"):
            pdf.set_draw_color(200, 200, 200)
            pdf.set_line_width(0.2)
            pdf.line(pdf.l_margin, pdf.get_y() + 2, pdf.w - pdf.r_margin, pdf.get_y() + 2)
            pdf.ln(4)
            i += 1
            continue

        # Bullet points (*, -, +)
        if line.startswith(("* ", "- ", "+ ")):
            bullet_text = line[2:].strip()
            # Bold prefix before colon/dash
            if ":" in bullet_text:
                parts = bullet_text.split(":", 1)
                _md_bullet(f"{parts[0].strip()}: {parts[1].strip()}")
            elif " \u2014 " in bullet_text or " -- " in bullet_text:
                sep = " \u2014 " if " \u2014 " in bullet_text else " -- "
                parts = bullet_text.split(sep, 1)
                _md_bullet(f"{parts[0].strip()} -- {parts[1].strip()}")
            else:
                _md_bullet(bullet_text)
            i += 1
            continue

        # Bold text (**) — likely a project name, role, or sub-heading
        if "**" in line:
            _render_bold_line(line)
            i += 1
            continue

        # Regular text — Professional Summary, context lines, links
        if "#" not in line:
            # Handle inline bold (**text**) by stripping markers
            clean_line = line.replace("**", "").strip()
            _md_text(clean_line, 10)
        i += 1


def _write_header(pdf: Any, resume_data: dict[str, Any]) -> None:
    """Write the name, contact, and links header block on the PDF."""
    primary = (26, 54, 93)
    muted = (113, 128, 150)

    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*primary)
    name = _sanitize_fpdf_text(resume_data.get("full_name", "Your Name"))
    pdf.cell(0, 12, name, new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*muted)
    contact_parts = [p for p in [
        _sanitize_fpdf_text(resume_data.get("email", "")),
        _sanitize_fpdf_text(resume_data.get("phone", "")),
    ] if p]
    contact = " | ".join(contact_parts)
    if contact:
        pdf.cell(0, 6, contact, new_x="LMARGIN", new_y="NEXT", align="C")

    links = []
    for url_key in ["linkedin_url", "github_url", "portfolio_url"]:
        url = resume_data.get(url_key, "")
        if url:
            display = url.replace("https://", "").replace("http://", "").rstrip("/")
            links.append(_sanitize_fpdf_text(display))
    if links:
        pdf.cell(0, 5, " | ".join(links), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.ln(4)


def _build_fpdf_pdf(resume_data: dict[str, Any], output_path: str) -> str:
    """Generate a PDF using fpdf (pure Python, no LaTeX needed).

    If the resume_data contains 'raw_md' with optimized content (>=100 chars),
    uses that markdown content directly instead of the structured fields.
    This ensures job-tailored resumes are rendered correctly in the PDF.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        raise ImportError("fpdf is required for PDF generation. Install: pip install fpdf")

    pdf = FPDF()
    pdf.add_page()

    # Always write the header (name + contact) from structured data
    _write_header(pdf, resume_data)

    # Check if we have optimized markdown content
    raw_md = resume_data.get("raw_md", "")
    if raw_md and len(raw_md) >= 100:
        # Use optimized markdown content directly
        _build_fpdf_pdf_from_md(pdf, resume_data, raw_md)
    else:
        # Fall back to structured fields (original resume content)
        _build_fpdf_pdf_structured(pdf, resume_data)

    pdf.output(output_path)
    return output_path


# ─── Main Generator Class ────────────────────────────────────────────────────


class ResumePDFGenerator:
    """Generates professional PDF resumes from parsed resume data.

    Tries LaTeX (pdflatex) first for best typographic quality,
    falls back to fpdf (pure Python) when LaTeX is unavailable.
    """

    def __init__(self):
        self.settings = get_settings()
        self.pdflatex_path = _find_pdflatex()
        self._has_fpdf = True  # Checked at runtime
        self._career_ops = CareerOpsBridge() if CareerOpsBridge is not None else None

    @property
    def is_career_ops_available(self) -> bool:
        """Whether the external career-ops tool (Playwright/HTML→PDF) is available."""
        return self._career_ops is not None and self._career_ops.is_available

    @property
    def is_latex_available(self) -> bool:
        """Whether pdflatex is installed on the system."""
        return self.pdflatex_path is not None

    @property
    def is_available(self) -> bool:
        """Whether any PDF generation method is available."""
        return self.is_career_ops_available or self.is_latex_available or self._has_fpdf

    def get_available_backends(self) -> list[dict[str, str]]:
        """List available PDF generation backends (ordered by preference)."""
        backends = []
        if self.is_career_ops_available:
            backends.append({
                "name": "career_ops",
                "label": "Career-Ops (Playwright)",
                "description": "Professional HTML→PDF via career-ops Playwright pipeline",
            })
        if self.is_latex_available:
            backends.append({
                "name": "latex",
                "label": "LaTeX (pdflatex)",
                "description": "Professional LaTeX typesetting",
            })
        if self._has_fpdf:
            backends.append({
                "name": "fpdf",
                "label": "fpdf (Python)",
                "description": "Pure Python PDF generation (fallback)",
            })
        return backends

    async def generate(
        self,
        resume_data: dict[str, Any],
        output_dir: str | Path | None = None,
        filename: str | None = None,
        job_description: str = "",
    ) -> dict[str, Any]:
        """Generate a PDF resume from parsed resume data.

        Args:
            resume_data: Parsed resume dict (from resume_parser.parse_resume)
            output_dir: Directory to save the PDF. Defaults to generated/resumes/
            filename: Output filename (without extension). Defaults to
                     "{full_name}_Resume.pdf"
            job_description: Job description text used by career-ops bridge to
                            filter and rank experiences/projects by relevance.
                            Empty = show all entries (backward compat).

        Returns:
            Dict with pdf_path, backend_used, file_size_bytes, and generated_at
        """
        output_dir = Path(output_dir or GENERATED_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        name_slug = safe_filename(resume_data.get("full_name", "Resume").replace(" ", "_"), max_len=40)
        filename = filename or f"{name_slug}_Resume"
        output_path = str(output_dir / f"{filename}.pdf")

        # Priority 1: Career-Ops (LaTeX first, falls back to Playwright) — full-page professional PDFs
        if self.is_career_ops_available:
            try:
                raw_md = resume_data.get("raw_md", "")
                result = await self._career_ops.generate_pdf(
                    resume_data,
                    optimized_md=raw_md if len(raw_md) >= 100 else None,
                    output_path=output_path,
                    backend="latex",  # LaTeX for full-page typesetting, falls back to Playwright
                    job_description=job_description,  # Pass JD for smart filtering
                )
                if result.get("status") == "completed":
                    return {
                        "status": "completed",
                        "pdf_path": result["pdf_path"],
                        "backend": "career_ops",
                        "file_size_bytes": result.get("file_size_bytes", 0),
                        "page_count": result.get("page_count", 0),
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                    }
                # If career_ops fails, fall through to LaTeX/FPDF
                print(f"[PDFGenerator] Career-Ops failed: {result.get('message')}, falling back")
            except Exception as e:
                print(f"[PDFGenerator] Career-Ops error: {e}, falling back")

        # Priority 2: LaTeX (pdflatex)
        if self.is_latex_available:
            try:
                result = await self._generate_via_latex(resume_data, output_path)
                return result
            except Exception as e:
                print(f"[PDFGenerator] LaTeX failed: {e}, falling back to fpdf")

        # Priority 3: fpdf (pure Python fallback)
        try:
            result = await self._generate_via_fpdf(resume_data, output_path)
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"PDF generation failed: {e}",
                "pdf_path": "",
            }

    async def _generate_via_latex(
        self, resume_data: dict[str, Any], output_path: str
    ) -> dict[str, Any]:
        """Generate PDF via LaTeX (pdflatex)."""
        latex_content = _build_latex(resume_data)

        # Write .tex to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = os.path.join(tmpdir, "resume.tex")
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(latex_content)

            # Run pdflatex (twice for proper references)
            for _ in range(2):
                proc = await asyncio.create_subprocess_exec(
                    self.pdflatex_path,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    f"-output-directory={tmpdir}",
                    tex_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()

            # Find the generated PDF
            pdf_src = os.path.join(tmpdir, "resume.pdf")
            if os.path.isfile(pdf_src):
                shutil.copy2(pdf_src, output_path)
                file_size = os.path.getsize(output_path)
                return {
                    "status": "completed",
                    "pdf_path": output_path,
                    "backend": "latex",
                    "file_size_bytes": file_size,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                raise RuntimeError("pdflatex did not produce a PDF output")

    async def _generate_via_fpdf(
        self, resume_data: dict[str, Any], output_path: str
    ) -> dict[str, Any]:
        """Generate PDF via fpdf (pure Python fallback)."""
        # Run in thread to avoid blocking event loop
        def _sync_generate():
            return _build_fpdf_pdf(resume_data, output_path)

        await asyncio.to_thread(_sync_generate)
        file_size = os.path.getsize(output_path)
        return {
            "status": "completed",
            "pdf_path": output_path,
            "backend": "fpdf",
            "file_size_bytes": file_size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ─── Cover Letter LaTeX Wrapper ────────────────────────────────────────────────


def _escape_latex_text(text: str) -> str:
    """Escape special LaTeX characters in arbitrary text.

    This is a public-safe alias for _escape_latex that can be used
    from other modules without importing _escape_latex directly.
    """
    return _escape_latex(text)


def _cover_letter_to_latex(
    cover_letter_text: str,
    job_title: str = "",
    company: str = "",
) -> str:
    """Wrap cover letter text in a minimal LaTeX document suitable for pdflatex.

    Uses a simple article layout with 1in margins, hyperref for potential
    links, and the cover letter content rendered as paragraphs.

    Args:
        cover_letter_text: The plain text cover letter content.
        job_title: Job title for the document title (optional).
        company: Company name for the document title (optional).

    Returns:
        Complete LaTeX document source string.
    """
    escaped = _escape_latex(cover_letter_text)
    title_parts = [p for p in [job_title, company] if p]
    doc_title = "Cover Letter"
    if title_parts:
        doc_title += " — " + " @ ".join(title_parts)

    return (
        r"\documentclass[11pt]{article}" + "\n"
        r"\usepackage[utf8]{inputenc}" + "\n"
        r"\usepackage[T1]{fontenc}" + "\n"
        r"\usepackage{geometry}" + "\n"
        r"\usepackage[hidelinks]{hyperref}" + "\n"
        r"\geometry{margin=1in, top=0.75in}" + "\n"
        r"\pagestyle{empty}" + "\n"
        r"\begin{document}" + "\n"
        r"\begin{center}" + "\n"
        r"{\Large\bfseries " + _escape_latex(doc_title) + r"}" + "\n"
        r"\end{center}" + "\n"
        r"\vspace{1em}" + "\n"
        + escaped.replace("\n", "\n\n").replace("\n\n\n\n", "\n\n") + "\n"
        r"\end{document}" + "\n"
    )


def _build_cover_letter_fpdf(
    cover_letter_text: str,
    output_path: str,
    job_title: str = "",
    company: str = "",
) -> str:
    """Generate a cover letter PDF using fpdf2 (pure Python, no LaTeX needed).

    Renders the cover letter text as a clean, professional document with:
    - Title header (Cover Letter — Job Title @ Company)
    - Body text as paragraphs with proper line spacing

    Args:
        cover_letter_text: Plain text cover letter content.
        output_path: Full path for the output .pdf file.
        job_title: Job title (used in document title).
        company: Company name (used in document title).

    Returns:
        The output path string.

    Raises:
        ImportError: If fpdf2 is not installed.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        raise ImportError("fpdf2 is required for PDF generation. Install: pip install fpdf2")

    pdf = FPDF()
    pdf.add_page()

    primary = (26, 54, 93)
    accent = (43, 108, 192)
    muted = (113, 128, 150)

    # ── Title ────────────────────────────────────────────────────────
    title_parts = [p for p in [job_title, company] if p]
    doc_title = "Cover Letter"
    if title_parts:
        doc_title += " \u2014 " + " @ ".join(title_parts)

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*primary)
    pdf.cell(0, 14, _sanitize_fpdf_text(doc_title), new_x="LMARGIN", new_y="NEXT", align="C")

    # Divider line under title
    pdf.set_draw_color(*accent)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(6)

    # ── Body ─────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(30, 30, 30)

    # Split into paragraphs by double newline
    paragraphs = cover_letter_text.split("\n\n")
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Single newlines within a paragraph become spaces
        para_clean = " ".join(para.split("\n"))
        pdf.multi_cell(0, 6, _sanitize_fpdf_text(para_clean))
        pdf.ln(2)

    # ── Footer ───────────────────────────────────────────────────────
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*muted)
    pdf.cell(0, 4, _sanitize_fpdf_text(f"Generated by BARQ AI \u2014 {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"),
             new_x="LMARGIN", new_y="NEXT", align="C")

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    pdf.output(output_path)
    return output_path


async def generate_cover_letter_pdf(
    cover_letter_text: str,
    output_path: str,
    job_title: str = "",
    company: str = "",
) -> dict[str, Any]:
    """Generate a PDF for a cover letter from plain text.

    Priority:
    1. LaTeX (pdflatex) for best typographic quality
    2. fpdf2 (pure Python) fallback — no external dependencies
    3. .txt file as last resort

    Args:
        cover_letter_text: Plain text cover letter content.
        output_path: Full path for the output .pdf file.
        job_title: Job title (used in document title).
        company: Company name (used in document title).

    Returns:
        Dict with status, pdf_path, file_size_bytes, and generated_at.
    """
    # Priority 1: LaTeX (pdflatex)
    try:
        latex = _cover_letter_to_latex(cover_letter_text, job_title, company)
        pdf_bytes = await compile_latex_string(latex, os.path.basename(output_path))

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

        file_size = os.path.getsize(output_path)
        return {
            "status": "completed",
            "pdf_path": output_path,
            "backend": "latex",
            "file_size_bytes": file_size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"[PDFGenerator] Cover letter LaTeX failed: {e}, trying fpdf2...")

    # Priority 2: fpdf2 (pure Python, no LaTeX needed)
    try:
        _build_cover_letter_fpdf(cover_letter_text, output_path, job_title, company)
        file_size = os.path.getsize(output_path)
        print(f"[PDFGenerator] Cover letter PDF generated via fpdf2 ({file_size} bytes)")
        return {
            "status": "completed",
            "pdf_path": output_path,
            "backend": "fpdf",
            "file_size_bytes": file_size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        print(f"[PDFGenerator] Cover letter fpdf2 also failed: {e}, falling back to .txt")

    # Priority 3: .txt last resort
    txt_path = output_path.rsplit(".", 1)[0] + ".txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(cover_letter_text)
    print(f"[PDFGenerator] Cover letter fell back to .txt: {txt_path}")
    return {
        "status": "completed",
        "pdf_path": txt_path,
        "backend": "txt_fallback",
        "file_size_bytes": len(cover_letter_text.encode("utf-8")),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Hardcoded LLM LaTeX Template ──────────────────────────────────────────────
#
# The LLM does NOT write LaTeX. It outputs a JSON object with fields that
# get injected into this pre-verified template via .replace() and string
# formatting. This prevents malformed LaTeX, leaked markdown tags, stray
# characters, and broken compilation.

LATEX_LLM_RESUME_TEMPLATE = r"""
\documentclass[11pt]{article}

% ── Packages ────────────────────────────────────────────────────────────────
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{geometry}
\usepackage[hidelinks]{hyperref}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{titlesec}
\usepackage{parskip}

% ── Page Layout ─────────────────────────────────────────────────────────────
\geometry{
    margin=0.6in,
    top=0.5in,
    bottom=0.5in,
}

% ── Colors ──────────────────────────────────────────────────────────────────
\definecolor{primary}{HTML}{1a365d}
\definecolor{accent}{HTML}{2b6cb0}
\definecolor{muted}{HTML}{718096}

% ── Section Formatting ──────────────────────────────────────────────────────
\titleformat{\section}
    {\Large\bfseries\color{primary}}
    {}{0em}{}[\vspace{-0.3em}\rule{\textwidth}{0.5pt}]
\titlespacing{\section}{0em}{0.8em}{0.4em}

% ── List Formatting ─────────────────────────────────────────────────────────
\setlist[itemize]{
    leftmargin=1.2em,
    itemsep=0.1em,
    parsep=0em,
    topsep=0.2em,
}

% ── Hyperlinks ──────────────────────────────────────────────────────────────
\hypersetup{
    colorlinks=true,
    urlcolor=accent,
    linkcolor=primary,
}

% ── Custom Commands ─────────────────────────────────────────────────────────
\newcommand{\name}[1]{{\Huge\bfseries\color{primary}#1}}
\newcommand{\contact}[1]{{\small\color{muted}#1}}
\newcommand{\role}[1]{{\bfseries\color{accent}#1}}

\begin{document}
\begin{center}
    \name{{{{NAME}}}} \\\[0.3em]
    \contact{{{{CONTACT}}}}
\end{center}

% ── Professional Summary ────────────────────────────────────────────────────
\section*{Professional Summary}
{{SUMMARY}}

% ── Skills ──────────────────────────────────────────────────────────────────
\section*{Skills}
{{SKILLS}}

% ── Experience ──────────────────────────────────────────────────────────────
\section*{Experience}
{{EXPERIENCE}}

% ── Education ──────────────────────────────────────────────────────────────
\section*{Education}
{{EDUCATION}}

% ── Projects ────────────────────────────────────────────────────────────────
\section*{Projects}
{{PROJECTS}}

\end{document}
"""

# ── Experience Entry Sub-template (repeated for each role) ──────────────────

LATEX_EXPERIENCE_ENTRY = r"""
\noindent\role{{{JOB_TITLE}}} \hfill \textit{{{COMPANY}}}
\\ \small\color{muted}{{{DATES}}}

\begin{itemize}[nosep]
{{ACHIEVEMENT_BULLETS}}
\end{itemize}
"""

# ── Education Entry Sub-template ─────────────────────────────────────────────

LATEX_EDUCATION_ENTRY = r"""
\noindent{{DEGREE}} \\\
\small\color{muted}{{{INSTITUTION}} \hfill {{EDUCATION_DATES}}}
"""

# ── Project Entry Sub-template ───────────────────────────────────────────────

LATEX_PROJECT_ENTRY = r"""
\noindent\role{{{PROJECT_NAME}}} --- {{PROJECT_DESCRIPTION}}
"""


def _build_latex_from_llm_json(llm_json: dict) -> str:
    """Build a complete LaTeX resume from LLM JSON data.

    The LLM outputs a JSON object with structured resume data.
    This function:
    1. Escapes all LaTeX special characters from string values
    2. Builds section content by looping over repeated entries
    3. Injects everything into the hardcoded template via .replace()

    Args:
        llm_json: JSON dict with keys:
            - name (str): Candidate full name
            - contact (dict): email, phone, linkedin, github
            - summary (str): Professional summary (2-3 sentences)
            - skills (list[str]): Skill keywords
            - experience (list[dict]): Each with job_title, company, start_date,
              end_date, bullets (list[str])
            - education (list[dict]): Each with degree, institution, start_date,
              end_date
            - projects (list[dict]): Each with name, description

    Returns:
        Complete LaTeX document source string (pre-verified to compile).
    """
    # ── Name ────────────────────────────────────────────────────────────
    name = _escape_latex(llm_json.get("name", "Your Name"))

    # ── Contact ─────────────────────────────────────────────────────────
    contact_info = llm_json.get("contact", {})
    email = _escape_latex(contact_info.get("email", ""))
    phone = _escape_latex(contact_info.get("phone", ""))
    linkedin = contact_info.get("linkedin", "")
    github = contact_info.get("github", "")

    contact_parts = [p for p in [email, phone] if p]
    contact = " $|$ ".join(contact_parts) if contact_parts else ""
    links = []
    if linkedin:
        display = linkedin.replace("https://", "").replace("http://", "").rstrip("/")
        links.append(f"\\href{{{linkedin}}}{{{_escape_latex(display)}}}")
    if github:
        display = github.replace("https://", "").replace("http://", "").rstrip("/")
        links.append(f"\\href{{{github}}}{{{_escape_latex(display)}}}")
    if links:
        if contact:
            contact += " \\\\ "
        contact += " $|$ ".join(links)

    # ── Summary ─────────────────────────────────────────────────────────
    summary = _escape_latex(llm_json.get("summary", ""))
    if not summary:
        summary = "\\textit{Professional summary not available}"

    # ── Skills ──────────────────────────────────────────────────────────
    skills = llm_json.get("skills", [])
    if skills and isinstance(skills, list):
        skill_text = " $\\bullet$ ".join(_escape_latex(s) for s in skills[:25])
        if len(skills) > 25:
            skill_text += " $\\bullet$ \\textit{and more}"
        skills_block = "\\begin{center}" + skill_text + "\\end{center}"
    else:
        skills_block = "\\textit{Skills not specified}"

    # ── Experience ──────────────────────────────────────────────────────
    experience = llm_json.get("experience", [])
    exp_blocks = []
    for exp in experience:
        role = _escape_latex(exp.get("job_title", ""))
        company = _escape_latex(exp.get("company", ""))
        start = _escape_latex(exp.get("start_date", ""))
        end = _escape_latex(exp.get("end_date", ""))
        dates = f"{start} -- {end}" if start or end else ""
        bullets_raw = exp.get("bullets", [])

        # Build bullet items
        bullet_items = "\n".join(
            f"    \\item {_escape_latex(b)}"
            for b in bullets_raw[:8]
        )

        block = LATEX_EXPERIENCE_ENTRY
        block = block.replace("{{JOB_TITLE}}", role)
        block = block.replace("{{COMPANY}}", company)
        block = block.replace("{{DATES}}", dates)
        block = block.replace("{{ACHIEVEMENT_BULLETS}}", bullet_items)
        exp_blocks.append(block)
    experience_block = "\n".join(exp_blocks) if exp_blocks else "\\textit{No experience listed}"

    # ── Education ───────────────────────────────────────────────────────
    education = llm_json.get("education", [])
    edu_blocks = []
    for edu in education:
        degree = _escape_latex(edu.get("degree", ""))
        institution = _escape_latex(edu.get("institution", ""))
        start = _escape_latex(edu.get("start_date", ""))
        end = _escape_latex(edu.get("end_date", ""))
        dates = f"{start} -- {end}" if start or end else ""

        block = LATEX_EDUCATION_ENTRY
        block = block.replace("{{DEGREE}}", degree)
        block = block.replace("{{INSTITUTION}}", institution)
        block = block.replace("{{EDUCATION_DATES}}", dates)
        edu_blocks.append(block)
    education_block = "\n".join(edu_blocks) if edu_blocks else "\\textit{No education listed}"

    # ── Projects ────────────────────────────────────────────────────────
    projects = llm_json.get("projects", [])
    proj_blocks = []
    for proj in projects:
        name = _escape_latex(proj.get("name", ""))
        desc = _escape_latex(proj.get("description", ""))

        block = LATEX_PROJECT_ENTRY
        block = block.replace("{{PROJECT_NAME}}", name)
        block = block.replace("{{PROJECT_DESCRIPTION}}", desc)
        proj_blocks.append(block)
    projects_block = "\n".join(proj_blocks) if proj_blocks else "\\textit{No projects listed}"

    # ── Assemble ────────────────────────────────────────────────────────
    latex = LATEX_LLM_RESUME_TEMPLATE
    latex = latex.replace("{{NAME}}", name)
    latex = latex.replace("{{CONTACT}}", contact or "\\textit{No contact info}")
    latex = latex.replace("{{SUMMARY}}", summary)
    latex = latex.replace("{{SKILLS}}", skills_block)
    latex = latex.replace("{{EXPERIENCE}}", experience_block)
    latex = latex.replace("{{EDUCATION}}", education_block)
    latex = latex.replace("{{PROJECTS}}", projects_block)

    return latex


async def compile_resume_pdf_from_json(
    llm_json: dict,
    output_filename: str = "resume.pdf",
) -> bytes:
    """Build LaTeX from LLM JSON data, compile to PDF, return bytes.

    This is the primary entry point for the pipeline's LaTeX PDF generation.
    It:
    1. Takes the LLM's JSON output (no LaTeX from the LLM)
    2. Injects the data into the hardcoded, pre-verified template
    3. Escapes all LaTeX special characters
    4. Compiles via pdflatex
    5. Returns the PDF bytes

    Args:
        llm_json: JSON dict with structured resume data from the LLM.
        output_filename: Logical name for the PDF (used for temp naming).

    Returns:
        Bytes of the compiled PDF.

    Raises:
        ValueError: If llm_json is empty or missing required fields.
        RuntimeError: If pdflatex is not found or compilation fails.
    """
    if not llm_json:
        raise ValueError("LLM JSON data is empty — nothing to compile.")

    latex_string = _build_latex_from_llm_json(llm_json)
    return await compile_latex_string(latex_string, output_filename)


# ─── LaTeX String Compiler ────────────────────────────────────────────────────


def _compile_latex_sync(latex_string: str, output_filename: str = "resume.pdf") -> bytes:
    """Synchronous implementation of LaTeX compilation.

    Writes .tex to a temp directory, runs pdflatex twice, reads the PDF
    into bytes, and cleans up all intermediate files.

    Separated from the public async wrapper so it can be run in a thread
    without blocking the event loop.

    Args:
        latex_string: Valid LaTeX document source.
        output_filename: Logical name for the PDF (only used for temp file naming).

    Returns:
        Bytes of the compiled PDF.

    Raises:
        RuntimeError: If pdflatex not found or compilation fails.
        ValueError: If the LaTeX source is empty.
    """
    import subprocess as _subprocess

    if not latex_string or not latex_string.strip():
        raise ValueError("LaTeX source string is empty — nothing to compile.")

    pdflatex_path = _find_pdflatex()
    if not pdflatex_path:
        raise RuntimeError(
            "pdflatex not found on system PATH. Install TeX Live (Linux/macOS) or "
            "MiKTeX (Windows). On Ubuntu/Debian: sudo apt-get install texlive-latex-base "
            "texlive-latex-extra texlive-fonts-recommended"
        )

    with tempfile.TemporaryDirectory(prefix="barq_latex_") as tmpdir:
        tex_name = output_filename.rsplit(".", 1)[0] + ".tex"
        tex_path = os.path.join(tmpdir, tex_name)
        pdf_name = output_filename.rsplit(".", 1)[0] + ".pdf"
        pdf_path = os.path.join(tmpdir, pdf_name)

        # Write source
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(latex_string)

        # Compile twice (first pass generates .aux, second resolves refs/links)
        for pass_num in range(1, 3):
            proc = _subprocess.run(
                [
                    pdflatex_path,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    f"-output-directory={tmpdir}",
                    tex_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Bail on first pass failure so we can surface the log
            if proc.returncode != 0:
                log_path = os.path.join(tmpdir, tex_name.replace(".tex", ".log"))
                log_snippet = ""
                if os.path.isfile(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                        lines = lf.readlines()
                        log_snippet = "".join(lines[-30:])
                raise RuntimeError(
                    f"pdflatex compilation failed on pass {pass_num}.\n"
                    f"Exit code: {proc.returncode}\n"
                    f"stderr: {proc.stderr[-500:] if proc.stderr else '(none)'}\n"
                    f"=== Last lines of .log ===\n{log_snippet}"
                )

        # Read compiled PDF into memory
        if not os.path.isfile(pdf_path):
            raise RuntimeError(
                f"pdflatex completed but no PDF was produced at: {pdf_path}"
            )

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Cleanup is automatic via TemporaryDirectory

    if not pdf_bytes:
        raise RuntimeError("Compiled PDF is empty — LaTeX source may be malformed.")

    return pdf_bytes


async def compile_latex_string(latex_string: str, output_filename: str = "resume.pdf") -> bytes:
    """Compile a raw LaTeX string into a PDF and return the bytes (async-safe).

    Wraps the synchronous LaTeX compilation in `asyncio.to_thread()` so it
    does NOT block the event loop during the pdflatex subprocess call.

    Args:
        latex_string: Valid LaTeX document source.
        output_filename: Logical name for the PDF (used for temp file naming).

    Returns:
        Bytes of the compiled PDF.

    Raises:
        RuntimeError: If pdflatex is not found or compilation fails.
        ValueError: If the LaTeX source is empty.
    """
    return await asyncio.to_thread(_compile_latex_sync, latex_string, output_filename)


# Convenience function
async def generate_resume_pdf(
    resume_data: dict[str, Any],
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate a PDF resume with auto-detection of available backends."""
    generator = ResumePDFGenerator()
    return await generator.generate(resume_data, output_dir)
