import re
import asyncio
import functools
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
from pydub import AudioSegment
import numpy as np

class PostProcessing:
    def __init__(self, model_name: str = "oliverguhr/fullstop-punctuation-multilang-large"):
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForTokenClassification.from_pretrained(model_name)
        self.punctuator = pipeline(
            "token-classification",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy="simple",
            device=0
        )
        self.audio_emotion = pipeline(
            task="audio-classification",
            model="superb/wav2vec2-base-superb-er"
        )

    def add_punctuation(self, text: str) -> str:
        preds = self.punctuator(text)
        punctuated = []
        for token in preds:
            word = token["word"]
            label = token.get("entity_group", "O")
            punctuated.append(word)
            if label in [".", ",", "?", "!", ";", ":"]:
                punctuated[-1] += label

        text_out = " ".join(punctuated)
        text_out = (
            text_out.replace(" ,", ",")
            .replace(" .", ".")
            .replace(" ?", "?")
            .replace(" !", "!")
            .replace(" ;", ";")
            .replace(" :", ":")
        )
        return text_out

    def _ndarray_to_audiosegment(self, arr: np.ndarray, sample_rate: int = 16000):
        if np.issubdtype(arr.dtype, np.floating):
            arr = (arr * 32767).astype(np.int16)
        elif arr.dtype != np.int16:
            arr = arr.astype(np.int16)
        channels = 1 if arr.ndim == 1 else arr.shape[1]
        return AudioSegment(
            data=arr.tobytes(),
            sample_width=2,
            frame_rate=sample_rate,
            channels=channels,
        )

    def capitalize_sentences(self, text: str) -> str:
        def cap_after_punct(match):
            return match.group(1) + match.group(2).upper()

        text = re.sub(r"\s+", " ", text.strip())
        if text:
            text = text[0].upper() + text[1:]
        text = re.sub(r"([.!?]\s+)(\w)", cap_after_punct, text)
        return text

    async def process(self, text: str, text_list, audio_list):

        if not text.strip():
            return "", [], []

        loop = asyncio.get_running_loop()

        punctuated = await loop.run_in_executor(
            None, functools.partial(self.add_punctuation, text)
        )
        capitalized = await loop.run_in_executor(
            None, functools.partial(self.capitalize_sentences, punctuated)
        )

        sentence_regex = re.compile(r'[^.!?]+[.!?]')
        sentences = [s.strip() for s in sentence_regex.findall(capitalized) if s.strip()]

        grouped_texts = []
        grouped_audios = []

        for sent in sentences:
            sent_words = sent.split()
            num_words = len(sent_words)

            curr_texts = []
            curr_audios = []
            words_in_curr = 0

            while text_list and words_in_curr < num_words:
                piece_words = len(text_list[0].split())
                curr_texts.append(text_list.pop(0))
                curr_audios.append(audio_list.pop(0))
                words_in_curr += piece_words

            grouped_texts.append(" ".join(curr_texts).strip())

            if len(curr_audios) > 1:
                grouped_audio = np.concatenate(curr_audios)
            else:
                grouped_audio = curr_audios[0]
            grouped_audios.append(grouped_audio)

        if text_list:
            grouped_texts.append(" ".join(text_list).strip())
            if len(audio_list) > 1:
                grouped_audio = np.concatenate(audio_list)
            else:
                grouped_audio = audio_list[0]
            grouped_audios.append(grouped_audio)

        emotions = []
        for audio_arr in grouped_audios:
            if np.issubdtype(audio_arr.dtype, np.integer):
                audio_arr = audio_arr.astype(np.float32) / 32768.0
            elif not np.issubdtype(audio_arr.dtype, np.floating):
                audio_arr = audio_arr.astype(np.float32)

            result = await loop.run_in_executor(
                None, functools.partial(self.audio_emotion, audio_arr)
            )
            emotions.append(result)

        return capitalized, grouped_texts, emotions
