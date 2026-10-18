"""Constants for Life RPG."""

DOMAIN = "life_rpg"
VERSION = "1.0.2"
URL_BASE = "/life_rpg_static"
PANEL_PATH = "life-rpg"
CONF_RACE = "race"
CONF_USER = "user_id"
ART_URL = "/life_rpg_art"

# art and AI (options -> "Art and AI")
CONF_BODY = "body"
CONF_COMFY_URL = "comfyui_url"
CONF_FAMILY = "model_family"
CONF_CHECKPOINT = "checkpoint"
CONF_PAINT = "paint"
CONF_AI_TASK = "ai_task_entity"
CONF_LLM = "llm_features"
CONF_ART_STYLE = "art_style"
CONF_GODDESS = "goddess_name"
CONF_PERSONA = "goddess_persona"
PERSONAS = ["goddess", "own"]
# quests that can be logged in Home Assistant instead of (or on top of) a sensor
CONF_MANUAL = "manual_quests"
CONF_WATER_UNIT = "water_unit"
CONF_CLOCK = "clock"
CONF_CORRECTIONS = "corrections"
CONF_KIDS = "kids_mode"
CONF_DAILY_BOUNTIES = "daily_bounties"
CONF_CHAT_AGENT = "chat_agent"
CONF_SPEED = "paint_speed"
SPEED_OPTIONS = ["quality", "balanced", "fast"]
CONF_FAST_MODEL = "fast_model"
CONF_EDIT_MODEL = "edit_model"  # an image-edit model (Flux Kontext, Qwen Image Edit) for consistent characters
CONF_EDIT_PARTS = "edit_parts"  # its text encoders and VAE, found when it's picked
CORRECTION_OPTIONS = ["steps", "floors", "hydration"]
CLOCK_OPTIONS = ["12", "24"]
TWELVE_HOUR_COUNTRIES = {"US", "CA", "AU", "NZ", "PH", "IN", "PK", "EG", "SA", "CO", "MX"}
WATER_UNIT_OPTIONS = ["ml", "floz"]
FLOZ_ML = 29.5735
GLASS = {"ml": 250, "floz": 8}  # one glass, in each unit
CONF_PENALTY = "emergency_penalty"
CONF_WORK_DAYS = "work_days"
CONF_WORK_START = "work_start"
CONF_WORK_END = "work_end"
CONF_WORK_ENTITY = "work_entity"
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WORK_DEFAULTS = {
    CONF_PENALTY: True,
    CONF_WORK_DAYS: WEEKDAYS[:5],
    CONF_WORK_START: "09:00:00",
    CONF_WORK_END: "17:00:00",
}
MANUAL_OPTIONS = ["hydration", "floors", "sleep"]
STAIR_FLIGHT = 1
ART_STYLES = ["painted", "pixel"]
PAINT_OPTIONS = ["portrait", "items", "guardians", "characters"]
LLM_OPTIONS = ["lune_chat", "flavour", "haggling"]
BODY_OPTIONS = ["androgynous", "feminine", "masculine"]
FAMILY_OPTIONS = ["sdxl", "flux", "flux_unet", "custom"]
FLUX_PARTS = {"clip_l": "flux_clip_l", "t5": "flux_t5", "vae": "flux_vae"}  # option keys for the separate files

# quest -> option holding its source sensor (bedtime reads the sleep sensor's startTime)
SOURCES = {
    "steps": "steps_entity",
    "floors": "floors_entity",
    "sleep": "sleep_entity",
    "hydration": "hydration_entity",
}
CONF_BEDTIME = "bedtime_goal"
CONF_BEDTIME_ON = "bedtime_quest"
# quest -> (goal option, default)
GOALS = {
    "steps": ("steps_goal", 8000),
    "floors": ("floors_goal", 10),
    "sleep": ("sleep_goal", 7.5),
    "hydration": ("hydration_goal", 2000),
    "bedtime": (CONF_BEDTIME, "23:00:00"),
}
# quest -> {unit: factor} into steps, floors, minutes (sleep; Health Connect's unit) and mL
UNITS = {
    "steps": {},
    "floors": {"m": 1 / 3, "ft": 1 / 10},
    "sleep": {"h": 60, "s": 1 / 60, "d": 1440},
    "hydration": {
        "L": 1000,
        "l": 1000,
        "mL": 1,
        "ml": 1,
        "fl. oz.": 29.5735,
        "fl. oz": 29.5735,
        "fl oz": 29.5735,
        "oz": 29.5735,
        "gal": 3785.41,
    },
}
