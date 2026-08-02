"""Centralized configuration for the QA agent."""
import os
from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

LLM_MODEL = LiteLlm(model="openrouter/deepseek/deepseek-v4-flash")

# Site login credentials (override in .env)
SITE_EMAIL = os.getenv("SITE_EMAIL", "director@calliq.com")
SITE_PASSWORD = os.getenv("SITE_PASSWORD", "password")
SITE_PASSWORD_FALLBACK = os.getenv("SITE_PASSWORD_FALLBACK", "director_password")

MAX_RETRIES_PER_CHECK = 3
MAX_LLM_CALLS_PER_NAVIGATOR = 50
MAX_CHECKS_PER_SCREEN = 8
MAX_TIME_PER_SCREEN_SECONDS = 300
MAX_TOTAL_COST_USD = 2.0
TEST_FILE_PATH = r"C:\Users\DIVYA SINGHI\OneDrive\Desktop\test for tester agent call q\(Audio) i love u joe vid.m4a"

# Install LiteLLM rate limiting + 429 retry (free tier: ~20 req/min)
from .utils.throttle import install_throttle

install_throttle()