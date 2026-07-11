"""
Cold Email Writer — generates personalized cold outreach emails.

Supports multiple tones: professional, casual, enthusiastic
Uses Ollama to write compelling outreach that references the recipient/company.
"""


from config import get_settings


class ColdEmailWriter:
    """Generates personalized cold outreach emails using local LLM."""

    def __init__(self):
        self.settings = get_settings()

    async def write(
        self,
        company: str,
        job_title: str,
        resume_summary: str,
        reason: str,
        recipient_name: str | None = None,
        recipient_email: str | None = None,
        tone: str = "professional",
    ) -> dict[str, str]:
        """
        Generate a cold outreach email.

        Args:
            company: Target company name
            job_title: Desired role title
            resume_summary: Brief summary of the user's background
            reason: Why the user is reaching out (e.g., "saw their AI product launch")
            recipient_name: Optional hiring manager name
            recipient_email: Optional recipient email
            tone: One of "professional", "casual", "enthusiastic"

        Returns:
            Dict with subject_line and email_body
        """
        prompt = self._build_prompt(company, job_title, resume_summary, reason, recipient_name, tone)

        try:
            import ollama
            response = ollama.chat(
                model=self.settings.ollama_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"You are an expert cold email writer. Tone: {tone}.\n"
                            "Rules:\n"
                            "1. Subject line: compelling, specific, not spammy\n"
                            "2. Opening: personalized to the recipient or company\n"
                            "3. Body: value proposition backed by specific experience\n"
                            "4. Ask: specific request (coffee chat, referral, consideration)\n"
                            "5. Closing: professional, gratitude\n"
                            "6. Max 200 words\n"
                            "7. Warm, confident, not desperate"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.6},
            )

            content = response["message"]["content"].strip()
            return self._parse(content, company, job_title, recipient_name, recipient_email, tone)

        except Exception as e:
            print(f"[ColdMail] Generation failed: {e}")
            return self._fallback(company, job_title, recipient_name, tone)

    def _build_prompt(
        self,
        company: str,
        job_title: str,
        resume_summary: str,
        reason: str,
        recipient_name: str | None,
        tone: str,
    ) -> str:
        greeting = f" to {recipient_name}" if recipient_name else ""
        tone_guide = {
            "professional": "Be professional and polished",
            "casual": "Be friendly and conversational",
            "enthusiastic": "Show genuine excitement and energy",
        }
        guide = tone_guide.get(tone, "Be professional")

        return f"""
Write a cold email{greeting} at {company} regarding the {job_title} role.

Background: {resume_summary[:300]}
Why Reaching Out: {reason}
Tone: {tone} — {guide}

Return format:
Subject: <subject line>
[empty line]
<body>
"""

    def _parse(self, content: str, company: str, job_title: str,
                recipient_name: str | None, recipient_email: str | None, tone: str) -> dict[str, str]:
        """Parse the LLM response into subject and body."""
        subject = ""
        body = content

        # Extract subject line
        for prefix in ["Subject:", "Subject :", "Re:"]:
            if prefix in content:
                parts = content.split(prefix, 1)
                if len(parts) > 1:
                    subject = parts[1].split("\n")[0].strip().strip('"').strip("'")
                    body = parts[1].split("\n", 1)[1].strip() if "\n" in parts[1] else ""
                    break

        return {
            "subject_line": subject or f"Regarding the {job_title} position at {company}",
            "email_body": body or content,
            "to_name": recipient_name or "",
            "to_email": recipient_email or "",
            "tone": tone,
        }

    def _fallback(self, company: str, job_title: str, recipient_name: str | None, tone: str) -> dict[str, str]:
        greeting = f"Dear {recipient_name}" if recipient_name else f"Dear {company} Team"
        return {
            "subject_line": f"Interest in the {job_title} role at {company}",
            "email_body": f"""{greeting},

I came across the {job_title} position at {company} and was immediately drawn to the role. My background aligns well with what you are looking for.

I would love the opportunity to discuss how my experience could contribute to {company}'s success.

Would you be open to a brief chat next week?

Best regards,
[Your Name]""",
            "to_name": recipient_name or "",
            "to_email": "",
            "tone": tone,
        }
