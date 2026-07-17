import requests
from typing import Optional

from src.config import get_config

logger = __import__("logging").getLogger("line_notify")


class LINENotifier:
    def __init__(self, token: Optional[str] = None):
        cfg = get_config()
        self.token = token or cfg.notification.line_notify_token
        self.enabled = cfg.notification.line_notify_enabled and bool(self.token)
        self.api_url = "https://notify-api.line.me/api/notify"

    def send(self, message: str) -> bool:
        if not self.enabled:
            logger.debug("LINE notification disabled")
            return False

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                data={"message": message},
                timeout=10,
            )

            if response.status_code == 200:
                logger.info("LINE notification sent")
                return True
            else:
                logger.error(f"LINE API error: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"LINE notification failed: {e}")
            return False

    def send_signal(self, signal) -> bool:
        if not self.enabled:
            return False

        msg = (
            f"\n><> MAE PLA GREEN PEN AI\n"
            f"========================\n"
            f"XAUUSD\n"
            f"Decision: {signal.direction}\n"
            f"Grade: {signal.signal_grade}\n"
            f"Score: {signal.confidence_score}/10\n"
        )

        if signal.direction != "WAIT":
            msg += (
                f"\nTRADE PLAN\n"
                f"Entry: ${signal.entry_price:.2f}\n"
                f"SL: ${signal.stop_loss:.2f}\n"
                f"TP1: ${signal.take_profit_1:.2f}\n"
                f"RR: {signal.risk_reward}:1\n"
            )
        else:
            msg += "\nNo active setup. Waiting.\n"

        msg += "========================\n#MaePlaGreenPen #XAUUSD"

        return self.send(msg)

    def send_alert(self, title: str, body: str) -> bool:
        return self.send(f"\n{title}\n{body}")
