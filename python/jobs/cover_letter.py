"""
Cover Letter Generator — creates tailored cover letters for specific jobs.

Uses the user's custom prompt template for expert-level cover letters with:
- Specific company hook (never generic)
- 3-4 paragraphs: Introduction, Technical Value, Soft Skills/Background, Call to Action
- Professional, enthusiastic, and confident tone
- Connects technical achievements and unique background directly to JD needs
"""

from typing import Any

from config import get_settings


class CoverLetterGenerator:
    """Generates tailored cover letters using local LLM with a customizable prompt structure."""

    def __init__(self):
        self.settings = get_settings()

    def _extract_best_highlight(
        self, resume: dict[str, Any], job_title: str, description: str
    ) -> str:
        """Extract the single best resume achievement that matches the target job."""
        # Look through projects first
        projects = resume.get("projects", [])
        if projects:
            # Pick first project that looks relevant
            for proj in projects:
                name = proj.get("name", "")
                desc = proj.get("description", "")
                combined = f"{name} {desc}".lower()
                # Check if it mentions any keywords from the JD
                desc_lower = description.lower()
                keywords = ["python", "aws", "react", "api", "backend", "cloud", "microservices", 
                          "distributed", "scalable", "kubernetes", "docker", "typescript",
                          "fullstack", "full stack", "full-stack", "machine learning"]
                for kw in keywords:
                    if kw in desc_lower and kw in combined:
                        return f"{name}: {desc[:200]}"
            # Fallback to first project
            p = projects[0]
            return f"{p.get('name', 'Project')}: {p.get('description', '')[:200]}"

        # Fallback: look at skills that mention the job title keywords
        skills = resume.get("skills", [])
        if skills:
            relevant = [s for s in skills if any(kw in s.lower() for kw in job_title.lower().split())]
            if relevant:
                return f"Deep expertise in {relevant[0]}"

        # Last resort: mention the most impressive job
        experience = resume.get("experience", [])
        if experience:
            top = experience[0]
            role = top.get("role", "")
            company = top.get("company", "")
            bullets = top.get("bullets", [])
            if bullets:
                return f"As {role} at {company}: {bullets[0][:150]}"

        return "Building scalable backend systems and mentoring engineering teams"

    def _build_resume_summary(self, resume: dict[str, Any]) -> str:
        """Build a concise resume summary from parsed data."""
        lines = []

        full_name = resume.get("full_name", "")
        if full_name:
            lines.append(f"Candidate: {full_name}")

        summary = resume.get("summary", "") or resume.get("headline", "")
        if summary:
            lines.append(f"Profile: {summary[:300]}")

        skills = resume.get("skills", [])
        if skills:
            skill_groups = {}
            for s in skills:
                prefix = s.split(":")[0].strip() if ":" in s else ""
                if prefix:
                    skill_groups.setdefault(prefix, []).append(s.split(":")[-1].strip())
            for group, items in skill_groups.items():
                lines.append(f"  {group}: {', '.join(items[:8])}")
            if not skill_groups:
                lines.append(f"  Skills: {', '.join(skills[:15])}")

        experience = resume.get("experience", [])
        if experience:
            lines.append("\nExperience:")
            for exp in experience[:3]:
                role = exp.get("role", "")
                company = exp.get("company", "")
                date = exp.get("date_range", "")
                header = f"  {role}"
                if company:
                    header += f" -- {company}"
                if date:
                    header += f" ({date})"
                lines.append(header)
                bullets = exp.get("bullets", [])
                for b in bullets[:3]:
                    lines.append(f"    * {b[:120]}")

        projects = resume.get("projects", [])
        if projects:
            lines.append("\nProjects:")
            for proj in projects[:3]:
                name = proj.get("name", "")
                tech = proj.get("technologies", "")
                desc = proj.get("description", "")[:150]
                lines.append(f"  * {name}{f' [{tech}]' if tech else ''}: {desc}")

        education = resume.get("education", [])
        if education:
            lines.append("\nEducation:")
            for edu in education:
                lines.append(f"  * {edu.get('title', '')}")

        return "\n".join(lines)

    async def generate(
        self,
        job: dict[str, Any],
        resume: dict[str, Any],
        optimized_resume: str | None = None,
    ) -> str:
        """
        Generate a tailored cover letter using the user's custom prompt template.

        Args:
            job: Job listing details (title, company, description)
            resume: Parsed resume data
            optimized_resume: Optional optimized resume markdown for extra context

        Returns:
            Cover letter text (250-350 words, 3-4 paragraphs)
        """
        job_title = job.get("title", "the position")
        company = job.get("company", "the company")
        description = job.get("description", "")[:2000]

        # Build a structured resume summary
        resume_summary = self._build_resume_summary(resume)

        # Pick the best highlight matching this job
        highlight = self._extract_best_highlight(resume, job_title, description)

        prompt = self._build_prompt(job_title, company, description, resume_summary, highlight)

        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert career coach and executive recruiter. "
                            "Write compelling, highly customized cover letters that are "
                            "specific to each company and role. Follow these rules:\n"
                            "1. Structure: Exactly 3-4 concise paragraphs:\n"
                            "   - Introduction (hook about the company/role)\n"
                            "   - Technical Value (connect achievements to JD needs)\n"
                            "   - Soft Skills / Unique Background\n"
                            "   - Confident Call to Action\n"
                            "2. Tone: Professional, enthusiastic, confident -- never robotic, "
                            "desperate, or overly formal.\n"
                            "3. Content: Do NOT regurgitate the resume. Connect specific "
                            "achievements to what the job description asks for.\n"
                            "4. Focus on the VALUE you bring to their engineering team, "
                            "not just what you want from the role.\n"
                            "5. Never use 'I am writing to express my interest'\n"
                            "6. Keep it 250-350 words\n"
                            "7. Sign with the candidate's full name"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.5},
            )

            return response["message"]["content"].strip()

        except ImportError:
            print("[CoverLetter] ollama not installed; using fallback")
            return self._fallback(job_title, company)
        except Exception as e:
            print(f"[CoverLetter] Generation failed: {e}")
            return self._fallback(job_title, company)

    def _build_prompt(
        self,
        job_title: str,
        company: str,
        description: str,
        resume_summary: str,
        highlight: str,
    ) -> str:
        """Build the user's custom cover letter prompt with placeholders filled."""
        return f"""Act as an expert career coach and executive recruiter. Write a compelling, highly customized cover letter for a {job_title} position at {company}.

Follow these strict guidelines:
1. Structure: Keep it to 3-4 concise paragraphs (Introduction, The Technical Value paragraph, The Soft Skills/Unique Background paragraph, and a confident Call to Action).
2. Tone: Professional, enthusiastic, and confident. Do not sound robotic, desperate, or overly formal.
3. Content strategy: Do not just regurgitate my resume. Connect my specific technical achievements and my unique background directly to the needs outlined in the job description.
4. Focus on the value I bring to their engineering team, not just what I want from the role.

Here is the Target Job Description:
{description}

Here is my background information to draw from:
- Current/Recent Roles: Full Stack Developer (backend-focused, .NET Core, AWS) previously at Coinmint, and Computer Science Teacher at National Public Inter College.
- Education: Bachelor of Computer Science, University of Windsor.
- Unique Value Proposition: I combine deep technical expertise in building robust APIs and scalable backend architectures with exceptional communication skills gained from teaching and curriculum design. I know how to write clean code and how to mentor others, document processes, and communicate complex concepts to non-technical stakeholders.
- Specific Highlight for this role: {highlight}

Full Resume:
{resume_summary}
"""

    def _fallback(self, job_title: str, company: str) -> str:
        """Generate a simple fallback cover letter when LLM is unavailable."""
        return f"""Dear Hiring Manager at {company},

I am excited to apply for the {job_title} position. My background in full-stack development, particularly building scalable backend systems with .NET Core and AWS, aligns closely with what your team is looking for. I have a proven track record of architecting distributed microservices that handle 50,000+ monthly users while reducing latency by 25%.

What sets me apart is my combination of deep technical expertise and strong communication skills. As a Computer Science teacher, I've developed the ability to explain complex technical concepts clearly, mentor junior developers, and document systems thoroughly. I bring not just code, but the ability to elevate an entire engineering team's effectiveness.

I would welcome the opportunity to discuss how my background aligns with {company}'s engineering goals. Thank you for your consideration.

Best regards,
Sai Prabhat"""
