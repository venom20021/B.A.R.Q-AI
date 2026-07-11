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

from config import get_settings

# Output directory for generated PDFs
GENERATED_DIR = Path(__file__).parent.parent / "generated" / "resumes"


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

def _build_fpdf_pdf(resume_data: dict[str, Any], output_path: str) -> str:
    """Generate a PDF using fpdf (pure Python, no LaTeX needed)."""
    try:
        from fpdf import FPDF
    except ImportError:
        raise ImportError("fpdf is required for PDF generation. Install: pip install fpdf")

    pdf = FPDF()
    pdf.add_page()

    # Colors
    primary = (26, 54, 93)      # Dark blue
    accent = (43, 108, 192)    # Medium blue
    muted = (113, 128, 150)    # Gray

    # Title
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*primary)
    name = _sanitize_fpdf_text(resume_data.get("full_name", "Your Name"))
    pdf.cell(0, 12, name, new_x="LMARGIN", new_y="NEXT", align="C")

    # Contact info
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*muted)
    contact_parts = [p for p in [
        _sanitize_fpdf_text(resume_data.get("email", "")),
        _sanitize_fpdf_text(resume_data.get("phone", "")),
    ] if p]
    contact = " | ".join(contact_parts)
    if contact:
        pdf.cell(0, 6, contact, new_x="LMARGIN", new_y="NEXT", align="C")

    # Links
    links = []
    for url_key in ["linkedin_url", "github_url", "portfolio_url"]:
        url = resume_data.get(url_key, "")
        if url:
            display = url.replace("https://", "").replace("http://", "").rstrip("/")
            links.append(_sanitize_fpdf_text(display))
    if links:
        pdf.cell(0, 5, " | ".join(links), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.ln(4)

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
        # Skills as comma-separated
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

    @property
    def is_latex_available(self) -> bool:
        """Whether pdflatex is installed on the system."""
        return self.pdflatex_path is not None

    @property
    def is_available(self) -> bool:
        """Whether any PDF generation method is available."""
        return self.is_latex_available or self._has_fpdf

    def get_available_backends(self) -> list[dict[str, str]]:
        """List available PDF generation backends."""
        backends = []
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
    ) -> dict[str, Any]:
        """Generate a PDF resume from parsed resume data.

        Args:
            resume_data: Parsed resume dict (from resume_parser.parse_resume)
            output_dir: Directory to save the PDF. Defaults to generated/resumes/
            filename: Output filename (without extension). Defaults to
                     "{full_name}_Resume.pdf"

        Returns:
            Dict with pdf_path, backend_used, file_size_bytes, and generated_at
        """
        output_dir = Path(output_dir or GENERATED_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)

        name_slug = resume_data.get("full_name", "Resume").replace(" ", "_")
        filename = filename or f"{name_slug}_Resume"
        output_path = str(output_dir / f"{filename}.pdf")

        # Try pdflatex first
        if self.is_latex_available:
            try:
                result = await self._generate_via_latex(resume_data, output_path)
                return result
            except Exception as e:
                print(f"[PDFGenerator] LaTeX failed: {e}, falling back to fpdf")

        # Fallback to fpdf
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


# Convenience function
async def generate_resume_pdf(
    resume_data: dict[str, Any],
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate a PDF resume with auto-detection of available backends."""
    generator = ResumePDFGenerator()
    return await generator.generate(resume_data, output_dir)
