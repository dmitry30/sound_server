import re
from typing import Optional
from datetime import datetime

from app.ml.punctuation import PunctuationModel


class PostProcessor:
    def __init__(self):
        self.punctuation_model = PunctuationModel()

    def process_text(self, raw_text: str) -> str:
        """
        Apply full post-processing pipeline to raw transcribed text:
        1. Basic cleaning
        2. Punctuation restoration
        3. Capitalization
        4. Final formatting
        """
        if not raw_text or not raw_text.strip():
            return ""

        try:
            # Step 1: Basic text cleaning
            cleaned_text = self._clean_text(raw_text)

            # Step 2: Add punctuation using ML model
            punctuated_text = self.punctuation_model.add_punctuation(cleaned_text)

            # Step 3: Apply capitalization rules
            capitalized_text = self._capitalize_text(punctuated_text)

            # Step 4: Final formatting
            final_text = self._format_final_text(capitalized_text)

            return final_text

        except Exception as e:
            print(f"Post-processing error: {e}")
            return raw_text

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())

        # Fix common transcription artifacts (placeholder)
        common_fixes = {
            'при вет': 'привет',
            'какде ла': 'как дела',
            'спа сибо': 'спасибо'
        }

        for wrong, correct in common_fixes.items():
            text = text.replace(wrong, correct)

        return text

    def _capitalize_text(self, text: str) -> str:
        """Apply capitalization rules"""
        if not text:
            return text

        # Capitalize first letter of sentence
        if len(text) > 0:
            text = text[0].upper() + text[1:]

        # Capitalize proper nouns (simple rule-based approach)
        proper_nouns = ['я', 'мы', 'вы', 'он', 'она', 'оно', 'они']
        words = text.split()

        for i, word in enumerate(words):
            # Skip if word contains punctuation or is too short
            if len(word) <= 1 or not word.isalpha():
                continue

            # Capitalize proper nouns at start of sentence or after punctuation
            if word.lower() in proper_nouns and (i == 0 or words[i - 1][-1] in '.!?'):
                words[i] = word.capitalize()

        return ' '.join(words)

    def _format_final_text(self, text: str) -> str:
        """Apply final formatting touches"""
        # Ensure proper spacing around punctuation
        text = re.sub(r'\s+([.,!?])', r'\1', text)  # Remove space before punctuation
        text = re.sub(r'([.,!?])(\w)', r'\1 \2', text)  # Add space after punctuation

        return text.strip()