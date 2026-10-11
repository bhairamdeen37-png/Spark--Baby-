"""
Generates study notes / summaries / formula sheets through the AI router.
"""
from services import ai_router

NOTES_SYSTEM_PROMPT = (
    "You are a study-notes generator for a tutoring app. Produce clear, "
    "well-structured notes using short headings and bullet points. Do not "
    "invent textbook page numbers, citations, or quotations. If the topic "
    "is ambiguous, make a reasonable, clearly-stated assumption about scope "
    "instead of asking a clarifying question."
)


async def generate_notes(topic: str, style: str = "detailed") -> str:
    """style: 'short' | 'detailed' | 'formula_sheet' | 'flashcards'"""
    style_instructions = {
        "short": "Give short notes — key points only, max ~150 words.",
        "detailed": "Give detailed notes covering the topic thoroughly with examples.",
        "formula_sheet": "Give only a formula sheet — formulas with one-line meaning each, no prose.",
        "flashcards": "Give 8-10 flashcards in Q: / A: pairs covering the key facts.",
    }
    instruction = style_instructions.get(style, style_instructions["detailed"])
    user_prompt = f"Topic: {topic}\n\n{instruction}"
    return await ai_router.generate_answer(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=NOTES_SYSTEM_PROMPT,
    )
