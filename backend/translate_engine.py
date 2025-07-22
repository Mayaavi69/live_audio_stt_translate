import os
import logging
import requests
from dotenv import load_dotenv
from transformers import MarianMTModel, MarianTokenizer
import torch

load_dotenv(dotenv_path='../config/.env')

class TranslationEngine:
    def __init__(self):
        self.deepl_api_key = os.getenv("DEEPL_API_KEY")
        if not self.deepl_api_key or self.deepl_api_key == "your_deepl_api_key":
            logging.warning("DeepL API key not found or is a placeholder. DeepL translation will not work.")
            self.deepl_api_key = None
        self._marian_model = None
        self._marian_tokenizer = None

    @property
    def marian_model(self):
        if self._marian_model is None:
            logging.info("Loading MarianMT model for fallback...")
            self._marian_model = MarianMTModel.from_pretrained("Helsinki-NLP/opus-mt-hi-en")
            logging.info("MarianMT model loaded.")
        return self._marian_model

    @property
    def marian_tokenizer(self):
        if self._marian_tokenizer is None:
            logging.info("Loading MarianMT tokenizer for fallback...")
            self._marian_tokenizer = MarianTokenizer.from_pretrained("Helsinki-NLP/opus-mt-hi-en")
            logging.info("MarianMT tokenizer loaded.")
        return self._marian_tokenizer

    def translate_deepl(self, text: str) -> str:
        logging.info("Translating with DeepL...")
        url = "https://api-free.deepl.com/v2/translate"
        params = {
            "auth_key": self.deepl_api_key,
            "text": text,
            "source_lang": "HI",
            "target_lang": "EN-US",
        }
        response = requests.post(url, data=params)
        response.raise_for_status()
        return response.json()["translations"][0]["text"]

    def translate_marianmt(self, text: str) -> str:
        logging.info("Translating with MarianMT...")
        inputs = self.marian_tokenizer(text, return_tensors="pt", padding=True)
        with torch.no_grad():
            generated_ids = self.marian_model.generate(**inputs)
        return self.marian_tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]

    def translate(self, hindi_text: str) -> str:
        if self.deepl_api_key:
            try:
                translated_text = self.translate_deepl(hindi_text)
                logging.info("DeepL translation successful.")
                return translated_text
            except Exception as e:
                logging.warning(f"DeepL translation failed: {e}. Falling back to MarianMT.")
                return self.translate_marianmt(hindi_text)
        else:
            return self.translate_marianmt(hindi_text)