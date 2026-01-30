from egse.settings import Settings

CS_SETTINGS = Settings.load("KIKUSUI PMX-A Control Server")
PROTOCOL = CS_SETTINGS.get("PROTOCOL", "tcp")  # Communication protocol
