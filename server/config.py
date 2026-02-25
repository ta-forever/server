import asyncio
import logging
import os
from typing import Callable, Dict

import trueskill
import yaml

from .decorators import with_logger

# Logging setup
TRACE = 5
logging.addLevelName(TRACE, "TRACE")
logging.getLogger("aiomeasures").setLevel(logging.INFO)
logging.getLogger("aio_pika").setLevel(logging.INFO)

# Constants
FFA_TEAM = 1

# Credit to Axle for parameter changes,
# see: http://forums.faforever.com/viewtopic.php?f=45&t=11698#p119599
# Optimum values for ladder here, using them for global as well.
trueskill.setup(mu=1500, sigma=500, beta=240, tau=10, draw_probability=0.10)


@with_logger
class ConfigurationStore:
    def __init__(self):
        """
        Change default values here.
        """
        self.CONFIGURATION_REFRESH_TIME = 300
        self.LOG_LEVEL = "DEBUG"
        self.PROFILING_COUNT = 300
        self.PROFILING_DURATION = 2
        self.PROFILING_INTERVAL = -1

        self.CONTROL_SERVER_PORT = 4000
        self.METRICS_PORT = 8011
        self.ENABLE_METRICS = False

        self.DB_SERVER = "127.0.0.1"
        self.DB_PORT = 3306
        self.DB_LOGIN = "root"
        self.DB_PASSWORD = "banana"
        self.DB_NAME = "faf"
        self.FAF_ANOPE_DB_NAME = "faf-anope"

        self.API_CLIENT_ID = "client_id"
        self.API_CLIENT_SECRET = "banana"
        self.API_TOKEN_URI = "https://api.test.taforever.com/oauth/token"
        self.API_BASE_URL = "https://api.test.taforever.com/"
        self.USE_API = True

        self.MQ_USER = "faf-lobby"
        self.MQ_PASSWORD = "banana"
        self.MQ_SERVER = "127.0.0.1"
        self.MQ_PORT = 5672
        self.MQ_VHOST = "/faf-lobby"
        self.MQ_EXCHANGE_NAME = "faf-rabbitmq"

        self.WWW_URL = "https://www.taforever.com"
        self.CONTENT_URL = "http://content.taforever.com"
        self.FAF_POLICY_SERVER_BASE_URL = "http://faf-policy-server"
        self.USE_POLICY_SERVER = True

        self.FORCE_STEAM_LINK_AFTER_DATE = 1536105599  # 5 september 2018 by default
        self.FORCE_STEAM_LINK = False

        self.NEWBIE_BASE_MEAN = 500
        self.NEWBIE_MIN_GAMES = 10
        self.START_RATING_MEAN = 1500
        self.START_RATING_DEV = 500
        self.TOP_PLAYER_MIN_RATING = 1600

        self.TWILIO_ACCOUNT_SID = ""
        self.TWILIO_TOKEN = ""
        self.TWILIO_TTL = 86400
        self.COTURN_HOSTS = []
        self.COTURN_KEYS = []

        self.GEO_IP_DATABASE_PATH = "GeoLite2-Country.mmdb"
        self.GEO_IP_DATABASE_URL = "https://download.maxmind.com/app/geoip_download"
        self.GEO_IP_LICENSE_KEY = ""
        self.GEO_IP_DATABASE_MAX_AGE_DAYS = 22

        self.LADDER_1V1_OUTCOME_OVERRIDE = True
        self.LADDER_ANTI_REPETITION_LIMIT = 2
        self.LADDER_SEARCH_EXPANSION_MAX = 0.25
        self.LADDER_SEARCH_EXPANSION_STEP = 0.05
        # The maximum amount of time in seconds) to wait between pops.
        self.QUEUE_POP_TIME_MAX = 180
        # The number of possible matches we would like to have when the queue
        # pops. The queue pop time will be adjusted based on the current rate of
        # players queuing to try and hit this number.
        self.QUEUE_POP_DESIRED_MATCHES = 4
        # How many previous queue sizes to consider
        self.QUEUE_POP_TIME_MOVING_AVG_SIZE = 5
        self.STRICT_MAP_POOL = True

        self.CASE_SENSITIVE_MAP_NAMES = False
        self.TADA_API_URL = 'https://tademos.xyz'
        self.TADA_UPLOAD_ENABLE = True
        self.TADA_UPLOAD_MAX_SIZE_MB = 164
        self.TADA_AUTO_UPLOAD_LEADERBOARD_IDS = []

        self.GALACTIC_WAR_GALAXIES = [
            {
                "technical_name": "ota",
                "display_name": "OTA",
                "state_file": "/content/galactic_war/galactic_war.json",
                "map_select_strategy": "REGEX",   # or "MAP_POOL"
                "mods": [
                    {
                        "technical_name": "tacc",
                        "map_select_regexes": [".*"],
                        "map_select_mmq_id": -1
                    }
                ],
                "rank_avatar_ids": {
                    "arm": [21, 22, 23, 24, 25, 26, 27, 28, 29],
                    "core": [30, 31, 32, 33, 34, 35, 36, 37, 38]
                },
                "rank_achievement_ids": {}
            },
        ]
        self.GALACTIC_WAR_DEFAULT_GALAXY = "ota"    # for old clients that don't inform the galaxy name
        self.GALACTIC_WAR_SCENARIO_PATH = "/content/galactic_war/scenarios"
        self.GALACTIC_WAR_INITIAL_SCENARIO = "scenario_0.gml"

        self.GALACTIC_WAR_RELOAD_RESET_TARGETS = []   # galaxy technical names for below
        self.GALACTIC_WAR_RELOAD_STATE = 0      # a change will trigger GalacticWarService to reload its state
        self.GALACTIC_WAR_RESET = 0             # a change will trigger GalacticWarService to reset to GALACTIC_WAR_INITIAL_SCENARIO
        self.GALACTIC_WAR_RANDOMISE_MAPS = 0    # a change will trigger GalacticWarService to randomise the maps on all planets

        self.GALACTIC_WAR_DOMINANCE_THRESHOLD = 3.0    # ratio between highest score to lowest score to consider a planet conquered
        self.GALACTIC_WAR_MAX_SCORE = 30.0                  # maximum amount per player by which faction-score for a planet may increase
        self.GALACTIC_WAR_STAKES_STRATEGY = "rank"          # "rank" or "rating"
        self.GALACTIC_WAR_STAKES_RANK_FACTOR = 4.0          # stake is proportional to 1/(1+exp(-rank_difference/GALACTIC_WAR_STAKES_RANK_FACTOR))
        self.GALACTIC_WAR_MIN_MAX_PLANET_ADJ = [5.0, 25.0]  # lowest tier-rank in the game linearly interpolates between this min/max to determine change in planet score
        self.GALACTIC_WAR_UPDATE_CRONTAB = "*/10 * * * *"   # periods at which to process state updates. Or empty string to update immediately after each game
        self.GALACTIC_WAR_REQUIRE_CORRECT_MOD = True        # require games to be played on the correct mod
        self.GALACTIC_WAR_DEFAULT_PLANET_SIZE = 100
        self.GALACTIC_WAR_MANUAL_CAPTURE = []           # capture a planet for debugging purposes. eg {"planet":"Core Prime", "faction":"arm"}
        self.GALACTIC_WAR_MANUAL_ATTACK = []            # record an attack on a planet for debugging puroses. eg {"planet:"Academica Cromyona", "pid1":1, "pid2": 2, "faction1":"arm", "faction2":"core", "rank1":10, "rank2":20, "pwin": 0.5}
        self.GALACTIC_WAR_RANK_THRESHOLDS = [60, 150, 300, 600, 1200, 2400, 4800, 9600] # for avatar grant. need to keep in sync with dfc-config.json :(
        self.GALACTIC_WAR_RANK_AVATAR_AUTO_SELECT = True    # auto select user's new rank avatar when its granted

        self.ENABLE_FACTION_LOOKUP_FROM_REPLAY_META = True

        self.IRC_HOSTSTRING = "taf-ircd:~8167"
        self.IRC_RECONNECT_DELAY = 1
        self.IRC_NICK = "taf-python-server"
        self.IRC_USER = "taf-python-server"
        self.IRC_PASS = "b4n4n4"
        self.IRC_OPER_NAME = "taf-python-server"
        self.IRC_OPER_PASS = "b4n4n4"

        self.IRC_CHAT_BAN_REASON_IDENTIFIER = "all chats"   # ban reasons ending with this string will select CHAT_BAN
        self.IRC_ADD_CHAT_BAN = "GLINE {mask} {duration} :{reason}"
        self.IRC_DEL_CHAT_BAN = "GLINE -{mask}"

        self.IRC_CHANNEL_BAN_CHANNELS = "#coreprime"   # only for purpose of informing clients in which channels they're banned
        self.IRC_ADD_CHANNEL_BAN = "SAMODE #coreprime +b {mask}"
        self.IRC_DEL_CHANNEL_BAN = "SAMODE #coreprime -b {mask}"

        self.GAME_TITLE_BADWORDS = []

        self.PUBLISH_GAME_INFO_WITH_PINGS_ONLY = False
        self.NO_GAME_RESULTS_IS_LOSS_FOR_HOST = True
        self.NEW_USER_WELCOME_MESSAGE = None
        self.QDATASTREAM_PROTOCOL_MAX_BLOCK_LENGTH = 65535
        self.RUN_VALIDATE_LAUNCH_CODES = False
        self.UNRANK_ON_INVALID_LAUNCH_CODES = False
        self.RANKED_MAX_NUMBER_OF_AI = 0
        self.NOTIFY_USERS_ON_INVALID_LAUNCH_CODES = False

        self._defaults = {
            key: value for key, value in vars(self).items() if key.isupper()
        }

        self._callbacks: Dict[str, Callable] = {}
        self.refresh()

    def refresh(self) -> None:
        new_values = self._defaults.copy()

        config_file = os.getenv("CONFIGURATION_FILE")
        if config_file is not None:
            try:
                with open(config_file) as f:
                    new_values.update(yaml.safe_load(f))
            except FileNotFoundError:
                self._logger.info("No configuration file found at %s", config_file)
            except TypeError:
                self._logger.info(
                    "Configuration file at %s appears to be empty", config_file
                )

        triggered_callback_keys = tuple(
            key
            for key in new_values
            if key in self._callbacks
            and hasattr(self, key)
            and getattr(self, key) != new_values[key]
        )

        for key, new_value in new_values.items():
            old_value = getattr(self, key, None)
            if new_value != old_value:
                self._logger.info(
                    "New value for %s: %s -> %s", key, old_value, new_value
                )
            setattr(self, key, new_value)


        for key in triggered_callback_keys:
            self._dispatch_callback(key)

    def register_callback(self, key: str, callback: Callable) -> None:
        self._callbacks[key.upper()] = callback

    def _dispatch_callback(self, key: str) -> None:
        callback = self._callbacks[key]
        if asyncio.iscoroutinefunction(callback):
            asyncio.create_task(callback())
        else:
            callback()


def set_log_level():
    logger = logging.getLogger()
    logger.setLevel(config.LOG_LEVEL)


config = ConfigurationStore()
config.register_callback("LOG_LEVEL", set_log_level)
